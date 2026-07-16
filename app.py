import io
import os
import re
import json
import queue
import logging
import zipfile
import collections
import threading
import importlib.util
import inspect
import traceback
import mimetypes
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Browser log streaming ──────────────────────────────────────────────────

_log_buffer = collections.deque(maxlen=500)
_log_subscribers: list = []
_log_lock = threading.Lock()


class _BrowserLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            if '/logs' in msg:          # suppress SSE endpoint's own traffic
                return
            _log_buffer.append(msg)
            with _log_lock:
                for q in list(_log_subscribers):
                    try:
                        q.put_nowait(msg)
                    except queue.Full:
                        pass
        except Exception:
            pass


_browser_handler = _BrowserLogHandler()
_browser_handler.setFormatter(logging.Formatter('%(levelname)s  %(message)s'))
_browser_handler.setLevel(logging.DEBUG)
logging.getLogger('werkzeug').addHandler(_browser_handler)
app.logger.addHandler(_browser_handler)

# ── Paths ──────────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR   = os.path.join(BASE_DIR, 'plugins')
HISTORY_DIR  = os.path.join(BASE_DIR, 'history')
SESSION_FILE = os.path.join(BASE_DIR, 'presets', 'last_session.json')
CONFIG_FILE  = os.path.join(BASE_DIR, 'config_info.json')
DEFAULT_WS   = os.path.join(BASE_DIR, 'workspaces')
PRESETS_DIR       = os.path.join(BASE_DIR, 'presets')
PRESETS_META_FILE = os.path.join(BASE_DIR, 'presets', 'presets_meta.json')
HISTORY_META = os.path.join(HISTORY_DIR, 'meta.json')
MAX_HISTORY  = 50
MAX_SESSIONS = 5

for path in [PLUGIN_DIR, DEFAULT_WS, HISTORY_DIR, PRESETS_DIR]:
    os.makedirs(path, exist_ok=True)

for _ext, _mime in [
    ('.gcode', 'text/x-gcode'),
    ('.nc',    'text/x-gcode'),
    ('.ngc',   'text/x-gcode'),
    ('.cnc',   'text/x-gcode'),
    ('.gbr',   'text/x-gerber'),
]:
    mimetypes.add_type(_mime, _ext)

# ── Payload ────────────────────────────────────────────────────────────────

@dataclass
class Payload:
    """
    The universal pipeline token passed between every plugin step.

    data      — the actual content:
                  list[str]  for text files (one entry per line, newlines preserved)
                  bytes      for binary files (images, audio, video, etc.)
                  any        for richer types a plugin may introduce (numpy array,
                             PIL Image, etc.) — the next plugin must understand it.
    mime_type — IANA media type, e.g. "text/plain", "image/png", "audio/wav".
                Plugins update this when they change the data format.
    filename  — original filename; used for default output naming and MIME guessing.
    meta      — free-form dict for inter-step communication.
                Examples: {"layer_count": 12}, {"sample_rate": 44100}, {"crf": 23}
    """
    data:      Any
    mime_type: str  = "text/plain"
    filename:  str  = ""
    meta:      dict = field(default_factory=dict)


def payload_from_file(path: str) -> Payload:
    """Read a file from disk into a Payload, auto-detecting its MIME type."""
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    filename = os.path.basename(path)

    # Treat text/* and a few common text-encoded formats as line lists
    is_text = (
        mime.startswith("text/")
        or mime in ("application/json", "application/xml", "application/javascript")
    )

    if is_text:
        with open(path, "r", errors="replace") as f:
            data = f.readlines()
    else:
        with open(path, "rb") as f:
            data = f.read()

    return Payload(data=data, mime_type=mime, filename=filename)


def payload_to_file(payload: Payload, path: str):
    """Write a Payload back to disk in the appropriate mode."""
    if isinstance(payload.data, list):
        with open(path, "w") as f:
            f.writelines(payload.data)
    elif isinstance(payload.data, (bytes, bytearray)):
        with open(path, "wb") as f:
            f.write(payload.data)
    else:
        # Last resort: coerce to string (covers numpy arrays printed, etc.)
        with open(path, "w") as f:
            f.write(str(payload.data))


# ── Plugin loader ──────────────────────────────────────────────────────────
#
# Plugin files live in /plugins/*.py.
#
# Each file may declare a module-level PLUGIN_META dict that applies to all
# functions in the file.  Individual functions may also carry a .plugin_meta
# attribute (set via the @plugin decorator below) that overrides file-level
# metadata for that specific function.
#
# Minimal PLUGIN_META example:
#
#   PLUGIN_META = {
#       "label":       "Convert G00/G01 → G1",
#       "description": "Normalises move commands and rounds to 2 decimal places.",
#       "accepts":     ["text/plain", "text/x-gcode"],
#       "outputs":     ["text/plain", "text/x-gcode"],
#       "requires":    [],           # pip package names
#       "external":    [],           # system binary names (checked with shutil.which)
#       "language":    "python",     # informational
#       "tags":        ["gcode"],
#   }
#
# Plugin function signature (new style):
#   def my_step(payload: Payload) -> Payload: ...
#
# Legacy text-only signature (backwards compatible, auto-wrapped):
#   def my_step(lines: list[str]) -> list[str]: ...

