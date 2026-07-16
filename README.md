# PY-AUTOMATE

A local file-processing pipeline builder. Load a file (or a batch of files), chain Python plugin functions into a processing sequence, run it, and export the result. Think of it as a Pythonic replacement for MS Power Automate — designed for G-code post-processing but general enough for any text or binary file workflow.

---

## Quick Start

Run the setup.bat, or cd to the project folder and type into cmd:

```bash
pip install -r requirements.txt
python app.py
```

Then run the "run.bat" file. Open **http://localhost:5000** in your browser.

---

## Usage

### 1. Load a file

Click **Import → Files** (or **Folder** for a batch run). The file is uploaded to a local workspace session and held there until you export the result.

### 2. Build a pipeline

Click **Add Processing Step** to open the function browser. Search or filter by tag, then click a function to add it as a step. Steps run in order — drag handles to reorder, uncheck to skip without removing.

Some steps expose **configurable inputs** directly on the card (e.g. PCB dimensions for the grid tiler, laser power level). These values are saved with the pipeline.

### 3. Run

Click **Run** (or `Ctrl+Enter`). Each step processes the file in sequence. Warnings and errors appear in the Output console at the bottom.

### 4. Export

Click **Export** to choose the filename and location via a native dialog. If the browser does not support a native save dialog, the processed file downloads normally.

---

## Plugins Panel

The **Plugins** button in the header opens a panel listing all available plugin modules. Uncheck a module to hide all its functions from the Add Step picker for this session — useful when you only want operations relevant to the current file type.

---

## Workflows (Presets)

Save a pipeline as a reusable workflow with **Workflow → Save** (`Ctrl+P`). Saved workflows appear in the **Library** and can be loaded back in one click. The library tracks use count and success rate to surface your most reliable workflows.

---

## Undo / Redo

Every change to the pipeline is pushed onto a 50-state history ring. `Ctrl+Z` / `Ctrl+Y` step through it. The current pipeline is also auto-saved to `last_session.json` and restored when you reopen the app.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+Enter` | Run pipeline |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+S` | Export / Save output |
| `Ctrl+Shift+S` | Export / Save As… |
| `Ctrl+P` | Save workflow preset |
| `Escape` | Close any open panel |

---

## Writing Plugins

Plugin files live in `plugins/`. Every **public function** in a file becomes a browsable pipeline step. The loader handles two signatures automatically.

### Legacy style — simplest

```python
def my_step(lines: list[str]) -> list[str]:
    return [line.upper() for line in lines]
```

`lines` is the file split into individual lines with newlines preserved. Return the transformed list.

### Payload style — full control

Use this when you need to read or write metadata, change the MIME type, or work with binary data.

```python
def my_step(payload: "Payload") -> "Payload":
    payload.data = [line.upper() for line in payload.data]
    payload.meta["processed"] = True
    return payload
```

`Payload` fields:

| Field | Type | Purpose |
|---|---|---|
| `data` | `list[str]` or `bytes` | File content |
| `mime_type` | `str` | IANA media type, e.g. `"text/x-gcode"` |
| `filename` | `str` | Original filename |
| `meta` | `dict` | Free-form inter-step communication |

### Configurable arguments

Add keyword arguments with defaults beyond the first parameter. They appear as editable inputs on the step card and are saved with the pipeline.

```python
def scale_feed_rates(lines, factor=1.0, max_feed=5000.0):
    ...
```

The UI auto-generates number inputs for `factor` and `max_feed` with their defaults pre-filled. The backend coerces values to match the default's type.

To add better labels or override display hints, use `PLUGIN_META["args"]`:

```python
PLUGIN_META = {
    ...
    "args": [
        {"name": "factor",   "label": "Scale Factor"},
        {"name": "max_feed", "label": "Max Feed Rate (mm/min)"},
    ]
}
```

### Module metadata

Add a `PLUGIN_META` dict to the file to set labels, MIME type constraints, and tags:

```python
PLUGIN_META = {
    "label":       "G-code Normaliser",
    "description": "One-line summary shown in the picker.",
    "accepts":     ["text/x-gcode"],
    "outputs":     ["text/x-gcode"],
    "tags":        ["gcode"],
    "requires":    ["numpy"],      # pip package names — checked at load time
    "external":    ["ffmpeg"],     # system binaries — checked with shutil.which
    "language":    "python",
}
```

Individual functions can override the module label and description:

```python
def my_step(lines): ...

my_step.plugin_meta = {
    "label":       "My Step",
    "description": "Does something specific.",
}
```

### AI-assisted plugin creation

Click **New Plugin** in the Plugins panel, describe what you want in plain English, and the app calls the Claude API to generate a complete plugin file. Requires an `ANTHROPIC_API_KEY` set in Settings.

---

## Project Layout

```
app.py                  Flask backend + plugin loader + all API routes
plugins/                Plugin modules (one .py file per domain)
  laser_utils.py        G-code post-processing for Klipper laser cutter
  endmill_utils.py      G-code post-processing for CNC endmill
  gcode_utils.py        General G-code normalization
  iaq_utils.py          Indoor air quality data processing
templates/
  index.html            Main pipeline UI
  plugin_editor.html    AI plugin code editor
  help.html             This documentation
static/
  scripts.js            All frontend logic
  styles.css            Dark theme design system
presets/                Saved workflow JSON files (committed to git)
workspaces/             Per-session upload dirs — gitignored, auto-pruned to 5
history/                Undo/redo ring buffer (50 states) — gitignored
last_session.json       Auto-saved pipeline state — gitignored
```

---

## Runtime State

Files in `workspaces/`, `history/`, `last_session.json`, and `config_info.json` are gitignored — they are runtime state, not source. Presets in `presets/` are source and are committed.

---

## Requirements

```
flask>=3.0
flask-cors>=4.0
anthropic>=0.109      # only needed for AI plugin generation
```

Python 3.10+ recommended. Plugins may declare additional requirements via `PLUGIN_META["requires"]` — these are checked at load time and flagged in the UI if missing.
