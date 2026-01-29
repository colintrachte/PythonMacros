import re

def add_printer_header(lines):
    header = ["G28 ; Home all axes\n", "M06 T1 ; Grab endmill\n"]
    return header + lines

def remove_comments(lines):
    return [line for line in lines if not line.strip().startswith(';')]

def convert_g01_g00_2decimals(lines):
    """Convert G00/G01 to G1 and round all coordinates to 2 decimal places."""
    new_lines = []
    for line in lines:
        # Replace G00 and G01 with G1
        modified_line = re.sub(r'\bG0[01]\b', 'G1', line)
        # Round decimals: Match Letter followed by a float (e.g., X10.1234 -> X10.12)
        modified_line = re.sub(
            r'([A-Z])(-?\d+\.\d+)', 
            lambda m: f"{m.group(1)}{float(m.group(2)):.2f}", 
            modified_line
        )
        new_lines.append(modified_line)
    return new_lines

def remove_before_M106(lines):
    """Remove all lines occurring before the first M03 command."""
    start_index = next((i for i, line in enumerate(lines) if 'M03' in line), -1)
    return lines[start_index + 1:] if start_index != -1 else lines

def insert_before_first_g1z(lines):
    """Insert the end-mill power command before the first vertical move."""
    for i, line in enumerate(lines):
        if line.startswith('G1 Z'):
            lines.insert(i, 'SET_PIN PIN=end_mill VALUE=250\n')
            break
    return lines

def remove_after_m107(lines):
    """Truncate the file after the first M107 command."""
    idx = next((i for i, line in enumerate(lines) if 'M107' in line), len(lines))
    return lines[:idx]

def add_footer(lines):
    """Append end-mill shutdown and tool dropoff."""
    footer = ['SET_PIN PIN=end_mill VALUE=0\n', 'HOME_XY\n', 'TOOL_DROPOFF\n']
    return lines + footer

# --- Laser Specific Plugins ---

def convert_to_klipper_format(lines):
    """Convert legacy laser G-code to Klipper SET_PIN format."""
    converted_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("G1") and "S" in line:
            parts = line.split()
            x_val = next((p[1:] for p in parts if p.startswith("X")), None)
            y_val = next((p[1:] for p in parts if p.startswith("Y")), None)
            s_val = next((p[1:] for p in parts if p.startswith("S")), None)
            f_val = next((p[1:] for p in parts if p.startswith("F")), None)

            if s_val is not None:
                converted_lines.append(f"SET_PIN PIN=laser VALUE={s_val}\n")
            if x_val and y_val and f_val:
                converted_lines.append(f"G1 X{x_val} Y{y_val} F{f_val}\n")
        else:
            converted_lines.append(line + '\n')
    return converted_lines

def add_laser_header_footer(lines):
    """Add laser homing and pickup sequence."""
    header = ['HOME_PRINTER\n', 'GRAB_LASER\n']
    footer = ['SET_PIN PIN=laser VALUE=0\n', 'HOME_XY\n', 'TOOL_DROPOFF\n']
    return header + lines + footer

def modify_laser_gcode(lines):
    """Inject laser power triggers based on Z-height moves."""
    modified_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped == "G1 Z0.00":
            modified_lines.append(line)
            modified_lines.append("SET_PIN PIN=laser VALUE=0.4\n")
        elif stripped == "G0 Z1.00":
            modified_lines.append("SET_PIN PIN=laser VALUE=0\n")
        else:
            modified_lines.append(line)
    return modified_lines