DEFAULT_META = {
    "label":       None,          # falls back to "module.function" key
    "description": "",
    "accepts":     ["text/plain"],
    "outputs":     ["text/plain"],
    "requires":    [],
    "external":    [],
    "language":    "python",
    "tags":        [],
}


def _is_legacy(fn) -> bool:
    """Return True if fn looks like a legacy list[str] -> list[str] plugin."""
    try:
        params = list(inspect.signature(fn).parameters.values())
        if not params:
            return False
        ann = params[0].annotation
        if ann is inspect.Parameter.empty:
            return True
        # Direct class reference (normal import)
        if ann is Payload:
            return False
        # String annotation — occurs when the plugin uses
        # `from __future__ import annotations` or quotes the type: "Payload"
        if isinstance(ann, str) and ann in ("Payload", "app.Payload"):
            return False
        return True
    except (ValueError, TypeError):
        return True


def _wrap_legacy(fn):
    """Wrap fn(list[str], ...) -> list[str] into fn(Payload, **kwargs) -> Payload."""
    orig_sig    = inspect.signature(fn)
    orig_params = set(orig_sig.parameters.keys())

    def wrapped(payload: Payload, **kwargs) -> Payload:
        relevant = {k: v for k, v in kwargs.items() if k in orig_params}
        payload.data = fn(payload.data, **relevant)
        return payload

    wrapped.__name__   = fn.__name__
    wrapped.__doc__    = fn.__doc__
    wrapped._legacy    = True
    wrapped._orig_sig  = orig_sig
    return wrapped


def _discover_fn_args(fn) -> list:
    """Return [{name, type, default, label}] for every kwarg beyond the first param."""
    sig    = getattr(fn, '_orig_sig', None) or inspect.signature(fn)
    params = list(sig.parameters.values())
    result = []
    for p in params[1:]:
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p.default is inspect.Parameter.empty:
            continue
        result.append({
            "name":    p.name,
            "type":    type(p.default).__name__,
            "default": p.default,
            "label":   p.name.replace('_', ' ').title(),
        })
    return result


def _coerce_arg(value, default):
    """Coerce a JSON-decoded value to the same type as the parameter default."""
    try:
        return type(default)(value)
    except (ValueError, TypeError):
        return value


def get_plugins() -> dict:
    """
    Scan the plugins directory and return a dict keyed by module stem (one entry
    per plugin file).  Legacy "module.function" keys are also stored with
    _ui_hidden=True so saved pipelines built before this change still execute.

    {
      "gcode_utils": {
        "funcs":       [<callable>, ...],   # all public fns in file order
        "meta":        { label, description, accepts, outputs, ... },
        "deps_ok":     True,
        "missing_deps": [],
        "_ui_hidden":  False,
        "func_count":  N,
      },
      "gcode_utils.remove_comments": { ..., "_ui_hidden": True },  # legacy compat
      ...
    }
    """
    plugins = {}
    if not os.path.exists(PLUGIN_DIR):
        return plugins

    for filename in sorted(os.listdir(PLUGIN_DIR)):
        if not filename.endswith('.py') or filename == '__init__.py':
            continue
        module_name = filename[:-3]
        path = os.path.join(PLUGIN_DIR, filename)

        try:
            spec   = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"[plugins] Failed to import {filename}: {e}")
            continue

        file_meta = {**DEFAULT_META, **getattr(module, 'PLUGIN_META', {})}

        # Module-level deps are checked once (they apply to all functions)
        missing = []
        for pkg in file_meta.get("requires", []):
            try:
                importlib.import_module(pkg.replace("-", "_"))
            except ImportError:
                missing.append(f"pip:{pkg}")
        for binary in file_meta.get("external", []):
            if shutil.which(binary) is None:
                missing.append(f"bin:{binary}")
        deps_ok = len(missing) == 0

        module_funcs = []
        module_args  = {}   # {name: arg_dict}, deduplicated across all fns in module
        for fn_name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn_name.startswith('_'):
                continue
            callable_fn = _wrap_legacy(fn) if _is_legacy(fn) else fn
            module_funcs.append(callable_fn)

            # Collect discoverable args from this function
            for arg in _discover_fn_args(callable_fn):
                if arg["name"] not in module_args:
                    module_args[arg["name"]] = arg

            # Per-function key: used by "Add Step" picker and for backwards
            # compatibility with pipelines saved before the one-entry-per-file change.
            fn_meta = {**file_meta, **getattr(fn, 'plugin_meta', {})}
            if fn_meta["label"] is None:
                fn_meta["label"] = f"{module_name}.{fn_name}"
            fn_meta["args"] = _discover_fn_args(callable_fn)
            plugins[f"{module_name}.{fn_name}"] = {
                "funcs":       [callable_fn],
                "meta":        fn_meta,
                "module":      module_name,
                "deps_ok":     deps_ok,
                "missing_deps": missing,
                "_ui_hidden":  True,
                "func_count":  1,
            }

        if not module_funcs:
            continue

        mod_meta = {**file_meta}
        if mod_meta["label"] is None:
            mod_meta["label"] = module_name.replace('_', ' ').title()

        # Allow PLUGIN_META["args"] to override labels/add hints for individual args
        for override in file_meta.get("args", []):
            name = override.get("name")
            if name and name in module_args:
                module_args[name].update(override)

        mod_meta["args"] = list(module_args.values())

        plugins[module_name] = {
            "funcs":       module_funcs,
            "meta":        mod_meta,
            "deps_ok":     deps_ok,
            "missing_deps": missing,
            "_ui_hidden":  False,
            "func_count":  len(module_funcs),
        }

    return plugins


