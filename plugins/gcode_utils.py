# plugins/gcode_utils.py

def add_printer_header(lines):
    """Adds standard home and grab commands to the start of the file."""
    header = ["G28 ; Home all axes\n", "M06 T1 ; Grab endmill\n"]
    return header + lines

def remove_comments(lines):
    """Removes any line starting with a semicolon."""
    return [line for line in lines if not line.strip().startswith(';')]