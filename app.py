import os
import json
import importlib.util
import inspect
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), 'plugins')
# Default workspace if none is set
DEFAULT_WORKSPACE = os.path.join(os.path.dirname(__file__), 'workspaces')
SESSION_FILE = 'last_session.json'

def initialize_session_file():
    """Creates an empty session file if it doesn't exist."""
    if not os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'w') as f:
            json.dump([], f)  # Initialize with an empty list of steps

initialize_session_file()

def get_workspace():
    if os.path.exists('config_info.json'):
        try:
            with open('config_info.json', 'r') as f:
                data = json.load(f)
                return data.get('workspace', DEFAULT_WORKSPACE)
        except:
            pass
    return DEFAULT_WORKSPACE

@app.route('/save', methods=['POST'])
def save_config():
    scripts = request.json
    with open(SESSION_FILE, 'w') as f:
        json.dump(scripts, f, indent=4)
    return jsonify({"status": "success"})

@app.route('/load', methods=['GET'])
def load_config():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/list_workspaces', methods=['GET'])
def list_workspaces():
    current = get_workspace()
    parent = os.path.dirname(current)
    # Suggest other folders in the same parent directory
    try:
        options = [os.path.join(parent, d) for d in os.listdir(parent) if os.path.isdir(os.path.join(parent, d))]
        return jsonify(options[:10]) # Return top 10 suggestions
    except:
        return jsonify([DEFAULT_WORKSPACE])

def get_plugin_functions():
    """Scans plugins folder and returns a mapping of 'Module.Function': function_object"""
    plugins = {}
    if not os.path.exists(PLUGIN_DIR):
        os.makedirs(PLUGIN_DIR)
        
    for filename in os.listdir(PLUGIN_DIR):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            path = os.path.join(PLUGIN_DIR, filename)
            
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Grab every function defined in that file
            for name, func in inspect.getmembers(module, inspect.isfunction):
                plugins[f"{module_name}.{name}"] = func
    return plugins

@app.route('/list_plugins', methods=['GET'])
def list_plugins():
    return jsonify(list(get_plugin_functions().keys()))

@app.route('/execute', methods=['POST'])
def execute_scripts():
    data = request.json
    target_path = data.get('targetPath')
    filename = data.get('filename')
    scripts = data.get('scripts', [])
    
    # Combine Workspace + Filename
    workspace = get_workspace()
    target_path = os.path.join(workspace, filename)

    try:
        if not os.path.exists(target_path):
            return jsonify({"error": f"File not found: {target_path}"}), 404

        with open(target_path, 'r') as f:
            lines = f.readlines()

        # Load fresh plugins (allows editing plugins without restarting server)
        available_plugins = get_plugin_functions()

        for step in scripts:
            key = step.get('pluginKey')
            if key in available_plugins:
                try:
                    # Execute the plugin function
                    lines = available_plugins[key](lines)
                except Exception as e:
                    # Specific error handling for the PLUGIN logic
                    error_info = traceback.format_exc()
                    return jsonify({
                        "error": f"Plugin '{key}' failed: {str(e)}",
                        "trace": error_info
                    }), 500

        with open(target_path, 'w') as f:
            f.writelines(lines)

        return jsonify({"status": "success", "path_used": target_path, "message": "G-code processed successfully"})

    except Exception as e:
        # General error handling (File IO, permissions, etc)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)