# ── Config / workspace routes ──────────────────────────────────────────────

def get_config() -> dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
            # Promote stored API key into the environment on first read
            if not os.environ.get('ANTHROPIC_API_KEY') and cfg.get('api_key'):
                os.environ['ANTHROPIC_API_KEY'] = cfg['api_key']
            return cfg
        except (json.JSONDecodeError, IOError):
            pass
    return {"workspace": DEFAULT_WS}


# ── Session management ────────────────────────────────────────────────────

def list_session_dirs():
    """Return session dirs inside the workspace sorted oldest first."""
    ws = get_config()['workspace']
    result = []
    try:
        for d in os.listdir(ws):
            full = os.path.join(ws, d)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, 'session.json')):
                result.append((os.path.getmtime(full), full))
    except OSError:
        pass
    result.sort()
    return [p for _, p in result]


def prune_sessions():
    sessions = list_session_dirs()
    while len(sessions) >= MAX_SESSIONS:
        shutil.rmtree(sessions.pop(0), ignore_errors=True)


def new_session_dir(filename):
    """Create a timestamped session subfolder and prune old ones."""
    prune_sessions()
    ws   = get_config()['workspace']
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe = re.sub(r'[^\w.-]', '_', os.path.splitext(filename)[0])[:40]
    name = f"{ts}_{safe}"
    path = os.path.join(ws, name)
    os.makedirs(path, exist_ok=True)
    return name, path


@app.route('/')
def index():
    return render_template("index.html")


@app.route('/plugin-editor')
def plugin_editor():
    return render_template("plugin_editor.html")


@app.route('/help')
def help_page():
    return render_template("help.html")


@app.route('/readme')
def readme():
    path = os.path.join(BASE_DIR, 'README.md')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except FileNotFoundError:
        return '# README not found', 404, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/logs')
def log_stream():
    def generate():
        q = queue.Queue(maxsize=200)
        with _log_lock:
            _log_subscribers.append(q)
        try:
            for line in list(_log_buffer):
                yield f"data: {json.dumps(line)}\n\n"
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield f"data: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _log_lock:
                if q in _log_subscribers:
                    _log_subscribers.remove(q)

    return app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@app.route('/get_workspace', methods=['GET'])
def get_workspace_route():
    return jsonify(get_config())


@app.route('/set_workspace', methods=['POST'])
def set_workspace():
    path = request.json.get('path')
    if not path:
        return jsonify({"error": "No path provided"}), 400
    config = get_config()
    config['workspace'] = path
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    return jsonify(config)


@app.route('/set_api_key', methods=['POST'])
def set_api_key():
    key = (request.json or {}).get('key', '').strip()
    if not key:
        return jsonify({"error": "No key provided"}), 400
    config = get_config()
    config['api_key'] = key
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    os.environ['ANTHROPIC_API_KEY'] = key
    return jsonify({"status": "ok"})


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    filename     = os.path.basename(f.filename)
    existing_dir = request.form.get('session_dir', '').strip()

    if existing_dir:
        session_name = os.path.basename(existing_dir)
        session_path = os.path.join(get_config()['workspace'], session_name)
        if not os.path.isdir(session_path):
            return jsonify({"error": "Session not found"}), 404
    else:
        session_name, session_path = new_session_dir(filename)

    f.save(os.path.join(session_path, filename))

    meta_path = os.path.join(session_path, 'session.json')
    try:
        with open(meta_path) as mf:
            meta = json.load(mf)
    except (FileNotFoundError, json.JSONDecodeError):
        meta = {"files": [], "session_dir": session_name}
    if "files" not in meta:
        meta["files"] = [meta.get("filename", filename)]
    if filename not in meta["files"]:
        meta["files"].append(filename)
    with open(meta_path, 'w') as mf:
        json.dump(meta, mf)

    return jsonify({
        "status":      "success",
        "filename":    filename,
        "session_dir": session_name,
    })


