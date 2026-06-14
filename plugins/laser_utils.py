"""
laser_utils.py — G-code post-processing plugins for laser cutter operations.

Mix of legacy list[str] -> list[str] functions (auto-wrapped by the loader)
and one new-style Payload function that demonstrates writing to payload.meta.
"""

# Import Payload only for type-annotated functions; the loader needs the
# annotation to distinguish new-style from legacy signatures.
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


def inject_laser_power_on_z_moves(lines):
    """
    Inject laser power commands around Z-height transitions.

    G1 Z0.00 ...  → keep line, then SET_PIN PIN=laser VALUE=0.4  (laser on at engrave depth)
    G0/G1 Z1.00 ...  → SET_PIN PIN=laser VALUE=0 first, then keep the lift move (laser off for travel)
    """
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("G1 Z0.00"):
            result.append(line)
            result.append("SET_PIN PIN=laser VALUE=0.4\n")
        elif stripped.startswith("G0 Z1.00") or stripped.startswith("G1 Z1.00"):
            result.append("SET_PIN PIN=laser VALUE=0\n")
            result.append(line)
        else:
            result.append(line)
    return result

inject_laser_power_on_z_moves.plugin_meta = {
    "label":       "Inject laser power on Z transitions",
    "description": (
        "Turns the laser on (VALUE=0.4) after each G1 Z0.00 descent and "
        "off (VALUE=0) in place of each G0 Z1.00 lift."
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