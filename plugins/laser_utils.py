"""
laser_utils.py — G-code post-processing plugins for laser cutter operations.

Mix of legacy list[str] -> list[str] functions (auto-wrapped by the loader)
and one new-style Payload function that demonstrates writing to payload.meta.
"""

import re
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app import Payload   # pragma: no cover

# ── Module-level metadata ──────────────────────────────────────────────────

PLUGIN_META = {
    "accepts":  ["text/plain", "text/x-gcode"],
    "outputs":  ["text/plain", "text/x-gcode"],
    "requires": [],
    "external": [],
    "language": "python",
    "tags":     ["gcode", "laser"],
}

# ── Plugins ────────────────────────────────────────────────────────────────

def remove_flatcam_preamble(lines):
    """
    Strip the FlatCAM Repetier preamble and trailing shutdown from laser gcode.

    Removes everything up to and including the first M106 (Repetier spindle-on),
    and truncates at the first M107 (Repetier spindle-off) so only the toolpath
    remains. The laser header/footer plugin adds the correct Klipper commands.
    """
    start = next((i for i, l in enumerate(lines) if l.strip() == 'M106'), -1)
    lines = lines[start + 1:] if start != -1 else lines
    end = next((i for i, l in enumerate(lines) if l.strip() == 'M107'), len(lines))
    return lines[:end]

remove_flatcam_preamble.plugin_meta = {
    "label":       "Remove FlatCAM preamble / trailer",
    "description": "Strips everything before M106 (spindle-on) and after M107 (spindle-off), leaving only the laser toolpath.",
}


def convert_to_klipper_format(lines):
    """
    Convert legacy laser G-code (G1 with S spindle values) to Klipper
    SET_PIN PIN=laser format.
    """
    result = []
    for line in lines:
        line = line.strip()
        if line.startswith("G1") and "S" in line:
            parts = line.split()
            x_val = next((p[1:] for p in parts if p.startswith("X")), None)
            y_val = next((p[1:] for p in parts if p.startswith("Y")), None)
            s_val = next((p[1:] for p in parts if p.startswith("S")), None)
            f_val = next((p[1:] for p in parts if p.startswith("F")), None)

            if s_val is not None:
                result.append(f"SET_PIN PIN=laser VALUE={s_val}\n")
            if x_val and y_val and f_val:
                result.append(f"G1 X{x_val} Y{y_val} F{f_val}\n")
        else:
            result.append(line + '\n')
    return result

convert_to_klipper_format.plugin_meta = {
    "label":       "Convert S-value G-code → Klipper SET_PIN",
    "description": (
        "Rewrites G1 moves that carry an S (spindle/power) parameter into "
        "separate SET_PIN PIN=laser VALUE=… and G1 X… Y… F… lines."
    ),
}


def add_laser_header_footer(lines):
    """Wrap the file with laser homing, tool pickup, power-off, and drop-off."""
    header = ['HOME_PRINTER\n', 'GRAB_LASER\n']
    footer = ['SET_PIN PIN=laser VALUE=0\n', 'HOME_XY\n', 'TOOL_DROPOFF\n']
    return header + lines + footer

add_laser_header_footer.plugin_meta = {
    "label":       "Add laser header + footer",
    "description": "Prepends HOME_PRINTER / GRAB_LASER and appends power-off / HOME_XY / TOOL_DROPOFF.",
}


def inject_laser_power_on_z_moves(lines, power=0.4, engrave_z=0.0, travel_z=1.0):
    """
    Inject laser power commands around Z-height transitions.

    G1 Z<engrave_z> → keep line, then SET_PIN PIN=laser VALUE=<power>
    G0/G1 Z<travel_z> → SET_PIN PIN=laser VALUE=0 first, then keep the lift move
    """
    ez = f"Z{engrave_z:.2f}"
    tz = f"Z{travel_z:.2f}"
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"G1 {ez}"):
            result.append(line)
            result.append(f"SET_PIN PIN=laser VALUE={power}\n")
        elif stripped.startswith(f"G0 {tz}") or stripped.startswith(f"G1 {tz}"):
            result.append("SET_PIN PIN=laser VALUE=0\n")
            result.append(line)
        else:
            result.append(line)
    return result

inject_laser_power_on_z_moves.plugin_meta = {
    "label":       "Inject laser power on Z transitions",
    "description": (
        "Turns the laser on after each engrave-depth descent and "
        "off before each travel lift."
    ),
}


# ── New-style Payload example ──────────────────────────────────────────────
# This function uses the full Payload signature to read and write metadata
# alongside the file content.  The loader detects the Payload annotation and
# does NOT wrap it.

