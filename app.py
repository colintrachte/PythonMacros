import os
import json
import importlib.util
import inspect
import traceback
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- Configuration & Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(BASE_DIR, 'plugins')
HISTORY_DIR = os.path.join(BASE_DIR, 'history')
SESSION_FILE = os.path.join(BASE_DIR, 'last_session.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config_info.json')
DEFAULT_WS = os.path.join(BASE_DIR, 'workspaces')
HISTORY_META_FILE = os.path.join(HISTORY_DIR, 'meta.json')
MAX_HISTORY = 50

# Ensure necessary directories exist on startup
for path in [PLUGIN_DIR, DEFAULT_WS, HISTORY_DIR]:
    if not os.path.exists(path):
        os.makedirs(path)


def get_config():
    """Reads the workspace configuration, falling back to default if missing."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"workspace": DEFAULT_WS}


def read_history_meta():
    """Returns history metadata: {pointer, count}"""
    if os.path.exists(HISTORY_META_FILE):
        try:
            with open(HISTORY_META_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"pointer": -1, "count": 0}


def write_history_meta(meta):
    with open(HISTORY_META_FILE, 'w') as f:
        json.dump(meta, f)


def history_path(index):
    return os.path.join(HISTORY_DIR, f'session_{index:04d}.json')


# --- Routes ---

@app.route('/')
def hello_world():
    return render_template("index.html")


@app.route('/get_workspace', methods=['GET'])
def get_workspace_route():
    return jsonify(get_config())


@app.route('/set_workspace', methods=['POST'])
def set_workspace():
    path = request.json.get('path')
    if not path:
        return jsonify({"error": "No path provided"}), 400
    config = {"workspace": path}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    return jsonify(config)


@app.route('/list_workspaces', methods=['GET'])
def list_workspaces():
    current = get_config()['workspace']
    parent = os.path.dirname(current)
    try:
        options = [os.path.join(parent, d) for d in os.listdir(parent)
                   if os.path.isdir(os.path.join(parent, d))]
        return jsonify(options[:15])
    except Exception:
        return jsonify([DEFAULT_WS])


# --- Session Save / Load ---

@app.route('/save', methods=['POST'])
def save_config():
    """Saves the current sequence to last_session.json (autosave target)."""
    scripts = request.json
    with open(SESSION_FILE, 'w') as f:
        json.dump(scripts, f, indent=4)
    return jsonify({"status": "success"})


@app.route('/save_as', methods=['POST'])
def save_as():
    """Saves sequence to a named file inside the workspace."""
    data = request.json
    filename = data.get('filename', '').strip()
    scripts = data.get('scripts', [])

    if not filename:
        return jsonify({"error": "No filename provided"}), 400

    # Sanitize: only allow .json extension, no path traversal
    basename = os.path.basename(filename)
    if not basename.endswith('.json'):
        basename += '.json'

    workspace = get_config()['workspace']
    dest = os.path.join(workspace, basename)

    with open(dest, 'w') as f:
        json.dump(scripts, f, indent=4)

    return jsonify({"status": "success", "saved_to": dest, "filename": basename})


@app.route('/load', methods=['GET'])
def load_config():
    """Loads the last autosaved sequence."""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                return jsonify(json.load(f))
        except (json.JSONDecodeError, IOError):
            return jsonify([])
    return jsonify([])


@app.route('/load_file', methods=['POST'])
def load_file():
    """Loads a sequence from a named file in the workspace."""
    filename = request.json.get('filename', '').strip()
    if not filename:
        return jsonify({"error": "No filename provided"}), 400

    basename = os.path.basename(filename)
    workspace = get_config()['workspace']
    path = os.path.join(workspace, basename)

    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {basename}"}), 404

    try:
        with open(path, 'r') as f:
            return jsonify(json.load(f))
    except (json.JSONDecodeError, IOError) as e:
        return jsonify({"error": str(e)}), 500


# --- History (Undo/Redo) ---

@app.route('/history/push', methods=['POST'])
def history_push():
    """
    Pushes a new state onto the history stack.
    Truncates any redo-forward states (new action clears redo).
    Caps total history at MAX_HISTORY entries (circular replacement).
    """
    scripts = request.json
    meta = read_history_meta()

    # New action clears redo: everything after current pointer is gone
    new_pointer = meta["pointer"] + 1

    # Cap at MAX_HISTORY using modulo for circular behavior
    file_index = new_pointer % MAX_HISTORY

    with open(history_path(file_index), 'w') as f:
        json.dump(scripts, f, indent=4)

    meta["pointer"] = new_pointer
    meta["count"] = min(new_pointer + 1, MAX_HISTORY)
    write_history_meta(meta)

    return jsonify({"status": "success", "pointer": new_pointer, "count": meta["count"]})


@app.route('/history/undo', methods=['GET'])
def history_undo():
    """Returns the state one step back from the current pointer."""
    meta = read_history_meta()
    pointer = meta["pointer"]

    if pointer <= 0:
        return jsonify({"error": "Nothing to undo", "at_start": True}), 400

    target = pointer - 1
    file_index = target % MAX_HISTORY
    path = history_path(file_index)

    if not os.path.exists(path):
        return jsonify({"error": "History file missing"}), 500

    with open(path, 'r') as f:
        state = json.load(f)

    meta["pointer"] = target
    write_history_meta(meta)

    return jsonify({"state": state, "pointer": target, "count": meta["count"]})


@app.route('/history/redo', methods=['GET'])
def history_redo():
    """Returns the state one step forward from the current pointer."""
    meta = read_history_meta()
    pointer = meta["pointer"]
    count = meta["count"]

    if pointer >= count - 1:
        return jsonify({"error": "Nothing to redo", "at_end": True}), 400

    target = pointer + 1
    file_index = target % MAX_HISTORY
    path = history_path(file_index)

    if not os.path.exists(path):
        return jsonify({"error": "History file missing"}), 500

    with open(path, 'r') as f:
        state = json.load(f)

    meta["pointer"] = target
    write_history_meta(meta)

    return jsonify({"state": state, "pointer": target, "count": meta["count"]})


@app.route('/history/status', methods=['GET'])
def history_status():
    """Returns current undo/redo availability."""
    meta = read_history_meta()
    return jsonify({
        "can_undo": meta["pointer"] > 0,
        "can_redo": meta["pointer"] < meta["count"] - 1,
        "pointer": meta["pointer"],
        "count": meta["count"]
    })


# --- Plugins & Execution ---

@app.route('/list_plugins', methods=['GET'])
def list_plugins():
    return jsonify(list(get_plugin_functions().keys()))


@app.route('/execute', methods=['POST'])
def execute_scripts():
    data = request.json
    filename = data.get('filename')
    scripts = data.get('scripts', [])

    workspace = get_config()['workspace']
    target_path = os.path.join(workspace, filename)

    if not os.path.exists(target_path):
        return jsonify({"error": f"File not found: {target_path}"}), 404

    try:
        with open(target_path, 'r') as f:
            lines = f.readlines()

        available_plugins = get_plugin_functions()

        for step in scripts:
            key = step.get('pluginKey')
            if key in available_plugins:
                lines = available_plugins[key](lines)

        with open(target_path, 'w') as f:
            f.writelines(lines)

        return jsonify({"status": "success", "message": "File processed successfully"})

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


def get_plugin_functions():
    """Dynamically loads Python functions from the plugins folder."""
    plugins = {}
    if not os.path.exists(PLUGIN_DIR):
        return plugins
    for filename in os.listdir(PLUGIN_DIR):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            path = os.path.join(PLUGIN_DIR, filename)
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for name, func in inspect.getmembers(module, inspect.isfunction):
                    plugins[f"{module_name}.{name}"] = func
            except Exception as e:
                print(f"Failed to load plugin {filename}: {e}")
    return plugins


if __name__ == '__main__':
    app.run(debug=True, port=5000)