@app.route('/list_workspaces', methods=['GET'])
def list_workspaces():
    current = get_config()['workspace']
    parent  = os.path.dirname(current)
    try:
        options = [
            os.path.join(parent, d) for d in os.listdir(parent)
            if os.path.isdir(os.path.join(parent, d))
        ]
        return jsonify(options[:15])
    except Exception:
        return jsonify([DEFAULT_WS])


# ── Session save / load routes ─────────────────────────────────────────────

@app.route('/save', methods=['POST'])
def save_config():
    with open(SESSION_FILE, 'w') as f:
        json.dump(request.json, f, indent=4)
    return jsonify({"status": "success"})


@app.route('/load', methods=['GET'])
def load_config():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                return jsonify(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return jsonify([])


@app.route('/download_output', methods=['GET'])
def download_output():
    session_dir = os.path.basename(request.args.get('session_dir', '').strip())
    filename    = os.path.basename(request.args.get('filename', '').strip())
    if not session_dir or not filename:
        return jsonify({"error": "Missing session_dir or filename"}), 400
    path = os.path.join(get_config()['workspace'], session_dir, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True, download_name=filename)


@app.route('/save_preset', methods=['POST'])
def save_preset():
    data     = request.json
    filename = data.get('filename', '').strip()
    scripts  = data.get('scripts', [])
    if not filename:
        return jsonify({"error": "No filename provided"}), 400
    basename = os.path.basename(filename)
    if not basename.endswith('.json'):
        basename += '.json'
    with open(os.path.join(PRESETS_DIR, basename), 'w') as f:
        json.dump(scripts, f, indent=4)
    return jsonify({"status": "success", "filename": basename})


def read_presets_meta() -> dict:
    try:
        with open(PRESETS_META_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_presets_meta(meta: dict):
    with open(PRESETS_META_FILE, 'w') as f:
        json.dump(meta, f, indent=4)


@app.route('/list_presets', methods=['GET'])
def list_presets():
    try:
        meta  = read_presets_meta()
        files = sorted(f for f in os.listdir(PRESETS_DIR)
                       if f.endswith('.json') and f != 'presets_meta.json')
        result = []
        for filename in files:
            m    = meta.get(filename, {})
            uses = m.get('uses', 0)
            succ = m.get('successes', 0)
            # Count steps by reading the file
            try:
                with open(os.path.join(PRESETS_DIR, filename)) as pf:
                    steps = json.load(pf)
                step_count = len(steps) if isinstance(steps, list) else 0
            except Exception:
                step_count = 0
            result.append({
                'filename':     filename,
                'uses':         uses,
                'successes':    succ,
                'success_rate': round(succ / uses, 2) if uses > 0 else None,
                'step_count':   step_count,
                'last_used':    m.get('last_used'),
            })
        return jsonify(result)
    except Exception:
        return jsonify([])


@app.route('/presets/<filename>', methods=['GET'])
def get_preset(filename):
    filename = os.path.basename(filename)
    path = os.path.join(PRESETS_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    try:
        with open(path, 'r') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/preset_event', methods=['POST'])
def preset_event():
    filename = os.path.basename(request.json.get('filename', '').strip())
    event    = request.json.get('event', '')
    if not filename or event not in ('loaded', 'success'):
        return jsonify({"error": "Invalid request"}), 400
    meta = read_presets_meta()
    entry = meta.setdefault(filename, {"uses": 0, "successes": 0, "last_used": None})
    if event == 'loaded':
        entry['uses'] += 1
        entry['last_used'] = datetime.now().isoformat(timespec='seconds')
    elif event == 'success':
        entry['successes'] += 1
    write_presets_meta(meta)
    return jsonify({"status": "ok"})


# ── File-content history ──────────────────────────────────────────────────
# Stores raw byte snapshots of a file before each /execute run.
# Keyed by "session_dir/filename".  Pure in-memory; lost on server restart.

_file_histories: dict = {}
_file_hist_lock = threading.Lock()


def _fh_key(session_dir, filename):
    return f"{session_dir}/{filename}"


def _fh_get(key):
    if key not in _file_histories:
        _file_histories[key] = {"past": [], "future": [], "hit_limit": False}
    return _file_histories[key]


def _fh_limit():
    return max(1, int(get_config().get("file_undo_limit", 10)))


def fh_push_snapshot(session_dir, filename, path):
    """Snapshot the current file contents before overwriting it."""
    try:
        with open(path, "rb") as f:
            snapshot = f.read()
    except OSError:
        return
    key = _fh_key(session_dir, filename)
    limit = _fh_limit()
    with _file_hist_lock:
        fh = _fh_get(key)
        fh["past"].append(snapshot)
        fh["future"].clear()
        if len(fh["past"]) > limit:
            fh["past"].pop(0)
            fh["hit_limit"] = True


def fh_undo(session_dir, filename, path):
    key = _fh_key(session_dir, filename)
    with _file_hist_lock:
        fh = _fh_get(key)
        if not fh["past"]:
            return False
        try:
            with open(path, "rb") as f:
                current = f.read()
        except OSError:
            return False
        prev = fh["past"].pop()
        fh["future"].append(current)
    with open(path, "wb") as f:
        f.write(prev)
    return True


def fh_redo(session_dir, filename, path):
    key = _fh_key(session_dir, filename)
    with _file_hist_lock:
        fh = _fh_get(key)
        if not fh["future"]:
            return False
        try:
            with open(path, "rb") as f:
                current = f.read()
        except OSError:
            return False
        nxt = fh["future"].pop()
        fh["past"].append(current)
    with open(path, "wb") as f:
        f.write(nxt)
    return True


def fh_reset(session_dir):
    with _file_hist_lock:
        keys = [k for k in _file_histories if k.startswith(f"{session_dir}/")]
        for k in keys:
            del _file_histories[k]


def fh_status(session_dir, filename):
    key = _fh_key(session_dir, filename)
    with _file_hist_lock:
        fh = _fh_get(key)
        return {
            "can_undo":  len(fh["past"]) > 0,
            "can_redo":  len(fh["future"]) > 0,
            "hit_limit": fh["hit_limit"],
        }


@app.route('/file_history/status', methods=['GET'])
def file_history_status():
    session_dir = os.path.basename(request.args.get('session_dir', ''))
    filename    = request.args.get('filename', '')
    if not session_dir or not filename:
        return jsonify({"can_undo": False, "can_redo": False, "hit_limit": False})
    return jsonify(fh_status(session_dir, filename))


@app.route('/file_history/undo', methods=['POST'])
def file_history_undo():
    data        = request.json or {}
    session_dir = os.path.basename(data.get('session_dir', ''))
    filename    = data.get('filename', '')
    workspace   = get_config()['workspace']
    path        = os.path.join(workspace, session_dir, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    if fh_undo(session_dir, filename, path):
        return jsonify({"status": "ok"})
    return jsonify({"error": "Nothing to undo"}), 400


@app.route('/file_history/redo', methods=['POST'])
def file_history_redo():
    data        = request.json or {}
    session_dir = os.path.basename(data.get('session_dir', ''))
    filename    = data.get('filename', '')
    workspace   = get_config()['workspace']
    path        = os.path.join(workspace, session_dir, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    if fh_redo(session_dir, filename, path):
        return jsonify({"status": "ok"})
    return jsonify({"error": "Nothing to redo"}), 400


@app.route('/file_history/reset', methods=['POST'])
def file_history_reset():
    session_dir = os.path.basename((request.json or {}).get('session_dir', ''))
    if session_dir:
        fh_reset(session_dir)
    return jsonify({"status": "ok"})


@app.route('/set_file_undo_limit', methods=['POST'])
def set_file_undo_limit():
    try:
        limit = max(1, int((request.json or {}).get('limit', 10)))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid limit"}), 400
    config = get_config()
    config['file_undo_limit'] = limit
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    return jsonify({"status": "ok", "limit": limit})


# ── History routes ─────────────────────────────────────────────────────────

def read_history_meta():
    if os.path.exists(HISTORY_META):
        try:
            with open(HISTORY_META, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"pointer": -1, "count": 0}


def write_history_meta(meta):
    with open(HISTORY_META, 'w') as f:
        json.dump(meta, f)


def history_path(index):
    return os.path.join(HISTORY_DIR, f'session_{index:04d}.json')


@app.route('/history/push', methods=['POST'])
def history_push():
    meta        = read_history_meta()
    new_pointer = meta["pointer"] + 1
    file_index  = new_pointer % MAX_HISTORY

    with open(history_path(file_index), 'w') as f:
        json.dump(request.json, f, indent=4)

    meta["pointer"] = new_pointer
    meta["count"]   = min(new_pointer + 1, MAX_HISTORY)
    write_history_meta(meta)
    return jsonify({"status": "success", "pointer": new_pointer, "count": meta["count"]})


@app.route('/history/undo', methods=['GET'])
def history_undo():
    meta    = read_history_meta()
    pointer = meta["pointer"]
    if pointer <= 0:
        return jsonify({"error": "Nothing to undo", "at_start": True}), 400

    target = pointer - 1
    p      = history_path(target % MAX_HISTORY)
    if not os.path.exists(p):
        return jsonify({"error": "History file missing"}), 500

    with open(p, 'r') as f:
        state = json.load(f)

    meta["pointer"] = target
    write_history_meta(meta)
    return jsonify({"state": state, "pointer": target, "count": meta["count"]})


@app.route('/history/redo', methods=['GET'])
def history_redo():
    meta    = read_history_meta()
    pointer = meta["pointer"]
    count   = meta["count"]
    if pointer >= count - 1:
        return jsonify({"error": "Nothing to redo", "at_end": True}), 400

    target = pointer + 1
    p      = history_path(target % MAX_HISTORY)
    if not os.path.exists(p):
        return jsonify({"error": "History file missing"}), 500

    with open(p, 'r') as f:
        state = json.load(f)

    meta["pointer"] = target
    write_history_meta(meta)
    return jsonify({"state": state, "pointer": target, "count": meta["count"]})


@app.route('/history/status', methods=['GET'])
def history_status():
    meta = read_history_meta()
    return jsonify({
        "can_undo": meta["pointer"] > 0,
        "can_redo": meta["pointer"] < meta["count"] - 1,
        "pointer":  meta["pointer"],
        "count":    meta["count"],
    })


# ── Plugin routes ──────────────────────────────────────────────────────────

@app.route('/get_plugin_source', methods=['GET'])
def get_plugin_source():
    filename = os.path.basename(request.args.get('file', '').strip())
    if not filename.endswith('.py'):
        return jsonify({"error": "Invalid filename"}), 400
    path = os.path.join(PLUGIN_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return jsonify({"code": f.read(), "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/open_plugins_folder', methods=['GET'])
def open_plugins_folder():
    import subprocess, sys
    try:
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', PLUGIN_DIR])
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', PLUGIN_DIR])
        else:
            subprocess.Popen(['xdg-open', PLUGIN_DIR])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/list_plugins', methods=['GET'])
def list_plugins():
    plugins = get_plugins()
    result  = []
    for key, info in plugins.items():
        if info.get("_ui_hidden"):
            continue
        m = info["meta"]
        result.append({
            "key":          key,
            "label":        m["label"],
            "description":  m["description"],
            "accepts":      m["accepts"],
            "outputs":      m["outputs"],
            "tags":         m["tags"],
            "deps_ok":      info["deps_ok"],
            "missing_deps": info["missing_deps"],
            "func_count":   info["func_count"],
            "args":         m.get("args", []),
        })
    return jsonify(result)


@app.route('/list_functions', methods=['GET'])
def list_functions():
    """
    Return one entry per public function across all plugin modules.
    Used by the "Add Processing Step" picker so users browse individual operations.
    Each entry includes a `module` key for filtering by session-enabled modules.
    """
    plugins = get_plugins()
    result  = []
    for key, info in plugins.items():
        if not info.get("_ui_hidden"):
            continue  # skip module-level entries
        m = info["meta"]
        result.append({
            "key":          key,
            "module":       info["module"],
            "label":        m["label"],
            "description":  m["description"],
            "accepts":      m["accepts"],
            "outputs":      m["outputs"],
            "tags":         m["tags"],
            "deps_ok":      info["deps_ok"],
            "missing_deps": info["missing_deps"],
            "func_count":   1,
            "args":         m.get("args", []),
        })
    return jsonify(result)


@app.route('/preview_file', methods=['GET'])
def preview_file():
    """Return file contents for the in-app preview panel (text) or metadata (binary)."""
    session_dir = os.path.basename(request.args.get('session_dir', ''))
    filename    = request.args.get('filename', '')
    workspace   = get_config()['workspace']
    path        = os.path.join(workspace, session_dir, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    is_text = (
        mime.startswith("text/")
        or mime in ("application/json", "application/xml", "application/javascript")
    )

    MAX_LINES = 2000
    full = request.args.get('full') == '1'
    if is_text:
        try:
            with open(path, "r", errors="replace", newline="") as f:
                lines = f.readlines()
            truncated = len(lines) > MAX_LINES
            return jsonify({
                "type":        "text",
                "content":     "".join(lines if full else lines[:MAX_LINES]),
                "total_lines": len(lines),
                "truncated":   truncated and not full,
                "mime_type":   mime,
            })
        except OSError as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({
            "type":      "binary",
            "mime_type": mime,
            "size":      os.path.getsize(path),
        })


@app.route('/update_file', methods=['POST'])
def update_file():
    """Replace a session text file, recording the previous contents for undo."""
    data = request.json or {}
    session_dir = os.path.basename(data.get('session_dir', '').strip())
    filename = os.path.basename(data.get('filename', '').strip())
    content = data.get('content')
    if not session_dir or not filename or not isinstance(content, str):
        return jsonify({"error": "Missing session_dir, filename, or content"}), 400

    path = os.path.join(get_config()['workspace'], session_dir, filename)
    if not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404

    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    is_text = (
        mime.startswith("text/")
        or mime in ("application/json", "application/xml", "application/javascript")
    )
    if not is_text:
        return jsonify({"error": "Binary files cannot be edited as text"}), 415

    try:
        with open(path, "r", errors="replace", newline="") as f:
            current = f.read()
        if current != content:
            fh_push_snapshot(session_dir, filename, path)
            with open(path, "w", newline="") as f:
                f.write(content)
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "ok"})


@app.route('/settings_info', methods=['GET'])
def settings_info():
    plugin_count = len([
        f for f in os.listdir(PLUGIN_DIR)
        if f.endswith('.py') and f != '__init__.py'
    ]) if os.path.exists(PLUGIN_DIR) else 0
    cfg = get_config()
    return jsonify({
        "api_key_set":     bool(os.environ.get('ANTHROPIC_API_KEY')),
        "workspace":       cfg['workspace'],
        "plugin_dir":      PLUGIN_DIR,
        "plugin_count":    plugin_count,
        "file_undo_limit": int(cfg.get('file_undo_limit', 10)),
    })


# ── Execution route ────────────────────────────────────────────────────────

@app.route('/execute', methods=['POST'])
def execute_scripts():
    """
    POST { "filename": "part.gcode", "scripts": [{"pluginKey": "..."}, ...] }

    Pipeline:
      1. Load file → Payload
      2. For each active step: call plugin(payload) → new payload
      3. Write final payload back to the same file

    Errors in individual steps are caught; execution halts at the first failure
    and reports which steps completed successfully before the crash.
    """
    data        = request.json
    filename    = data.get('filename')
    session_dir = os.path.basename(data.get('session_dir', ''))
    scripts     = data.get('scripts', [])

    workspace   = get_config()['workspace']
    target_path = (
        os.path.join(workspace, session_dir, filename) if session_dir
        else os.path.join(workspace, filename)
    )

    if not os.path.exists(target_path):
        return jsonify({"error": f"File not found in workspace: {filename}"}), 404

    plugins = get_plugins()

    # Pre-flight: validate all keys and check deps before touching the file
    active_steps = []
    for step in scripts:
        key = step.get('pluginKey')
        if key not in plugins:
            return jsonify({"error": f"Unknown plugin: '{key}'"}), 400
        info = plugins[key]
        if not info["deps_ok"]:
            return jsonify({
                "error":        f"Plugin '{key}' has unsatisfied dependencies.",
                "missing_deps": info["missing_deps"],
            }), 400
        active_steps.append((key, info["funcs"], info["meta"], step.get('args', {})))

    try:
        payload  = payload_from_file(target_path)
        step_log = []

        for key, funcs, meta, step_args in active_steps:
            accepted = meta.get("accepts", [])
            if accepted and payload.mime_type not in accepted:
                step_log.append({
                    "step":    key,
                    "warning": (
                        f"type mismatch — plugin accepts {accepted}, "
                        f"payload is '{payload.mime_type}'"
                    ),
                })

            for fn in funcs:
                try:
                    # Resolve which of the step's args this fn accepts
                    sig        = getattr(fn, '_orig_sig', None) or inspect.signature(fn)
                    fn_params  = dict(list(sig.parameters.items())[1:])  # skip first param
                    fn_kwargs  = {
                        k: _coerce_arg(v, fn_params[k].default)
                        for k, v in step_args.items()
                        if k in fn_params and fn_params[k].default is not inspect.Parameter.empty
                    }
                    payload = fn(payload, **fn_kwargs)
                except ValueError as e:
                    return jsonify({
                        "error":     f"Step '{key}' → '{fn.__name__}': bad input — {e}",
                        "completed": [s["step"] for s in step_log if "warning" not in s],
                    }), 400
                except Exception as e:
                    return jsonify({
                        "error":     f"Step '{key}' → '{fn.__name__}': {type(e).__name__}: {e}",
                        "trace":     traceback.format_exc(),
                        "completed": [s["step"] for s in step_log if "warning" not in s],
                    }), 500

            step_log.append({"step": key, "status": "ok"})

        fh_push_snapshot(session_dir, filename, target_path)
        payload_to_file(payload, target_path)

        return jsonify({
            "status":    "success",
            "message":   f"Processed {len(active_steps)} step(s) on '{filename}'.",
            "steps":     step_log,
            "mime_type": payload.mime_type,
        })

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ── AI plugin generation ───────────────────────────────────────────────────

_PLUGIN_SYSTEM_PROMPT = """\
You are writing a plugin for PY-AUTOMATE, a local file-processing pipeline tool.

Plugins are plain Python files in the plugins/ folder. Each public function becomes
a pipeline step. The simplest (and preferred) signature is the legacy style:

    def my_step(lines: list[str]) -> list[str]: ...

lines is the file split into individual lines (newlines preserved).
Return the transformed line list.

File-level metadata (optional, but include it):

    PLUGIN_META = {
        "label":       "Short human name",
        "description": "One sentence.",
        "accepts":     ["text/x-gcode"],   # MIME types this works on
        "outputs":     ["text/x-gcode"],
        "tags":        ["gcode"],          # for filtering in the UI
    }

Rules:
- No markdown, no explanation — output ONLY the .py file content.
- Keep functions small and focused; one logical task per function.
- Standard library only unless the user requests a specific package.
- Follow the style of this example exactly:

import re

PLUGIN_META = {
    "label":       "G-code Normaliser",
    "description": "Converts G00/G01 to G1 and rounds coordinates to 2 dp.",
    "accepts":     ["text/x-gcode"],
    "outputs":     ["text/x-gcode"],
    "tags":        ["gcode"],
}

def normalize_moves(lines):
    result = []
    for line in lines:
        line = re.sub(r'\\bG0[01]\\b', 'G1', line)
        line = re.sub(r'([A-Z])(-?\\d+\\.\\d+)',
                      lambda m: f"{m.group(1)}{float(m.group(2)):.2f}", line)
        result.append(line)
    return result
"""


@app.route('/generate_plugin', methods=['POST'])
def generate_plugin():
    description = (request.json or {}).get('description', '').strip()
    if not description:
        return jsonify({"error": "No description provided"}), 400

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set in the environment."}), 400

    try:
        import anthropic as ant
    except ImportError:
        return jsonify({"error": "anthropic package not installed"}), 500

    client  = ant.Anthropic(api_key=api_key)
    message = client.messages.create(
        model      = "claude-sonnet-4-6",
        max_tokens = 2048,
        system     = _PLUGIN_SYSTEM_PROMPT,
        messages   = [{"role": "user", "content": description}],
    )

    block = next((b for b in message.content if isinstance(b, ant.types.TextBlock)), None)
    if block is None:
        return jsonify({"error": "No text in API response"}), 500
    code = block.text.strip()
    # Strip accidental markdown fences
    if code.startswith('```'):
        lines = code.splitlines()
        start = 1
        end   = len(lines) - 1 if lines[-1].strip() == '```' else len(lines)
        code  = '\n'.join(lines[start:end])

    return jsonify({"code": code})


@app.route('/save_plugin', methods=['POST'])
def save_plugin():
    body     = request.json or {}
    code     = body.get('code', '').strip()
    filename = os.path.basename(body.get('filename', '').strip())
    if not code or not filename:
        return jsonify({"error": "Missing code or filename"}), 400
    if not filename.endswith('.py'):
        filename += '.py'
    dest = os.path.join(PLUGIN_DIR, filename)
    with open(dest, 'w', encoding='utf-8') as f:
        f.write(code)
    return jsonify({"status": "ok", "filename": filename})


@app.route('/download_batch', methods=['GET'])
def download_batch():
    session_dir = os.path.basename(request.args.get('session_dir', '').strip())
    if not session_dir:
        return jsonify({"error": "Missing session_dir"}), 400
    session_path = os.path.join(get_config()['workspace'], session_dir)
    if not os.path.isdir(session_path):
        return jsonify({"error": "Session not found"}), 404
    try:
        with open(os.path.join(session_path, 'session.json')) as f:
            meta = json.load(f)
        files = meta.get('files', [])
    except Exception:
        files = []
    if not files:
        return jsonify({"error": "No files in session"}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in files:
            fpath = os.path.join(session_path, fname)
            if os.path.isfile(fpath):
                zf.write(fpath, fname)
    buf.seek(0)
    zip_name = f"{session_dir}_output.zip"
    return send_file(buf, as_attachment=True, download_name=zip_name,
                     mimetype='application/zip')


if __name__ == '__main__':
    import socket as _socket
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as _s:
            if _s.connect_ex(('localhost', 5000)) == 0:
                print("Server already running on port 5000 — exiting to avoid duplicate.")
                raise SystemExit(0)
    app.run(debug=True, port=5000)
