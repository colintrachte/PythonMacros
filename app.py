from flask import Flask, request, jsonify
from flask_cors import CORS  # Import CORS
import subprocess, os, logging, json

logging.basicConfig(filename='script_execution.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

example_scripts = [
    {'name': 'script1.py', 'description': 'This is script 1', 'filePath': 'add header.py', 'isChecked': True}
]

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/example_scripts', methods=['GET'])
def get_example_scripts():
    return jsonify(example_scripts)

# Endpoint to save configuration name and location
@app.route('/save_config_info', methods=['POST'])
def save_config_info():
    data = request.json
    try:
        with open('config_info.json', 'w') as f:
            json.dump(data, f, indent=4)  # Save configuration info
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

# Endpoint to load configuration name and location
@app.route('/load_config_info', methods=['GET'])
def load_config_info():
    try:
        with open('config_info.json', 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

@app.route('/save', methods=['POST'])
def save_configuration():
    data = request.json
    # Save data to a JSON file
    try:
        with open('configuration.json', 'w') as f:
            json.dump(data, f, indent=4)  # Write data in a pretty JSON format
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

@app.route('/load', methods=['GET'])
def load_configuration():
    try:
        with open('configuration.json', 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

# Endpoint to execute scripts
@app.route('/execute', methods=['POST'])
def execute_scripts():
    scripts = request.json.get('scripts', [])
    results = {}
    if not scripts:
        return jsonify({'error': 'No scripts provided'}), 400

    for script in scripts:
        try:
            result = subprocess.run(['python', script['filePath']], capture_output=True, text=True)
            results[script['name']] = {
                'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip(),
                'exit_code': result.returncode,
            }
            # Log execution result
            #logging.info(f"Executed {script['name']} - Exit Code: {result.returncode}")
        except Exception as e:
            results[script['name']] = {
                'error': str(e),
                'exit_code': -1,
            }
            #logging.error(f"Error executing {script['name']}: {str(e)}")

    return jsonify(results)


if __name__ == '__main__':
    # Make sure to set the directory where your scripts are located
    os.chdir('G:/3D printing/PCB Milling gcode')  # Change this to your scripts directory
    app.run(debug=True)
