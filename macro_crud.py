import importlib.util
import os
from typing import Callable, List

class MacroCRUD:
    def __init__(self):
        self.steps = []  # Store steps as {"description", "function", "enabled"}

    def add_step(self, description: str, function: Callable):
        """Add a step to the processor."""
        self.steps.append({"description": description, "function": function, "enabled": True})

    def remove_step(self, index: int):
        """Remove a step by index."""
        if 0 <= index < len(self.steps):
            self.steps.pop(index)

    def toggle_step(self, index: int):
        """Toggle a step's enabled/disabled state."""
        if 0 <= index < len(self.steps):
            self.steps[index]["enabled"] = not self.steps[index]["enabled"]

    def save_steps(self, filename: str):
        """Save steps to a Python file in a readable format."""
        with open(filename, 'w') as f:
            f.write("def get_steps():\n")
            f.write("    steps = []\n")
            for step in self.steps:
                desc = step["description"]
                func_source = self.get_function_source(step["function"])
                f.write(f"    # {desc}\n")
                f.write(f"    steps.append((\"{desc}\", {func_source}))\n\n")
            f.write("    return steps\n")

    def get_function_source(self, func: Callable) -> str:
        """Retrieve the source code of a function as a string."""
        import inspect
        source_lines = inspect.getsource(func).splitlines()
        indented_source = "\n".join(f"        {line}" for line in source_lines)
        return f"lambda lines: (\n{indented_source}\n    )"

    def load_steps(self, filename: str):
        """Load steps from a Python file."""
        spec = importlib.util.spec_from_file_location("loaded_steps", filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded_steps = module.get_steps()
        self.steps = [{"description": desc, "function": func, "enabled": True} for desc, func in loaded_steps]

    def process_gcode(self, lines: List[str]) -> List[str]:
        """Process G-code lines with enabled steps."""
        for step in self.steps:
            if step["enabled"]:
                lines = step["function"](lines)
        return lines
