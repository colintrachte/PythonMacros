import os
import json
import importlib.util
import inspect
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- Configuration & Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(BASE_DIR, 'plugins')
SESSION_FILE = os.path.join(BASE_DIR, 'last_session.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config_info.json')
DEFAULT_WS = os.path.join(BASE_DIR, 'workspaces')

# Ensure necessary directories exist on startup
for path in [PLUGIN_DIR, DEFAULT_WS]:
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

# --- Routes ---

@app.route('/get_workspace', methods=['GET'])
def get_workspace_route():
    """Returns the current active workspace path."""
    return jsonify(get_config())

@app.route('/set_workspace', methods=['POST'])
def set_workspace():
    """Updates the active workspace path in the config file."""
    path = request.json.get('path')
    if not path:
        return jsonify({"error": "No path provided"}), 400
    
    config = {"workspace": path}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    return jsonify(config)

@app.route('/list_workspaces', methods=['GET'])
def list_workspaces():
    """Suggests workspace directories based on the parent of the current workspace."""
    current = get_config()['workspace']
    parent = os.path.dirname(current)
    try:
        # List directories in the parent folder
        options = [os.path.join(parent, d) for d in os.listdir(parent) 
                  if os.path.isdir(os.path.join(parent, d))]
        return jsonify(options[:15]) 
    except Exception:
        return jsonify([DEFAULT_WS])

@app.route('/save', methods=['POST'])
def save_config():
    """Saves the current processing sequence to the session file."""
    scripts = request.json
    with open(SESSION_FILE, 'w') as f:
        json.dump(scripts, f, indent=4)
    return jsonify({"status": "success"})

@app.route('/load', methods=['GET'])
def load_config():
    """Loads the last saved processing sequence."""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                return jsonify(json.load(f))
        except (json.JSONDecodeError, IOError):
            return jsonify([])
    return jsonify([])

@app.route('/list_plugins', methods=['GET'])
def list_plugins():
    """Returns a list of available function keys from the plugins directory."""
    return jsonify(list(get_plugin_functions().keys()))

@app.route('/execute', methods=['POST'])
def execute_scripts():
    """Processes a file through the selected sequence of plugin functions."""
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
                # The plugin function modifies the lines list
                lines = available_plugins[key](lines)

        with open(target_path, 'w') as f:
            f.writelines(lines)

        return jsonify({"status": "success", "message": "File processed successfully"})

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

def get_plugin_functions():
    """Dynamically loads Python functions from the plugins folder."""
    plugins = {}
    for filename in os.listdir(PLUGIN_DIR):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            path = os.path.join(PLUGIN_DIR, filename)
            
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for name, func in inspect.getmembers(module, inspect.isfunction):
                plugins[f"{module_name}.{name}"] = func
    return plugins

if __name__ == '__main__':
    app.run(debug=True, port=5000)