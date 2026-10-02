import importlib
import inspect
import json
import unittest
from pathlib import Path

from plugins import endmill_utils, laser_utils


ROOT = Path(__file__).resolve().parents[1]


class EndmillLibraryTests(unittest.TestCase):
    def test_normalizer_preserves_motion_meaning_and_comments(self):
        lines = [
            "G00 X1.234 Y2 ; X999.999 stays a comment\n",
            "G01 Z-.125\n",
            "HOME2\n",
        ]

        result = endmill_utils.normalize_gcode_format(lines, decimal_places=2)

        self.assertEqual(
            result,
            [
                "G0 X1.23 Y2.00 ; X999.999 stays a comment\n",
                "G1 Z-0.12\n",
                "HOME2\n",
            ],
        )

    def test_trim_uses_whole_commands_and_can_require_marker(self):
        lines = ["M103\n", "; M03\n", "M03 S100\n", "G1 X1\n"]

        self.assertEqual(endmill_utils.remove_before_first_M03(lines), ["G1 X1\n"])
        with self.assertRaises(ValueError):
            endmill_utils.remove_before_first_M03(
                ["G1 X1\n"], start_command="M42", require_start_command=True
            )

    def test_power_insertion_handles_spacing_word_order_and_configuration(self):
        lines = ["  G01 X2 Z-0.1 F100\n"]

        result = endmill_utils.insert_endmill_power_before_first_z_move(
            lines, pin_name="spindle", power=75
        )

        self.assertEqual(result[0], "SET_PIN PIN=spindle VALUE=75\n")
        self.assertEqual(result[1], lines[0])


class LaserLibraryTests(unittest.TestCase):
    def test_m_code_normalizer_does_not_change_comments_or_longer_codes(self):
        lines = ["M03 ; keep M05 in comment\n", "M103\n", "m005\n"]

        self.assertEqual(
            laser_utils.replace_m_codes(lines),
            ["M3 ; keep M05 in comment\n", "M103\n", "m5\n"],
        )

    def test_klipper_conversion_only_removes_s_word(self):
        lines = ["G1 X1 S0.5 Z2 A3 ; preserve everything else\n"]

        result = laser_utils.convert_to_klipper_format(
            lines, pin_name="beam", power_scale=2
        )

        self.assertEqual(result[0], "SET_PIN PIN=beam VALUE=1\n")
        self.assertEqual(result[1], "G1 X1 Z2 A3 ; preserve everything else\n")

    def test_z_transition_matching_is_numeric_and_order_independent(self):
        lines = [" G1 X2 Z.000 F100\n", "G00 X3 Z+1.0\n"]

        result = laser_utils.inject_laser_power_on_z_moves(lines, power=0.3)

        self.assertEqual(result[1], "SET_PIN PIN=laser VALUE=0.3\n")
        self.assertEqual(result[2], "SET_PIN PIN=laser VALUE=0\n")

        with self.assertRaises(ValueError):
            laser_utils.inject_laser_power_on_z_moves(
                lines, engrave_z=1.0, travel_z=1.0
            )

    def test_laser_wrapper_uses_configurable_commands(self):
        result = laser_utils.add_laser_header_footer(
            ["G1 X1\n"],
            home_command="HOME",
            tool_command="PICK",
            shutdown_command="OFF",
            finish_home_command="PARK",
            release_command="DROP",
        )

        self.assertEqual(
            result, ["HOME\n", "PICK\n", "G1 X1\n", "OFF\n", "PARK\n", "DROP\n"]
        )

    def test_grid_preserves_wrapper_and_offsets_only_motion_body(self):
        lines = [
            "HOME\n",
            "PICK\n",
            "G0 X0 Y0\n",
            "G1 X10 Y10 F100\n",
            "OFF\n",
            "DROP\n",
        ]

        result = laser_utils.make_laser_grid(
            lines,
            pcb_width=25,
            pcb_height=10,
            gap=2,
            header_end_command="PICK",
            footer_start_command="OFF",
        )

        self.assertEqual(result[:2], ["HOME\n", "PICK\n"])
        self.assertEqual(result[-2:], ["OFF\n", "DROP\n"])
        self.assertIn("G0 X12 Y0\n", result)
        self.assertIn("G1 X22 Y10 F100\n", result)

    def test_grid_rejects_expansion_above_configured_limit(self):
        lines = ["G0 X0 Y0\n", "G1 X1 Y1\n"]

        with self.assertRaises(ValueError):
            laser_utils.make_laser_grid(
                lines,
                pcb_width=100,
                pcb_height=100,
                gap=0,
                max_generated_tiles=10,
            )


class PresetContractTests(unittest.TestCase):
    def test_every_preset_step_resolves_and_only_passes_supported_arguments(self):
        for path in (ROOT / "presets").glob("*.json"):
            if path.name == "presets_meta.json":
                continue
            steps = json.loads(path.read_text(encoding="utf-8"))
            for step in steps:
                module_name, function_name = step["pluginKey"].split(".", 1)
                module = importlib.import_module(f"plugins.{module_name}")
                function = getattr(module, function_name)
                parameters = inspect.signature(function).parameters
                unsupported = set(step.get("args", {})) - set(parameters)
                self.assertFalse(
                    unsupported, f"{path.name}: {step['pluginKey']}: {unsupported}"
                )


if __name__ == "__main__":
    unittest.main()
