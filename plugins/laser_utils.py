"""Configurable G-code transformations for laser workflows."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import Payload


PLUGIN_META = {
    "accepts": ["text/plain", "text/x-gcode"],
    "outputs": ["text/plain", "text/x-gcode"],
    "requires": [],
    "external": [],
    "language": "python",
    "tags": ["gcode", "laser"],
}

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_MOTION_PATTERN = re.compile(r"^\s*G0?([0-3])\b", re.IGNORECASE)
_COORD_PATTERN = re.compile(
    rf"(?<![A-Z_])(?P<axis>[XYZ])(?P<value>{_NUMBER})", re.IGNORECASE
)


def _line_ending(line):
    return "\r\n" if line.endswith("\r\n") else "\n"


def _as_line(command, ending="\n"):
    command = str(command).strip()
    return f"{command}{ending}" if command else ""


def _code_part(line):
    return line.split(";", 1)[0]


def _normalize_gcode_word(value):
    return re.sub(r"^(?P<letter>[GM])0+(?=\d)", r"\g<letter>", value.upper())


def _has_command(line, command):
    command = str(command).strip()
    if not command:
        return False
    return (
        re.search(
            rf"(?<!\w){re.escape(command)}(?!\w)", _code_part(line), re.IGNORECASE
        )
        is not None
    )


def _format_number(value, decimal_places=6):
    formatted = f"{value:.{decimal_places}f}".rstrip("0").rstrip(".")
    return "0" if formatted in {"-0", "+0", ""} else formatted


def replace_m_codes(lines: list[str], codes="3|5") -> list[str]:
    """Remove leading zeroes from configurable M-codes, excluding comments."""
    code_values = []
    for value in str(codes).split("|"):
        value = value.strip().upper().removeprefix("M").lstrip("0") or "0"
        if not value.isdigit():
            raise ValueError(f"Invalid M-code value: {value!r}")
        code_values.append(re.escape(value))
    if not code_values:
        return lines

    pattern = re.compile(
        rf"(?<!\w)(M)0*(?:{'|'.join(code_values)})(?!\w)", re.IGNORECASE
    )

    def shorten(match):
        digits = match.group(0)[1:].lstrip("0") or "0"
        return f"{match.group(1)}{digits}"

    result = []
    for line in lines:
        code, separator, comment = line.partition(";")
        result.append(
            pattern.sub(shorten, code) + (separator + comment if separator else "")
        )
    return result


replace_m_codes.plugin_meta = {
    "label": "Normalize selected M-codes",
    "description": "Removes leading zeroes from a configurable pipe-separated list of M-codes.",
}


def remove_flatcam_preamble(
    lines,
    start_command="M106",
    end_command="M107",
    keep_start_command=False,
    keep_end_command=False,
    require_markers=False,
):
    """Keep the content between configurable whole-command markers."""
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if _has_command(line, start_command)
        ),
        None,
    )
    if start is None:
        if require_markers:
            raise ValueError(f"Start command {start_command!r} was not found")
        body_start = 0
    else:
        body_start = start if keep_start_command else start + 1

    end = next(
        (
            index
            for index in range(body_start, len(lines))
            if _has_command(lines[index], end_command)
        ),
        None,
    )
    if end is None:
        if require_markers:
            raise ValueError(f"End command {end_command!r} was not found")
        body_end = len(lines)
    else:
        body_end = end + 1 if keep_end_command else end
    return lines[body_start:body_end]


remove_flatcam_preamble.plugin_meta = {
    "label": "Extract G-code between commands",
    "description": "Keeps content between configurable start and end command markers.",
}


def convert_to_klipper_format(lines, pin_name="laser", power_scale=1.0):
    """Move S words on G1 lines into Klipper SET_PIN commands."""
    result = []
    s_pattern = re.compile(rf"(?<![A-Z])S(?P<value>{_NUMBER})\b", re.IGNORECASE)

    for line in lines:
        code = _code_part(line)
        match = (
            s_pattern.search(code)
            if re.match(r"^\s*G0?1\b", code, re.IGNORECASE)
            else None
        )
        if not match:
            result.append(line)
            continue

        ending = _line_ending(line)
        value = float(match.group("value")) * power_scale
        result.append(f"SET_PIN PIN={pin_name} VALUE={_format_number(value)}{ending}")
        converted = s_pattern.sub("", line, count=1)
        converted = re.sub(r"[ \t]{2,}", " ", converted)
        converted = re.sub(r"[ \t]+(?=\r?$)", "", converted)
        result.append(converted)
    return result


convert_to_klipper_format.plugin_meta = {
    "label": "Convert S words to Klipper SET_PIN",
    "description": "Extracts only the S word and preserves every other move parameter and comment.",
}


def add_laser_header_footer(
    lines,
    home_command="HOME_PRINTER",
    tool_command="GRAB_LASER",
    shutdown_command="M5",
    finish_home_command="HOME_XY",
    release_command="TOOL_DROPOFF",
):
    """Wrap G-code with configurable setup and safe-shutdown commands."""
    header = [
        _as_line(command)
        for command in (home_command, tool_command)
        if str(command).strip()
    ]
    footer = [
        _as_line(command)
        for command in (shutdown_command, finish_home_command, release_command)
        if str(command).strip()
    ]
    return header + lines + footer


add_laser_header_footer.plugin_meta = {
    "label": "Add laser header and footer",
    "description": "Adds configurable setup, shutdown, homing, and tool-release commands.",
}


def inject_laser_power_on_z_moves(
    lines,
    power=0.4,
    engrave_z=0.0,
    travel_z=1.0,
    pin_name="laser",
    tolerance=0.0001,
    engrave_motion_codes="G1",
    travel_motion_codes="G0|G1",
):
    """Switch laser power around configurable Z-height transitions."""
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    if power < 0:
        raise ValueError("power must be non-negative")
    if abs(engrave_z - travel_z) <= tolerance:
        raise ValueError("engrave_z and travel_z must differ by more than tolerance")
    engrave_codes = {
        _normalize_gcode_word(code.strip())
        for code in str(engrave_motion_codes).split("|")
        if code.strip()
    }
    travel_codes = {
        _normalize_gcode_word(code.strip())
        for code in str(travel_motion_codes).split("|")
        if code.strip()
    }
    z_pattern = re.compile(rf"(?<![A-Z])Z(?P<value>{_NUMBER})\b", re.IGNORECASE)
    result = []

    for line in lines:
        code = _code_part(line)
        motion = re.match(r"^\s*G0?(?P<kind>[01])\b", code, re.IGNORECASE)
        z_match = z_pattern.search(code)
        if not motion or not z_match:
            result.append(line)
            continue

        motion_code = f"G{motion.group('kind')}"
        z_value = float(z_match.group("value"))
        ending = _line_ending(line)
        if motion_code in engrave_codes and abs(z_value - engrave_z) <= tolerance:
            result.append(line)
            result.append(
                f"SET_PIN PIN={pin_name} VALUE={_format_number(power)}{ending}"
            )
        elif motion_code in travel_codes and abs(z_value - travel_z) <= tolerance:
            result.append(f"SET_PIN PIN={pin_name} VALUE=0{ending}")
            result.append(line)
        else:
            result.append(line)
    return result


inject_laser_power_on_z_moves.plugin_meta = {
    "label": "Switch laser power on Z transitions",
    "description": "Uses configurable heights, motion types, tolerance, pin name, and power.",
}


def count_laser_on_segments(payload: "Payload", pin_name="laser") -> "Payload":
    """Count positive SET_PIN values for a configurable pin."""
    pattern = re.compile(
        rf"\bSET_PIN\s+PIN={re.escape(pin_name)}\s+VALUE=(?P<value>{_NUMBER})\b",
        re.IGNORECASE,
    )
    count = 0
    for line in payload.data:
        match = pattern.search(_code_part(line))
        if match and float(match.group("value")) > 0:
            count += 1
    payload.meta["laser_segment_count"] = count
    payload.data = payload.data + [f"; laser segments fired: {count}\n"]
    return payload


count_laser_on_segments.plugin_meta = {
    "label": "Count laser-on segments",
    "description": "Counts positive SET_PIN values for a configurable pin and records the result.",
}


def _shift_body(body, dx=0.0, dy=0.0, dz=0.0, decimal_places=3):
    if dx == 0 and dy == 0 and dz == 0:
        return list(body)

    offsets = {"X": dx, "Y": dy, "Z": dz}
    shifted = []
    for line in body:
        code, separator, comment = line.partition(";")
        if _MOTION_PATTERN.match(code):

            def replace_coordinate(match):
                axis = match.group("axis")
                value = float(match.group("value")) + offsets[axis.upper()]
                return f"{axis}{_format_number(value, decimal_places)}"

            code = _COORD_PATTERN.sub(replace_coordinate, code)
        shifted.append(code + (separator + comment if separator else ""))
    return shifted


def offset_gcode(lines, dx=0.0, dy=0.0, dz=0.0, decimal_places=3):
    """Offset motion coordinates without touching comments or non-motion commands."""
    return _shift_body(lines, dx, dy, dz, decimal_places)


offset_gcode.plugin_meta = {
    "label": "Offset G-code coordinates",
    "description": "Offsets X, Y, and Z on G0-G3 moves with configurable precision.",
}


def _apply_settings(body, speed=None, power=None, pin_name="laser"):
    feed_pattern = re.compile(rf"(?<![A-Z])F{_NUMBER}\b", re.IGNORECASE)
    power_pattern = re.compile(
        rf"(\bSET_PIN\s+PIN={re.escape(pin_name)}\s+VALUE=)(?P<value>{_NUMBER})\b",
        re.IGNORECASE,
    )
    result = []
    for line in body:
        code = _code_part(line)
        if speed is not None and re.match(r"^\s*G0?1\b", code, re.IGNORECASE):
            line = feed_pattern.sub(f"F{_format_number(speed)}", line)
        if power is not None:

            def replace_power(match):
                if float(match.group("value")) <= 0:
                    return match.group(0)
                return f"{match.group(1)}{_format_number(power)}"

            line = power_pattern.sub(replace_power, line)
        result.append(line)
    return result


def _range_list(minimum, maximum, step, label):
    provided = [value for value in (minimum, maximum, step) if value is not None]
    if not provided:
        return None
    if len(provided) != 3:
        raise ValueError(f"{label}: set min, max, and step together")
    if step <= 0 or minimum > maximum:
        raise ValueError(f"{label}: require step > 0 and min <= max")
    count = int((maximum - minimum) / step + 1e-9) + 1
    if count > 10000:
        raise ValueError(f"{label}: range produces too many values")
    return [minimum + index * step for index in range(count)]


def make_laser_grid(
    lines,
    pcb_width=80.0,
    pcb_height=100.0,
    gap=2.0,
    max_copies=0,
    skip_first_n=0,
    speed_min=None,
    speed_max=None,
    speed_step=None,
    power_min=None,
    power_max=None,
    power_step=None,
    header_end_command="GRAB_LASER",
    footer_start_command="M5",
    pin_name="laser",
    decimal_places=3,
    max_generated_tiles=10000,
):
    """Tile a detected motion body across a configurable work area."""
    if gap < 0:
        raise ValueError("gap must be non-negative")
    if max_copies < 0 or skip_first_n < 0:
        raise ValueError("max_copies and skip_first_n must be non-negative")
    if max_generated_tiles <= 0:
        raise ValueError("max_generated_tiles must be positive")

    speeds = _range_list(speed_min, speed_max, speed_step, "speed")
    powers = _range_list(power_min, power_max, power_step, "power")
    if powers is not None and any(power < 0 for power in powers):
        raise ValueError("power range values must be non-negative")

    header_match = next(
        (
            index
            for index, line in enumerate(lines)
            if _has_command(line, header_end_command)
        ),
        None,
    )
    header_end = header_match + 1 if header_match is not None else 0
    footer_matches = [
        index
        for index in range(header_end, len(lines))
        if _has_command(lines[index], footer_start_command)
    ]
    footer_start = footer_matches[-1] if footer_matches else len(lines)

    header = lines[:header_end]
    body = lines[header_end:footer_start]
    footer = lines[footer_start:]

    x_values = []
    y_values = []
    for line in body:
        code = _code_part(line)
        if not _MOTION_PATTERN.match(code):
            continue
        for match in _COORD_PATTERN.finditer(code):
            if match.group("axis").upper() == "X":
                x_values.append(float(match.group("value")))
            elif match.group("axis").upper() == "Y":
                y_values.append(float(match.group("value")))

    if not x_values or not y_values:
        return lines

    art_width = max(x_values) - min(x_values)
    art_height = max(y_values) - min(y_values)
    pitch_x = art_width + gap
    pitch_y = art_height + gap
    if pitch_x <= 0 or pitch_y <= 0:
        raise ValueError("Artwork size plus gap must be positive on both axes")

    direction_x = -1.0 if pcb_width < 0 else 1.0
    direction_y = -1.0 if pcb_height < 0 else 1.0
    columns = (
        len(speeds) if speeds is not None else max(1, int(abs(pcb_width) / pitch_x))
    )
    rows = len(powers) if powers is not None else max(1, int(abs(pcb_height) / pitch_y))
    requested_tiles = columns * rows
    effective_tiles = (
        min(requested_tiles, max_copies) if max_copies > 0 else requested_tiles
    )
    if effective_tiles > max_generated_tiles:
        raise ValueError(
            f"Grid would produce {effective_tiles} tiles; limit is {max_generated_tiles}"
        )

    tiled_body = []
    generated = 0
    produced = 0
    for row in range(rows):
        for column in range(columns):
            if max_copies > 0 and produced >= max_copies:
                break
            if generated < skip_first_n:
                generated += 1
                continue

            tile = _shift_body(
                body,
                column * pitch_x * direction_x,
                row * pitch_y * direction_y,
                decimal_places,
            )
            tile = _apply_settings(
                tile,
                speed=speeds[column] if speeds is not None else None,
                power=powers[row] if powers is not None else None,
                pin_name=pin_name,
            )
            tiled_body.extend(tile)
            generated += 1
            produced += 1
        if max_copies > 0 and produced >= max_copies:
            break

    return header + tiled_body + footer


make_laser_grid.plugin_meta = {
    "label": "Tile G-code across a work area",
    "description": (
        "Tiles a detected G-code body while preserving configurable wrappers. "
        "Work-area direction, copies, offsets, speed tests, and power tests are configurable."
    ),
}