def count_laser_on_segments(payload: "Payload") -> "Payload":
    """
    Count how many times the laser fires (SET_PIN PIN=laser VALUE>0) and store
    the result in payload.meta["laser_segment_count"] for downstream steps or
    for display in the console log.
    """
    count = sum(
        1 for line in payload.data
        if "SET_PIN PIN=laser VALUE=" in line
        and not line.strip().endswith("VALUE=0")
    )
    payload.meta["laser_segment_count"] = count
    # Append a comment to the file so the count is visible in the output
    payload.data = payload.data + [f"; laser segments fired: {count}\n"]
    return payload

count_laser_on_segments.plugin_meta = {
    "label":       "Count laser-on segments",
    "description": (
        "Counts SET_PIN laser VALUE>0 occurrences, stores the result in "
        "payload.meta['laser_segment_count'], and appends it as a comment."
    ),
}


# ── Grid tiling ────────────────────────────────────────────────────────────

def _shift_body(body, dx, dy):
    """Shift every G0/G1 X and Y coordinate in a body block by (dx, dy)."""
    shifted = []
    for line in body:
        s = line.strip()
        if s.startswith('G0') or s.startswith('G1'):
            def replace_coord(m, _dx=dx, _dy=dy):
                axis = m.group(1)
                return f'{axis}{float(m.group(2)) + (_dx if axis == "X" else _dy):.2f}'
            line = re.sub(r'([XY])(-?\d+(?:\.\d+)?)', replace_coord, line)
        shifted.append(line)
    return shifted


def make_laser_grid(lines, pcb_width=80.0, pcb_height=100.0, gap=2.0, max_copies=0, skip_first_n=0):
    """
    Tile the laser artwork in a grid to fill the PCB and bake shifted coordinates
    into one file.

    Run this step AFTER add_laser_header_footer and inject_laser_power_on_z_moves.
    Auto-detects artwork extents from G0/G1 X/Y values in the body, computes
    cols = floor(abs(pcb_width) / (art_width + gap)) and the same for rows.
    The sign of pcb_width/pcb_height controls the tiling direction (negative = tile
    Toward lower coordinates).
    max_copies: if > 0, caps the total number of tiles produced (0 = unlimited).
    skip_first_n: skips the first N generated duplicate positions in the grid layout.
    """
    # Locate header end (line after GRAB_LASER)
    header_end = 0
    for i, line in enumerate(lines):
        if line.strip() == 'GRAB_LASER':
            header_end = i + 1
            break

    # Footer is always the last 3 fixed lines added by add_laser_header_footer
    if (len(lines) >= 3
            and lines[-1].strip() == 'TOOL_DROPOFF'
            and lines[-2].strip() == 'HOME_XY'
            and lines[-3].strip() == 'SET_PIN PIN=laser VALUE=0'):
        footer_start = len(lines) - 3
    else:
        footer_start = len(lines)

    header = lines[:header_end]
    body   = lines[header_end:footer_start]
    footer = lines[footer_start:]

    # Auto-detect artwork extents
    x_vals, y_vals = [], []
    for line in body:
        s = line.strip()
        if s.startswith('G0') or s.startswith('G1'):
            for m in re.finditer(r'X(-?\d+(?:\.\d+)?)', s):
                x_vals.append(float(m.group(1)))
            for m in re.finditer(r'Y(-?\d+(?:\.\d+)?)', s):
                y_vals.append(float(m.group(1)))

    if not x_vals or not y_vals:
        return lines

    art_w = max(x_vals) - min(x_vals)
    art_h = max(y_vals) - min(y_vals)

    # Use abs() for count, sign for direction
    dir_x = -1.0 if pcb_width < 0 else 1.0
    dir_y = -1.0 if pcb_height < 0 else 1.0
    cols = max(1, int(abs(pcb_width)  / (art_w + gap)))
    rows = max(1, int(abs(pcb_height) / (art_h + gap)))

    new_body = []
    generated_count = 0
    produced_count = 0

    for row in range(rows):
        for col in range(cols):
            # Check maximum copies limit based on actually produced tiles
            if max_copies > 0 and produced_count >= max_copies:
                break

            # Handle skipping the first N layout positions
            if generated_count < skip_first_n:
                generated_count += 1
                continue

            dx = col * (art_w + gap) * dir_x
            dy = row * (art_h + gap) * dir_y
            
            new_body.extend(body if (dx == 0.0 and dy == 0.0) else _shift_body(body, dx, dy))
            
            generated_count += 1
            produced_count += 1
            
        if max_copies > 0 and produced_count >= max_copies:
            break

    return header + new_body + footer

make_laser_grid.plugin_meta = {
    "label":       "Tile grid — fill PCB",
    "description": (
        "Duplicates the laser body in a grid that fills the PCB. "
        "Negative pcb_width/pcb_height tiles toward lower coordinates. "
        "max_copies caps total tiles (0 = unlimited). "
        "skip_first_n skips the first N duplicate grid spaces. "
        "Coordinates are baked in; no Klipper macro changes needed. "
        "Run after 'Add laser header + footer' and 'Inject laser power on Z transitions'."
    ),
}