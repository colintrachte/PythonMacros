"""Configurable G-code transformations for CNC endmill workflows."""

import re


PLUGIN_META = {
    "accepts": ["text/plain", "text/x-gcode"],
    "outputs": ["text/plain", "text/x-gcode"],
    "requires": [],
    "external": [],
    "language": "python",
    "tags": ["gcode", "endmill"],
}

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_MOTION_PATTERN = re.compile(r"^(?P<indent>\s*)G0?(?P<kind>[01])\b", re.IGNORECASE)
_WORD_PATTERN = re.compile(
    rf"(?<![A-Z_])(?P<letter>[A-FH-LP-SU-Z])(?P<value>{_NUMBER})",
    re.IGNORECASE,
)


def _line_ending(line):
    return "\r\n" if line.endswith("\r\n") else "\n"


def _as_line(command, ending="\n"):
    command = str(command).strip()
    return f"{command}{ending}" if command else ""


def _commands(value):
    return [command.strip() for command in str(value).split("|") if command.strip()]


def _normalize_gcode_word(value):
    return re.sub(r"^(?P<letter>[GM])0+(?=\d)", r"\g<letter>", value.upper())


def _code_part(line):
    return line.split(";", 1)[0]


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


def add_printer_header(
    lines,
    home_command="HOME_PRINTER ; Home all axes",
    tool_command="GRAB_ENDMILL",
):
    """Prepend configurable homing and tool-selection commands."""
    header = [
        _as_line(command)
        for command in (home_command, tool_command)
        if str(command).strip()
    ]
    return header + lines


add_printer_header.plugin_meta = {
    "label": "Add endmill header",
    "description": "Prepends configurable homing and tool-selection commands.",
}


def remove_comments(lines):
    """Strip full-line semicolon comments without changing inline comments."""
    return [line for line in lines if not line.lstrip().startswith(";")]


remove_comments.plugin_meta = {
    "label": "Remove full-line comments",
    "description": "Deletes lines whose first non-whitespace character is a semicolon.",
}


def normalize_gcode_format(lines, decimal_places=2, normalize_leading_zeros=True):
    """Normalize numeric formatting while preserving rapid versus linear motion."""
    if decimal_places < 0 or decimal_places > 10:
        raise ValueError("decimal_places must be between 0 and 10")

    normalized = []
    for original in lines:
        code, separator, comment = original.partition(";")
        ending = _line_ending(original) if original.endswith(("\n", "\r\n")) else ""
        code = code.rstrip("\r\n")

        if normalize_leading_zeros:
            code = _MOTION_PATTERN.sub(
                lambda match: f"{match.group('indent')}G{match.group('kind')}",
                code,
            )

        def format_word(match):
            letter = match.group("letter")
            value = float(match.group("value"))
            return f"{letter}{value:.{decimal_places}f}"

        code = _WORD_PATTERN.sub(format_word, code)
        rebuilt = code
        if separator:
            rebuilt += f";{comment.rstrip(chr(13) + chr(10))}"
        normalized.append(rebuilt + ending)
    return normalized


normalize_gcode_format.plugin_meta = {
    "label": "Normalize G-code formatting",
    "description": (
        "Normalizes G00/G01 spelling and numeric precision without changing "
        "rapid G0 moves into linear G1 moves."
    ),
}


def convert_g01_g00_to_g1_2decimals(lines, decimal_places=2):
    """Compatibility entry point for saved workflows; preserves G0/G1 meaning."""
    return normalize_gcode_format(lines, decimal_places=decimal_places)


convert_g01_g00_to_g1_2decimals.plugin_meta = {
    "label": "Normalize G-code formatting (legacy workflow key)",
    "description": (
        "Compatibility step for existing presets. It now preserves rapid G0 moves "
        "and exposes numeric precision as an argument."
    ),
}


def remove_before_first_M03(
    lines,
    start_command="M03",
    keep_start_command=False,
    require_start_command=False,
):
    """Discard content before a configurable command marker."""
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if _has_command(line, start_command)
        ),
        None,
    )
    if start is None:
        if require_start_command:
            raise ValueError(f"Start command {start_command!r} was not found")
        return lines
    return lines[start if keep_start_command else start + 1 :]


remove_before_first_M03.plugin_meta = {
    "label": "Trim before start command",
    "description": "Discards content before a configurable whole-command marker.",
}


def insert_endmill_power_before_first_z_move(
    lines,
    pin_name="end_mill",
    power=250.0,
    power_command="",
    motion_codes="G0|G1",
    require_z_move=False,
):
    """Insert a configurable activation command before the first Z-axis move."""
    allowed_codes = {_normalize_gcode_word(code) for code in _commands(motion_codes)}
    if not str(power_command).strip() and power < 0:
        raise ValueError("power must be non-negative when generating a SET_PIN command")
    activation = str(power_command).strip() or f"SET_PIN PIN={pin_name} VALUE={power:g}"
    result = []
    inserted = False

    for line in lines:
        code = _code_part(line)
        motion = re.match(r"^\s*(G0?\d+)\b", code, re.IGNORECASE)
        has_z_word = re.search(rf"(?<![A-Z])Z{_NUMBER}\b", code, re.IGNORECASE)
        if not inserted and motion and has_z_word:
            normalized_motion = _normalize_gcode_word(motion.group(1))
            if normalized_motion in allowed_codes:
                result.append(_as_line(activation, _line_ending(line)))
                inserted = True
        result.append(line)

    if require_z_move and not inserted:
        raise ValueError("No matching Z-axis move was found")
    return result


insert_endmill_power_before_first_z_move.plugin_meta = {
    "label": "Activate endmill before first Z move",
    "description": "Inserts a configurable pin or custom command before the first matching Z move.",
}


def remove_after_M107(
    lines,
    end_command="M107",
    keep_end_command=False,
    require_end_command=False,
):
    """Discard content after a configurable command marker."""
    end = next(
        (index for index, line in enumerate(lines) if _has_command(line, end_command)),
        None,
    )
    if end is None:
        if require_end_command:
            raise ValueError(f"End command {end_command!r} was not found")
        return lines
    return lines[: end + 1 if keep_end_command else end]


remove_after_M107.plugin_meta = {
    "label": "Trim after end command",
    "description": "Discards content after a configurable whole-command marker.",
}


def add_footer(
    lines,
    shutdown_command="SET_PIN PIN=end_mill VALUE=0",
    home_command="HOME_XY",
    tool_command="TOOL_DROPOFF",
):
    """Append configurable shutdown, homing, and tool-release commands."""
    footer = [
        _as_line(command)
        for command in (shutdown_command, home_command, tool_command)
        if str(command).strip()
    ]
    return lines + footer


add_footer.plugin_meta = {
    "label": "Add endmill footer",
    "description": "Appends configurable shutdown, homing, and tool-release commands.",
}
