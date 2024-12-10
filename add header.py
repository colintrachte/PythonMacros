def get_steps():
    steps = []
    # Add Header
    steps.append(("Add Header", lambda lines: (
                def example_step(lines):
                    return ["HOME_PRINTER\n", "GRAB_ENDMILL\n"] + lines
    )))

    return steps
