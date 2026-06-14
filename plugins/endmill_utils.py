"""
endmill_utils.py — G-code post-processing plugins for CNC endmill operations.

All functions use the legacy list[str] -> list[str] signature and are
automatically wrapped by the plugin loader into the Payload contract.
Functions that need to read or write payload.meta should use the new
Payload signature instead (see laser_utils.py for an example).
"""

import re

# ── Module-level metadata (applies to all functions unless overridden) ─────

PLUGIN_META = {
    "accepts":  ["text/plain", "text/x-gcode"],
    "outputs":  ["text/plain", "text/x-gcode"],
    "requires": [],
    "external": [],
    "language": "python",
    "tags":     ["gcode", "endmill"],
}

# ── Plugins ────────────────────────────────────────────────────────────────

def add_printer_header(lines):
    """Prepend G28 home-all and GRAB_ENDMILL tool-grab commands to the file."""
    header = [
        "G28 ; Home all axes\n",
        "GRAB_ENDMILL\n",
    ]
    return header + lines

add_printer_header.plugin_meta = {
    "label":       "Add printer header",
    "description": "Prepends G28 home-all and GRAB_ENDMILL to the start of the file.",
}


def remove_comments(lines):
    """Strip all full-line G-code comments (lines starting with ';')."""
    return [line for line in lines if not line.strip().startswith(';')]

remove_comments.plugin_meta = {
    "label":       "Remove full-line comments",
    "description": "Deletes any line whose first non-whitespace character is ';'.",
}


def convert_g01_g00_to_g1_2decimals(lines):
    """Normalise G00/G01 to G1 and round all axis coordinates to 2 decimal places."""
    new_lines = []
    for line in lines:
        line = re.sub(r'\bG0[01]\b', 'G1', line)
        line = re.sub(
            r'([A-Z])(-?\d+\.\d+)',
            lambda m: f"{m.group(1)}{float(m.group(2)):.2f}",
            line,
        )
        new_lines.append(line)
    return new_lines

convert_g01_g00_to_g1_2decimals.plugin_meta = {
    "label":       "Normalise G00/G01 → G1 + 2 dp",
    "description": (
        "Replaces G00 and G01 with G1, then rounds every axis value "
        "(X, Y, Z, E, etc.) to 2 decimal places."
    ),
}


def remove_before_first_M03(lines):
    """
    Remove all lines before the first M03 (spindle-on) command.

    Previously misnamed 'remove_before_M106'; renamed to match actual behaviour.
    """
    start = next((i for i, line in enumerate(lines) if 'M03' in line), -1)
    return lines[start + 1:] if start != -1 else lines

remove_before_first_M03.plugin_meta = {
    "label":       "Remove preamble before M03",
    "description": "Discards everything before the first M03 (spindle-on) command.",
}


def insert_endmill_power_before_first_z_move(lines):
    """
    Insert SET_PIN PIN=end_mill VALUE=250 immediately before the first G1 Z move.

    Rebuilds the list rather than mutating in-place during iteration.
    """
    result = []
    inserted = False
    for line in lines:
        if not inserted and line.startswith('G1 Z'):
            result.append('SET_PIN PIN=end_mill VALUE=250\n')
            inserted = True
        result.append(line)
    return result

insert_endmill_power_before_first_z_move.plugin_meta = {
    "label":       "Insert endmill power before first Z move",
    "description": "Injects SET_PIN PIN=end_mill VALUE=250 just before the first G1 Z descent.",
}


def remove_after_M107(lines):
    """Truncate the file at the first M107 (fan-off / spindle-off) command."""
    idx = next((i for i, line in enumerate(lines) if 'M107' in line), len(lines))
    return lines[:idx]

remove_after_M107.plugin_meta = {
    "label":       "Remove content after M107",
    "description": "Keeps only the lines up to (not including) the first M107 command.",
}


def add_footer(lines):
    """Append endmill shutdown, XY home, and tool drop-off commands."""
    footer = [
        'SET_PIN PIN=end_mill VALUE=0\n',
        'HOME_XY\n',
        'TOOL_DROPOFF\n',
    ]
    return lines + footer

add_footer.plugin_meta = {
    "label":       "Add endmill footer",
    "description": "Appends SET_PIN VALUE=0, HOME_XY, and TOOL_DROPOFF to the end of the file.",
}