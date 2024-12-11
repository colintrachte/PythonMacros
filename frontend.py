import os, logging
import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, Scrollbar, simpledialog, Toplevel, Label
import importlib.util
import inspect

class GCodeProcessor:
    def __init__(self):
        self.steps = []  # Store all steps as {description, function, enabled}

    def add_step(self, description, function):
        """Add a new step."""
        self.steps.append({"description": description, "function": function, "enabled": True})

    def remove_step(self, index):
        if 0 <= index < len(self.steps):
            self.steps.pop(index)

    def toggle_step(self, index):
        if 0 <= index < len(self.steps):
            self.steps[index]["enabled"] = not self.steps[index]["enabled"]

    def reorder_steps(self, old_index, new_index):
        if 0 <= old_index < len(self.steps) and 0 <= new_index < len(self.steps):
            step = self.steps.pop(old_index)
            self.steps.insert(new_index, step)

    def execute(self, file_path):
        """Run enabled steps on the G-code file."""
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()

            for step in self.steps:
                if step["enabled"]:
                    lines = step["function"](lines)

            with open(file_path, 'w') as f:
                f.writelines(lines)

            messagebox.showinfo("Success", f"Processed '{os.path.basename(file_path)}' successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process file: {e}")

    def save_steps(self, filename):
        """Save steps to a Python file."""
        try:
            with open(filename, 'w') as f:
                f.write("def get_steps():\n    steps = []\n")
                for step in self.steps:
                    desc = step["description"]
                    func_source = self.get_function_source(step["function"])
                    f.write(f"    # {desc}\n")
                    f.write(f"    steps.append(({repr(desc)}, {func_source}))\n\n")
                f.write("    return steps\n")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save steps: {e}")

    def get_function_source(self, func):
        """Get function source code."""
        source_lines = inspect.getsource(func).splitlines()
        return f"lambda lines: {''.join(source_lines).strip()}"

    def load_steps(self, filename):
        """Load steps from a Python file."""
        try:
            spec = importlib.util.spec_from_file_location("loaded_steps", filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded_steps = module.get_steps()
            self.steps = [{"description": desc, "function": func, "enabled": True} for desc, func in loaded_steps]
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load steps: {e}")

# Helper Functions

def remove_before_M106(lines):
    """Remove lines up to the first M106."""
    start_index = next((i for i, line in enumerate(lines) if 'M106' in line), -1)
    return lines[start_index + 1:] if start_index != -1 else lines

def add_header(lines):
    """Add a header."""
    header = ['HOME_PRINTER\n', 'GRAB_ENDMILL\n']
    return header + lines

def insert_before_first_g1z(lines):
    """Insert a line before the first 'G1 Z'."""
    for i, line in enumerate(lines):
        if line.startswith('G1 Z'):
            lines.insert(i, 'SET_PIN PIN=end_mill VALUE=250\n')
            break
    return lines

def remove_after_m107(lines):
    """Remove all lines after the first 'M107'."""
    return lines[:next((i for i, line in enumerate(lines) if 'M107' in line), len(lines))]

def add_footer(lines):
    """Add a footer."""
    footer = ['SET_PIN PIN=end_mill VALUE=0\n', 'HOME_XY\n', 'TOOL_DROPOFF\n']
    return lines + footer

def convert_to_klipper_format(lines):
    """Convert G-code to Klipper-compatible format."""
    converted_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("G1") and "S" in line:
            parts = line.split()
            x_val, y_val, s_val, f_val = None, None, None, None

            for part in parts:
                if part.startswith("X"):
                    x_val = part[1:]
                elif part.startswith("Y"):
                    y_val = part[1:]
                elif part.startswith("S"):
                    s_val = part[1:]
                elif part.startswith("F"):
                    f_val = part[1:]

            if s_val is not None:
                converted_lines.append(f"SET_PIN PIN=laser VALUE={s_val}\n")
            if x_val is not None and y_val is not None and f_val is not None:
                converted_lines.append(f"G1 X{x_val} Y{y_val} F{f_val}\n")
        else:
            converted_lines.append(line + '\n')
    return converted_lines

def add_laser_header_footer(lines):
    """
    Add laser-specific header and footer to the G-code file.
    """
    header = ['HOME_PRINTER\n', 'GRAB_LASER\n']
    footer = ['SET_PIN PIN=laser VALUE=0\n', 'HOME_XY\n', 'TOOL_DROPOFF\n']
    return header + lines + footer

def modify_laser_gcode(lines):
    """
    Modify G-code to add or replace commands related to laser control.
    - After any line with `G01 Z0.0000`, add `SET_PIN PIN=laser VALUE=0.1`.
    - Replace any line with `G01 Z10.0000` with `SET_PIN PIN=laser VALUE=0.01`.
    """
    modified_lines = []
    for line in lines:
        # Add command after `G01 Z0.0000`
        if line.strip() == "G01 Z0.0000":
            modified_lines.append(line)
            modified_lines.append("SET_PIN PIN=laser VALUE=0.1\n")
        # Replace `G01 Z10.0000`
        elif line.strip() == "G01 Z10.0000":
            modified_lines.append("SET_PIN PIN=laser VALUE=0.01\n")
        else:
            modified_lines.append(line)
    return modified_lines

# GUI Setup

class GCodeEditorGUI:
    def __init__(self, root, processor):
        self.root = root
        self.processor = processor

        self.frame = tk.Frame(root)
        self.frame.pack(padx=10, pady=10)

        self.listbox = Listbox(self.frame, width=50, height=10)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = Scrollbar(self.frame, command=self.listbox.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=self.scrollbar.set)

        self.load_default_steps()

        # Buttons
        button_frame = tk.Frame(root)
        button_frame.pack(pady=10)

        buttons = [
            ("Add Step", self.add_step),
            ("Remove Step", self.remove_step),
            ("Toggle Step", self.toggle_step),
            ("Reorder Step", self.reorder_step),
            ("Process File", self.process_file),
            ("Save Steps", self.save_steps),
            ("Load Steps", self.load_steps),
        ]

        for i, (text, command) in enumerate(buttons):
            tk.Button(button_frame, text=text, command=command).grid(row=i // 4, column=i % 4, padx=5, pady=5)

    def load_default_steps(self):
        """Load default steps."""

        # Use default steps if no saved configuration is found
        default_steps = [
            ("Remove Old Header", remove_before_M106),
            ("Add Header", add_header),
            ("Insert Before G1 Z", insert_before_first_g1z),
            ("Remove After M107", remove_after_m107),
            ("Add Footer", add_footer),
            ("Add Laser Header and Footer", add_laser_header_footer),
            ("Modify Laser G-code", modify_laser_gcode),
        ]
        for desc, func in default_steps:
            self.processor.add_step(desc, func)
        self.refresh_listbox()

    def refresh_listbox(self):
        """Update the listbox."""
        self.listbox.delete(0, tk.END)
        for i, step in enumerate(self.processor.steps):
            status = "Enabled" if step["enabled"] else "Disabled"
            self.listbox.insert(tk.END, f"{i + 1}. {step['description']} [{status}]")

    def add_step(self):
        """Add a new step."""
        description = simpledialog.askstring("Add Step", "Enter step description:")
        if description:
            self.processor.add_step(description, lambda lines: lines)
            self.refresh_listbox()

    def remove_step(self):
        """Remove the selected step."""
        selected = self.listbox.curselection()
        if selected:
            self.processor.remove_step(selected[0])
            self.refresh_listbox()

    def toggle_step(self):
        """Toggle step enabled/disabled."""
        selected = self.listbox.curselection()
        if selected:
            self.processor.toggle_step(selected[0])
            self.refresh_listbox()

    def reorder_step(self):
        """Reorder a step."""
        old_index = self.listbox.curselection()
        if old_index:
            new_index = simpledialog.askinteger("Reorder Step", "Enter new position:") - 1
            if new_index is not None:
                self.processor.reorder_steps(old_index[0], new_index)
                self.refresh_listbox()

    def process_file(self):
        """Select and process a G-code file."""
        file_path = filedialog.askopenfilename(filetypes=[("G-code Files", "*.gcode")])
        if file_path:
            self.processor.execute(file_path)

    def save_steps(self):
        """Save steps to a file."""
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        #if filename:
            #self.processor.save_steps(filename)

    def load_steps(self):
        """Load steps from a file."""
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        #if filename:
            #self.processor.load_steps(filename)

# Main

if __name__ == "__main__":
    root = tk.Tk()
    root.title("G-code Editor")
    processor = GCodeProcessor()
    app = GCodeEditorGUI(root, processor)
    root.mainloop()
