import inspect
from importlib.util import spec_from_file_location, module_from_spec
from tkinter import Tk, filedialog, simpledialog
import os

def load_module_from_file(file_path):
    try:
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = spec_from_file_location(module_name, file_path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"Error loading module from {file_path}: {e}")
        return None

def get_classes_from_module(module):
    try:
        return [name for name, obj in inspect.getmembers(module, inspect.isclass) if obj.__module__ == module.__name__]
    except Exception as e:
        print(f"Error retrieving classes: {e}")
        return []

def get_functions_from_class(cls):
    try:
        # Get all functions defined in the class
        functions = []
        for name, member in inspect.getmembers(cls, inspect.isfunction):
            # Get function signature and docstring
            signature = str(inspect.signature(member))
            docstring = inspect.getdoc(member) or "No description available."
            functions.append({
                "name": name,
                "signature": signature,
                "docstring": docstring
            })
        return functions
    except Exception as e:
        print(f"Error retrieving functions: {e}")
        return []

def main():
    # Open file dialog to select Python file
    Tk().withdraw()  # Hide the root window
    file_path = filedialog.askopenfilename(title="Select a Python file", filetypes=[("Python files", "*.py")])

    if not file_path:
        print("No file selected.")
        return

    module = load_module_from_file(file_path)
    if not module:
        return

    classes = get_classes_from_module(module)
    if not classes:
        print("No classes found in the selected file.")
        return

    # Display checkboxes for user to select classes
    selected_classes = []
    for cls_name in classes:
        user_choice = simpledialog.askstring("Class Selection", f"Include class '{cls_name}'? (yes/no)")
        if user_choice and user_choice.lower() in ["yes", "y"]:
            selected_classes.append(cls_name)

    if not selected_classes:
        print("No classes selected.")
        return

    # Display functions for each selected class
    for cls_name in selected_classes:
        cls = getattr(module, cls_name)
        print(f"Class: {cls_name}")
        functions = get_functions_from_class(cls)
        if functions:
            print("  Functions:")
            for func in functions:
                print(f"    - {func['name']}{func['signature']}")
                print(f"      Description: {func['docstring']}")
        else:
            print("  No functions found or an error occurred.")
        print()

if __name__ == "__main__":
    main()
