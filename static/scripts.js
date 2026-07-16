/**
 * PY-AUTOMATE — scripts.js
 */

const API_BASE = 'http://localhost:5000';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
    selectedFile:          null,
    selectedFileMime:      null,
    sessionDir:            null,
    outputFilename:        null,
    currentPresetName:     null,
    pluginCache:           [],   // module-level entries, for "Choose Plugins" panel
    functionCache:         [],   // function-level entries, for "Add Step" picker
    // Batch
    batchFiles:            [],    // [{name, size, file}] for current selection
    pendingFiles:          [],    // held during warn prompt before upload starts
    isBatchSession:        false, // true when session has >1 file
    batchRunDone:          false, // true after a batch run completes
    uploadAbortFlag:       false,
    // Choose Plugins
    sessionPlugins:        null,   // null = all available; Set = restricted set (module keys)
    chooseTagFilter:       null,   // tag filter inside the choose panel
    chooseOpen:            false,
    // Add Step picker
    addStepTagFilter:      null,   // persists across opens
    pluginDropdownOpen:    false,
    // Modals
    presetLibraryOpen:     false,
    cachedPresets:         [],
    fileEditDirty:         false,
    fileEditSaving:        false,
};

let el = {};

// ── MIME guessing ─────────────────────────────────────────────────────────

function guessMime(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const map = {
        gcode: 'text/x-gcode', gc: 'text/x-gcode', nc: 'text/x-gcode',
        txt: 'text/plain', csv: 'text/plain', log: 'text/plain',
        json: 'application/json', xml: 'application/xml', js: 'application/javascript',
        py: 'text/x-python',
        png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
        gif: 'image/gif', bmp: 'image/bmp', tif: 'image/tiff', tiff: 'image/tiff',
        wav: 'audio/wav', mp3: 'audio/mpeg', flac: 'audio/flac', ogg: 'audio/ogg',
        mp4: 'video/mp4', mov: 'video/quicktime', avi: 'video/x-msvideo',
        mkv: 'video/x-matroska', pdf: 'application/pdf',
    };
    return map[ext] || 'application/octet-stream';
}

// ── Console ────────────────────────────────────────────────────────────────

function log(msg, type = 'info') {
    const line = document.createElement('div');
    line.className = `console-line ${type}`;
    line.textContent = `[${new Date().toLocaleTimeString()}]  ${msg}`;
    el.consoleContent.appendChild(line);
    el.consoleContent.scrollTop = el.consoleContent.scrollHeight;
}

// ── Server debug log stream ────────────────────────────────────────────────

let _logSource = null;

function updateDebugToggle() {
    const btn = el.consoleDebugToggle;
    if (!btn) return;
    btn.classList.toggle('active', !!_logSource);
    btn.title = _logSource ? 'Disconnect server logs' : 'Stream Flask server logs into this console';
}

function startServerDebug() {
    if (_logSource) return;
    _logSource = new EventSource(`${API_BASE}/logs`);
    _logSource.onmessage = e => {
        try { log('[server] ' + JSON.parse(e.data), 'system'); } catch (_) {}
    };
    localStorage.setItem('serverDebug', '1');
    log('Server debug stream connected.', 'system');
    updateDebugToggle();
}

function stopServerDebug() {
    if (_logSource) { _logSource.close(); _logSource = null; }
    localStorage.removeItem('serverDebug');
    log('Server debug stream disconnected.', 'system');
    updateDebugToggle();
}

function copyConsoleToClipboard() {
    const text = Array.from(el.consoleContent.querySelectorAll('.console-line'))
        .map(l => l.textContent).join('\n');
    navigator.clipboard.writeText(text).then(
        () => log('Console copied to clipboard.', 'system'),
        () => log('Clipboard write failed — check browser permissions.', 'warn'),
    );
}

// ── Step list ──────────────────────────────────────────────────────────────

function createStepEl({ pluginKey, description = '', isChecked = true, args = {} }) {
    const li = document.createElement('li');
    li.dataset.pluginKey = pluginKey;
    if (!isChecked) li.classList.add('step-disabled');

    const info      = state.functionCache.find(p => p.key === pluginKey)
                   || state.pluginCache.find(p => p.key === pluginKey)
                   || {};
    const label     = info.label || pluginKey;
    const depsOk    = info.deps_ok !== false;
    const missing   = info.missing_deps || [];
    const pluginArgs = info.args || [];

    const depWarn = !depsOk
        ? `<div class="step-dep-warning" title="Missing: ${missing.join(', ')}">
               <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
               </svg>Missing deps</div>`
        : '';

    const argsHtml = pluginArgs.length
        ? `<div class="step-args">${pluginArgs.map(a => {
            const val = args[a.name] !== undefined ? args[a.name] : a.default;
            if (a.type === 'bool') {
                return `<label class="step-arg-row">
                    <span class="step-arg-label">${a.label}</span>
                    <input type="checkbox" class="step-arg-input" data-arg="${a.name}" data-arg-type="bool" ${val ? 'checked' : ''}>
                </label>`;
            }
            return `<label class="step-arg-row">
                <span class="step-arg-label">${a.label}</span>
                <input type="number" class="step-arg-input" data-arg="${a.name}" data-arg-type="${a.type}" value="${val}" step="${a.type === 'float' ? 'any' : '1'}">
            </label>`;
        }).join('')}</div>`
        : '';

    // Derive file + function name for the edit button
    // pluginKey is either "module" or "module.fn_name"
    const dotIdx   = pluginKey.indexOf('.');
    const editFile = (dotIdx > -1 ? pluginKey.slice(0, dotIdx) : pluginKey) + '.py';
    const editFn   = dotIdx > -1 ? pluginKey.slice(dotIdx + 1) : null;
    const editUrl  = `/plugin-editor?file=${encodeURIComponent(editFile)}${editFn ? `&fn=${encodeURIComponent(editFn)}` : ''}`;

    li.innerHTML = `
        <div class="step-drag-handle">
            <svg width="12" height="16" viewBox="0 0 12 16" fill="currentColor">
                <circle cx="3.5" cy="3"  r="1.5"/><circle cx="8.5" cy="3"  r="1.5"/>
                <circle cx="3.5" cy="8"  r="1.5"/><circle cx="8.5" cy="8"  r="1.5"/>
                <circle cx="3.5" cy="13" r="1.5"/><circle cx="8.5" cy="13" r="1.5"/>
            </svg>
        </div>
        <input type="checkbox" class="step-checkbox" ${isChecked ? 'checked' : ''}>
        <div class="step-body">
            <div class="step-header-row">
                <span class="step-label">${label}</span>
                <span class="step-key-sub">${pluginKey}</span>
                ${depWarn}
            </div>
            <input type="text" class="step-note" value="${description.replace(/"/g,'&quot;')}" placeholder="Add a note…">
            ${argsHtml}
        </div>
        <a class="step-edit-btn" href="${editUrl}" target="_blank" title="Edit in plugin editor">
            <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
            </svg>
        </a>
        <button class="step-dup-btn" title="Duplicate step">
            <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
            </svg>
        </button>
        <button class="step-delete" title="Remove step">
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
        </button>`;

    li.querySelector('.step-checkbox').addEventListener('change', e => {
        li.classList.toggle('step-disabled', !e.target.checked);
        pushHistoryAndSave();
    });
    li.querySelector('.step-note').addEventListener('change', pushHistoryAndSave);
    li.querySelectorAll('.step-arg-input').forEach(input => {
        input.addEventListener('change', pushHistoryAndSave);
    });
    li.querySelector('.step-dup-btn').addEventListener('click', () => {
        const dupArgs = {};
        li.querySelectorAll('.step-arg-input').forEach(input => {
            const t = input.dataset.argType;
            dupArgs[input.dataset.arg] = t === 'bool' ? input.checked
                                       : t === 'int'  ? parseInt(input.value, 10)
                                       :                parseFloat(input.value);
        });
        const copy = createStepEl({
            pluginKey:   li.dataset.pluginKey,
            description: li.querySelector('.step-note').value,
            isChecked:   li.querySelector('.step-checkbox').checked,
            args:        dupArgs,
        });
        li.insertAdjacentElement('afterend', copy);
        updateEmptyState();
        pushHistoryAndSave();
    });
    li.querySelector('.step-delete').addEventListener('click', () => {
        li.remove(); updateEmptyState(); pushHistoryAndSave();
    });
    return li;
}

function getSequence() {
    return Array.from(el.scriptList.children).map(li => {
        const args = {};
        li.querySelectorAll('.step-arg-input').forEach(input => {
            const name = input.dataset.arg;
            const type = input.dataset.argType;
            if (type === 'bool') {
                args[name] = input.checked;
            } else if (type === 'int') {
                args[name] = parseInt(input.value, 10);
            } else {
                args[name] = parseFloat(input.value);
            }
        });
        return {
            pluginKey:   li.dataset.pluginKey,
            description: li.querySelector('.step-note').value,
            isChecked:   li.querySelector('.step-checkbox').checked,
            args,
        };
    });
}

function renderSequence(steps) {
    el.scriptList.innerHTML = '';
    steps.forEach(s => el.scriptList.appendChild(createStepEl(s)));
    updateEmptyState();
}

function updateEmptyState() {
    const empty = el.scriptList.children.length === 0;
    el.emptyState.classList.toggle('visible', empty);
    if (empty) el.playAll.disabled = true;
}

// ── Split-pane drag ────────────────────────────────────────────────────────

function initSplitDrag() {
    el.splitHandle.addEventListener('mousedown', e => {
        e.preventDefault();
        const onMove = ev => {
            const rect = el.splitContainer.getBoundingClientRect();
            const pct  = Math.max(15, Math.min(85,
                (ev.clientX - rect.left) / rect.width * 100));
            el.splitLeft.style.width = `${pct}%`;
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', () =>
            document.removeEventListener('mousemove', onMove), { once: true });
    });
}

// ── Workflow canvas pan ────────────────────────────────────────────────────

let canvasDX = 0;
let canvasDY = 0;

function applyCanvasTransform() {
    el.workflowCanvas.style.transform = `translate(${canvasDX}px, ${canvasDY}px)`;
}

function clampCanvasOffset(dx, dy) {
    const vp       = el.workflowPaneContent;
    const vpW      = vp.clientWidth;
    // Subtract fixed console height so steps don't get buried under it
    const consoleH = el.consoleToolbar ? el.consoleToolbar.offsetHeight : 110;
    const vpH      = vp.clientHeight - consoleH;
    const cW       = el.workflowCanvas.scrollWidth;
    const cH       = el.workflowCanvas.scrollHeight;
    const extraPad = Math.round(Math.min(vpW, vpH) * 0.5);

    return {
        dx: Math.max(vpW - cW - extraPad, Math.min(extraPad, dx)),
        dy: Math.max(vpH - cH - extraPad, Math.min(extraPad, dy)),
    };
}

function initCanvasPan() {
    let panStartX, panStartY, panStartDX, panStartDY;

    const noGo = e =>
        e.target.closest('li')                  ||
        e.target.closest('#add-global-step')    ||
        e.target.closest('.plugin-dropdown')    ||
        e.target.closest('.plugin-search-wrap') ||
        e.button !== 0;

    const onMove = e => {
        const { dx, dy } = clampCanvasOffset(
            panStartDX + (e.clientX - panStartX),
            panStartDY + (e.clientY - panStartY),
        );
        canvasDX = dx;
        canvasDY = dy;
        applyCanvasTransform();
    };

    const onUp = () => {
        el.workflowPaneContent.classList.remove('panning');
        document.removeEventListener('mousemove', onMove);
    };

    el.workflowPaneContent.addEventListener('mousedown', e => {
        if (noGo(e)) return;
        e.preventDefault();
        panStartX  = e.clientX;
        panStartY  = e.clientY;
        panStartDX = canvasDX;
        panStartDY = canvasDY;
        el.workflowPaneContent.classList.add('panning');
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp, { once: true });
    });

    // Re-clamp when the pane or window is resized
    new ResizeObserver(() => {
        const c = clampCanvasOffset(canvasDX, canvasDY);
        if (c.dx !== canvasDX || c.dy !== canvasDY) {
            canvasDX = c.dx; canvasDY = c.dy;
            applyCanvasTransform();
        }
    }).observe(el.workflowPaneContent);
}

// ── File preview ───────────────────────────────────────────────────────────

const PREVIEW_MAX_LINES = 2000;
let fileEditTimer = null;
let fileEditSavePromise = null;

function updateFileEditControls() {
    if (!el.applyFileEditBtn) return;
    el.applyFileEditBtn.disabled = !state.fileEditDirty || state.fileEditSaving;
    el.fileEditStatus.textContent = state.fileEditSaving
        ? 'Saving…'
        : state.fileEditDirty ? 'Unsaved edits' : '';
}

async function saveFileEdits() {
    clearTimeout(fileEditTimer);
    if (state.fileEditSaving) return fileEditSavePromise;
    if (!state.fileEditDirty || el.filePreview.readOnly) return;

    const content = el.filePreview.value;
    state.fileEditSaving = true;
    updateFileEditControls();
    fileEditSavePromise = (async () => {
        try {
            const r = await fetch(`${API_BASE}/update_file`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_dir: state.sessionDir,
                    filename: state.outputFilename,
                    content,
                }),
            });
            const d = await r.json();
            if (!r.ok) throw new Error(d.error || 'Save failed');
            if (el.filePreview.value === content) state.fileEditDirty = false;
            await refreshFileUndoRedoButtons();
        } catch (e) {
            log('File edit failed: ' + e.message, 'error');
        } finally {
            state.fileEditSaving = false;
            updateFileEditControls();
            if (state.fileEditDirty) fileEditTimer = setTimeout(saveFileEdits, 700);
        }
    })();
    try {
        await fileEditSavePromise;
    } finally {
        fileEditSavePromise = null;
    }
}

async function refreshFilePreview(force = false) {
    if (!state.sessionDir || !state.outputFilename || state.isBatchSession) {
        clearTimeout(fileEditTimer);
        state.fileEditDirty = false;
        el.filePreview.style.display          = 'none';
        el.filePreviewTruncation.style.display = 'none';
        el.filePreviewEmpty.style.display     = '';
        updateFileEditControls();
        return;
    }
    if (state.fileEditDirty && !force) return;
    try {
        const r = await fetch(
            `${API_BASE}/preview_file`
            + `?session_dir=${encodeURIComponent(state.sessionDir)}`
            + `&filename=${encodeURIComponent(state.outputFilename)}`
            + `&full=1`
        );
        const d = await r.json();
        if (d.error) { return; }

        if (d.type === 'text') {
            el.filePreview.value                  = d.content;
            el.filePreview.readOnly               = false;
            el.filePreview.style.display          = '';
            el.filePreviewEmpty.style.display     = 'none';
            if (d.truncated) {
                el.filePreviewTruncation.textContent  =
                    `Showing first ${PREVIEW_MAX_LINES.toLocaleString()} of ${d.total_lines.toLocaleString()} lines`;
                el.filePreviewTruncation.style.display = '';
            } else {
                el.filePreviewTruncation.style.display = 'none';
            }
        } else {
            el.filePreview.value                  = `[${d.mime_type}  ·  ${fmtBytes(d.size)}]\n\nBinary files cannot be edited as text.`;
            el.filePreview.readOnly               = true;
            el.filePreview.style.display          = '';
            el.filePreviewEmpty.style.display     = 'none';
            el.filePreviewTruncation.style.display = 'none';
        }
        state.fileEditDirty = false;
        updateFileEditControls();
    } catch (_) {}
}

// ── File-content history ───────────────────────────────────────────────────

async function refreshFileUndoRedoButtons() {
    const available = !state.isBatchSession && state.sessionDir && state.outputFilename;
    if (!available) {
        el.fileUndoBtn.disabled = true;
        el.fileRedoBtn.disabled = true;
        el.fileUndoBtn.classList.remove('at-limit');
        return;
    }
    try {
        const s = await (await fetch(
            `${API_BASE}/file_history/status`
            + `?session_dir=${encodeURIComponent(state.sessionDir)}`
            + `&filename=${encodeURIComponent(state.outputFilename)}`
        )).json();
        el.fileUndoBtn.disabled = !s.can_undo;
        el.fileRedoBtn.disabled = !s.can_redo;
        const atLimit = !s.can_undo && s.hit_limit;
        el.fileUndoBtn.classList.toggle('at-limit', atLimit);
        el.fileUndoBtn.title = atLimit
            ? 'History limit reached — oldest states were dropped'
            : 'Undo file change';
    } catch (_) {}
}

async function performFileUndo() {
    if (!state.sessionDir || !state.outputFilename) return;
    if (state.fileEditDirty) await saveFileEdits();
    try {
        const r = await fetch(`${API_BASE}/file_history/undo`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ session_dir: state.sessionDir, filename: state.outputFilename }),
        });
        if (!r.ok) { log('Nothing to undo.', 'warn'); return; }
        await refreshFileUndoRedoButtons();
        refreshFilePreview(true);
        log('File undone.', 'info');
    } catch (e) { log('File undo failed: ' + e.message, 'error'); }
}

async function performFileRedo() {
    if (!state.sessionDir || !state.outputFilename) return;
    if (state.fileEditDirty) await saveFileEdits();
    try {
        const r = await fetch(`${API_BASE}/file_history/redo`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ session_dir: state.sessionDir, filename: state.outputFilename }),
        });
        if (!r.ok) { log('Nothing to redo.', 'warn'); return; }
        await refreshFileUndoRedoButtons();
        refreshFilePreview(true);
        log('File redone.', 'info');
    } catch (e) { log('File redo failed: ' + e.message, 'error'); }
}

async function resetFileHistory() {
    if (!state.sessionDir) return;
    try {
        await fetch(`${API_BASE}/file_history/reset`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ session_dir: state.sessionDir }),
        });
    } catch (_) {}
    await refreshFileUndoRedoButtons();
}

// ── History / autosave ─────────────────────────────────────────────────────

async function autosave() {
    try {
        await fetch(`${API_BASE}/save`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify(getSequence()),
        });
    } catch (_) {}
}

async function pushHistoryAndSave() {
    autosave();
    try {
        await fetch(`${API_BASE}/history/push`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify(getSequence()),
        });
        await refreshUndoRedoButtons();
    } catch (_) {}
}

async function refreshUndoRedoButtons() {
    try {
        const s = await (await fetch(`${API_BASE}/history/status`)).json();
        el.undoBtn.disabled = !s.can_undo;
        el.redoBtn.disabled = !s.can_redo;
    } catch (_) {}
}

async function performUndo() {
    try {
        const r = await fetch(`${API_BASE}/history/undo`);
        if (!r.ok) { log('Nothing to undo.', 'warn'); return; }
        renderSequence((await r.json()).state);
        autosave(); await refreshUndoRedoButtons(); log('Undone.', 'info');
    } catch (e) { log('Undo failed: ' + e.message, 'error'); }
}

async function performRedo() {
    try {
        const r = await fetch(`${API_BASE}/history/redo`);
        if (!r.ok) { log('Nothing to redo.', 'warn'); return; }
        renderSequence((await r.json()).state);
        autosave(); await refreshUndoRedoButtons(); log('Redone.', 'info');
    } catch (e) { log('Redo failed: ' + e.message, 'error'); }
}

// ── Output management ──────────────────────────────────────────────────────

function fmtBytes(bytes) {
    if (bytes < 1024)        return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function updateOutputState() {
    const batchReady  = state.isBatchSession && state.batchRunDone;
    const singleReady = !!(state.sessionDir && state.outputFilename && !state.isBatchSession);
    const ready = batchReady || singleReady;
    el.exportBtn.disabled = !ready;
    if (batchReady) {
        el.outputFilename.textContent = `${state.batchFiles.length} files processed`;
        el.outputFilename.classList.add('named');
    } else if (singleReady) {
        el.outputFilename.textContent = state.outputFilename;
        el.outputFilename.classList.toggle('named', true);
    } else {
        el.outputFilename.textContent = '';
        el.outputFilename.classList.remove('named');
    }
}

function saveOutput() {
    if (state.isBatchSession) {
        if (!state.batchRunDone || !state.sessionDir) return;
        const url = `${API_BASE}/download_batch?session_dir=${encodeURIComponent(state.sessionDir)}`;
        const a   = document.createElement('a');
        a.href = url; a.download = `${state.sessionDir}_output.zip`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        log(`Downloading batch zip…`, 'success');
        return;
    }
    if (!state.sessionDir || !state.outputFilename) return;
    const url = `${API_BASE}/download_output`
        + `?session_dir=${encodeURIComponent(state.sessionDir)}`
        + `&filename=${encodeURIComponent(state.outputFilename)}`;
    const a = document.createElement('a');
    a.href = url; a.download = state.outputFilename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    log(`Downloading: ${state.outputFilename}`, 'success');
}

async function saveOutputAs() {
    if (state.isBatchSession) { saveOutput(); return; }
    if (!state.sessionDir || !state.outputFilename) return;
    const url = `${API_BASE}/download_output`
        + `?session_dir=${encodeURIComponent(state.sessionDir)}`
        + `&filename=${encodeURIComponent(state.outputFilename)}`;
    if ('showSaveFilePicker' in window) {
        try {
            const ext = state.outputFilename.split('.').pop();
            const fh  = await window.showSaveFilePicker({
                suggestedName: state.outputFilename,
                types: [{ description: 'Output file', accept: { '*/*': [`.${ext}`] } }],
            });
            const blob = await (await fetch(url)).blob();
            const ws   = await fh.createWritable();
            await ws.write(blob); await ws.close();
            log(`Saved: ${fh.name}`, 'success');
        } catch (e) { if (e.name !== 'AbortError') log('Save As failed: ' + e.message, 'error'); }
    } else { saveOutput(); }
}

// ── Preset management ──────────────────────────────────────────────────────

function updatePresetFilenameDisplay() {
    if (state.currentPresetName) {
        el.presetFilename.textContent = state.currentPresetName;
        el.presetFilename.classList.add('named');
    } else {
        el.presetFilename.textContent = 'unsaved';
        el.presetFilename.classList.remove('named');
    }
}

async function savePreset() {
    if (!state.currentPresetName) { openPresetSaveAsBar(); return; }
    try {
        const r = await fetch(`${API_BASE}/save_preset`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ filename: state.currentPresetName, scripts: getSequence() }),
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        log(`Preset saved → ${state.currentPresetName}`, 'success');
    } catch (e) { log('Save preset failed: ' + e.message, 'error'); }
}

function openPresetSaveAsBar() {
    el.presetSaveAsBar.classList.add('open');
    el.presetSaveAsInput.value = state.currentPresetName || '';
    el.presetSaveAsInput.focus(); el.presetSaveAsInput.select();
}
function closePresetSaveAsBar() { el.presetSaveAsBar.classList.remove('open'); }

async function confirmPresetSaveAs() {
    let name = el.presetSaveAsInput.value.trim();
    if (!name) return;
    if (!name.endsWith('.json')) name += '.json';
    try {
        const r = await fetch(`${API_BASE}/save_preset`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ filename: name, scripts: getSequence() }),
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        state.currentPresetName = d.filename;
        updatePresetFilenameDisplay();
        log(`Preset saved as → ${d.filename}`, 'success');
        closePresetSaveAsBar();
    } catch (e) { log('Save As failed: ' + e.message, 'error'); }
}

async function loadPresetFromPicker(file) {
    try {
        const steps = JSON.parse(await file.text());
        renderSequence(steps);
        state.currentPresetName = file.name;
        updatePresetFilenameDisplay();
        await pushHistoryAndSave();
        recordPresetEvent(file.name, 'loaded');
        log(`Preset loaded: ${file.name}`, 'success');
    } catch (e) { log('Load failed: ' + e.message, 'error'); }
}

async function recordPresetEvent(filename, event) {
    try {
        await fetch(`${API_BASE}/preset_event`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ filename, event }),
        });
    } catch (_) {}
}

// ── Preset Library ─────────────────────────────────────────────────────────

async function openPresetLibrary() {
    state.presetLibraryOpen = true;
    el.presetLibraryOverlay.classList.add('open');
    el.presetLibraryBody.innerHTML = '<div class="modal-loading">Loading…</div>';
    try {
        state.cachedPresets = await (await fetch(`${API_BASE}/list_presets`)).json();
    } catch (e) {
        el.presetLibraryBody.innerHTML = `<div class="modal-loading">Failed: ${e.message}</div>`;
        return;
    }
    renderPresetLibrary();
}

function closePresetLibrary() {
    state.presetLibraryOpen = false;
    el.presetLibraryOverlay.classList.remove('open');
}

function sortPresets(presets, by) {
    return [...presets].sort((a, b) => {
        if (by === 'uses')         return (b.uses || 0) - (a.uses || 0);
        if (by === 'success_rate') return (b.success_rate ?? -1) - (a.success_rate ?? -1);
        if (by === 'last_used')    return (b.last_used || '').localeCompare(a.last_used || '');
        if (by === 'name')         return a.filename.localeCompare(b.filename);
        return 0;
    });
}

function isSkillCandidate(p) {
    return p.uses >= 5 && p.success_rate != null && p.success_rate >= 0.8;
}

function renderPresetLibrary() {
    const presets = sortPresets(state.cachedPresets, el.presetSortSelect.value);
    if (presets.length === 0) {
        el.presetLibraryBody.innerHTML =
            '<div class="modal-empty">No presets saved yet. Build a pipeline and hit Save.</div>';
        return;
    }
    el.presetLibraryBody.innerHTML = '';
    presets.forEach(p => {
        const card = document.createElement('div');
        card.className = 'preset-card' + (isSkillCandidate(p) ? ' preset-card-star' : '');
        const name = p.filename.replace(/\.json$/, '');
        const pct  = p.success_rate != null ? `${Math.round(p.success_rate * 100)}%` : '—';
        const last = p.last_used ? new Date(p.last_used).toLocaleDateString() : 'Never';
        card.innerHTML = `
            <div class="preset-card-body">
                <div class="preset-card-name">
                    ${name}
                    ${isSkillCandidate(p) ? `<span class="skill-badge" title="≥5 uses, ≥80% success — strong candidate for a reusable skill">★ Skill</span>` : ''}
                </div>
                <div class="preset-card-meta">
                    <span>${p.step_count} step${p.step_count !== 1 ? 's' : ''}</span>
                    <span class="meta-dot">·</span>
                    <span>${p.uses} use${p.uses !== 1 ? 's' : ''}</span>
                    <span class="meta-dot">·</span>
                    <span>${pct} success</span>
                    <span class="meta-dot">·</span>
                    <span>Last: ${last}</span>
                </div>
                ${p.uses > 0 ? `<div class="preset-card-bar"><div class="preset-card-bar-fill" style="width:${Math.round((p.success_rate||0)*100)}%"></div></div>` : ''}
            </div>
            <button class="preset-card-load" data-filename="${p.filename}">Load</button>`;
        card.querySelector('.preset-card-load').addEventListener('click', async () => {
            try {
                const resp = await fetch(`${API_BASE}/presets/${encodeURIComponent(p.filename)}`);
                if (!resp.ok) throw new Error('Not found');
                renderSequence(await resp.json());
                state.currentPresetName = p.filename;
                updatePresetFilenameDisplay();
                await pushHistoryAndSave();
                await recordPresetEvent(p.filename, 'loaded');
                p.uses += 1; p.last_used = new Date().toISOString();
                log(`Preset loaded: ${name}`, 'success');
                closePresetLibrary();
            } catch (e) { log('Failed to load preset: ' + e.message, 'error'); }
        });
        el.presetLibraryBody.appendChild(card);
    });
}

// ── Choose Plugins panel ───────────────────────────────────────────────────

function openChoosePlugins() {
    if (state.chooseOpen) { closeChoosePlugins(); return; }
    state.chooseTagFilter   = null;
    el.chooseSearch.value   = '';
    renderChooseTagBar();
    renderChooseList();
    el.choosePluginsPanel.classList.add('open');
    state.chooseOpen = true;
    el.chooseSearch.focus();
}

function closeChoosePlugins() {
    el.choosePluginsPanel.classList.remove('open');
    state.chooseOpen = false;
}

function renderChooseTagBar() {
    const tags = [...new Set(state.pluginCache.flatMap(p => p.tags || []))].sort();
    el.chooseTagBar.innerHTML = '';
    if (!tags.length) { el.chooseTagBar.style.display = 'none'; return; }
    el.chooseTagBar.style.display = 'flex';

    const makeChip = (label, value) => {
        const btn = document.createElement('button');
        btn.className = 'tag-chip' + (state.chooseTagFilter === value ? ' active' : '');
        btn.textContent = label;
        btn.addEventListener('click', () => {
            state.chooseTagFilter = state.chooseTagFilter === value ? null : value;
            renderChooseTagBar();
            renderChooseList();
        });
        return btn;
    };
    el.chooseTagBar.appendChild(makeChip('all', null));
    tags.forEach(t => el.chooseTagBar.appendChild(makeChip(t, t)));
}

function renderChooseList() {
    const q   = (el.chooseSearch.value || '').toLowerCase();
    const tag = state.chooseTagFilter;

    const visible = state.pluginCache.filter(p => {
        const matchTag    = !tag || (p.tags||[]).includes(tag);
        const matchSearch = !q
            || p.key.toLowerCase().includes(q)
            || (p.label||'').toLowerCase().includes(q)
            || (p.description||'').toLowerCase().includes(q);
        return matchTag && matchSearch;
    });

    el.chooseList.innerHTML = '';
    if (!visible.length) {
        el.chooseList.innerHTML = '<div class="plugin-empty">No plugins match.</div>';
        return;
    }

    visible.forEach(p => {
        const li      = document.createElement('li');
        const active  = !state.sessionPlugins || state.sessionPlugins.has(p.key);
        li.className  = 'choose-item';

        li.innerHTML = `
            <label class="choose-item-label">
                <input type="checkbox" class="choose-checkbox" ${active ? 'checked' : ''}>
                <div class="choose-item-body">
                    <span class="plugin-item-label">${p.label || p.key}</span>
                    <span class="plugin-item-key">${p.key}</span>
                    ${p.description ? `<span class="plugin-item-desc">${p.description}</span>` : ''}
                </div>
            </label>
            <button class="plugin-edit-btn" title="Edit ${p.key}.py">
                <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                </svg>
            </button>`;

        li.querySelector('.choose-checkbox').addEventListener('change', e => {
            toggleSessionPlugin(p.key, e.target.checked);
        });
        li.querySelector('.plugin-edit-btn').addEventListener('click', e => {
            e.stopPropagation();
            openPluginEditor(`${p.key}.py`);
        });
        el.chooseList.appendChild(li);
    });

    updateChooseFooter();
}

function toggleSessionPlugin(key, checked) {
    if (checked) {
        // If we have a restriction set, add to it; otherwise no-op (all already active)
        if (state.sessionPlugins) state.sessionPlugins.add(key);
    } else {
        // Adding a restriction: if no set yet, create one with all-but-this
        if (!state.sessionPlugins) {
            state.sessionPlugins = new Set(state.pluginCache.map(p => p.key));
        }
        state.sessionPlugins.delete(key);
        if (state.sessionPlugins.size === state.pluginCache.length) {
            state.sessionPlugins = null; // back to "all"
        }
    }
    updateChooseFooter();
    updateChoosePluginsBtn();
    updateAddStepLabel();
}

function clearSessionPlugins() {
    state.sessionPlugins = null;
    renderChooseList();
    updateChoosePluginsBtn();
    updateAddStepLabel();
}

function updateChooseFooter() {
    if (!state.sessionPlugins) {
        el.chooseCount.textContent = 'All available';
    } else {
        const n = state.sessionPlugins.size;
        el.chooseCount.textContent = `${n} of ${state.pluginCache.length} selected`;
    }
}

function updateChoosePluginsBtn() {
    if (state.sessionPlugins) {
        el.choosePluginsBadge.textContent = state.sessionPlugins.size;
        el.choosePluginsBadge.style.display = '';
        el.choosePluginsBtn.classList.add('choose-active');
    } else {
        el.choosePluginsBadge.style.display = 'none';
        el.choosePluginsBtn.classList.remove('choose-active');
    }
}

function updateAddStepLabel() {
    if (state.sessionPlugins) {
        const n = state.functionCache.filter(p => state.sessionPlugins.has(p.module || p.key)).length;
        el.addStepLabel.textContent = `Add Step  (${n} available)`;
    } else {
        el.addStepLabel.textContent = 'Add Processing Step';
    }
}

// ── Add Processing Step picker ─────────────────────────────────────────────

async function openPluginDropdown() {
    if (state.pluginDropdownOpen) { closePluginDropdown(); return; }
    try {
        const r = await fetch(`${API_BASE}/list_functions`);
        state.functionCache = await r.json();
    } catch (e) { log('Could not load plugin functions: ' + e.message, 'error'); return; }

    el.pluginSearch.value = '';
    renderTagBar();
    renderPluginList(filteredForAddStep(state.functionCache));

    el.pluginDropdown.classList.add('open');
    state.pluginDropdownOpen = true;
    el.pluginSearch.focus();
}

function closePluginDropdown() {
    el.pluginDropdown.classList.remove('open');
    state.pluginDropdownOpen = false;
}

function filteredForAddStep(fns) {
    const q   = (el.pluginSearch.value || '').toLowerCase();
    const tag = state.addStepTagFilter;

    return fns.filter(p => {
        // sessionPlugins tracks module keys; functions are filtered by their parent module
        const inSession   = !state.sessionPlugins || state.sessionPlugins.has(p.module || p.key);
        const matchesTag  = !tag || (p.tags||[]).includes(tag);
        const matchSearch = !q
            || p.key.toLowerCase().includes(q)
            || (p.label||'').toLowerCase().includes(q)
            || (p.description||'').toLowerCase().includes(q)
            || (p.module||'').toLowerCase().includes(q)
            || (p.tags||[]).some(t => t.includes(q));
        return inSession && matchesTag && matchSearch;
    });
}

function renderTagBar() {
    // Tags from session-available functions only (filter by parent module)
    const available = state.sessionPlugins
        ? state.functionCache.filter(p => state.sessionPlugins.has(p.module || p.key))
        : state.functionCache;
    const tags = [...new Set(available.flatMap(p => p.tags || []))].sort();
    el.tagBar.innerHTML = '';
    if (!tags.length) { el.tagBar.style.display = 'none'; return; }
    el.tagBar.style.display = 'flex';

    const makeChip = (label, value) => {
        const chip = document.createElement('button');
        chip.className = 'tag-chip' + (state.addStepTagFilter === value ? ' active' : '');
        chip.textContent = label;
        chip.addEventListener('click', () => {
            state.addStepTagFilter = state.addStepTagFilter === value ? null : value;
            renderTagBar();
            renderPluginList(filteredForAddStep(state.functionCache));
        });
        return chip;
    };
    el.tagBar.appendChild(makeChip('all', null));
    tags.forEach(t => el.tagBar.appendChild(makeChip(t, t)));
}

function renderPluginList(plugins) {
    el.pluginList.innerHTML = '';
    if (!plugins.length) {
        el.pluginList.innerHTML = '<div class="plugin-empty">No matching plugins.</div>';
        return;
    }
    plugins.forEach(p => {
        const li        = document.createElement('li');
        const mimeMatch = !state.selectedFileMime || !p.accepts || !p.accepts.length
            || p.accepts.includes(state.selectedFileMime) || p.accepts.includes('*/*');
        const depOk     = p.deps_ok !== false;

        li.className = 'plugin-item'
            + (mimeMatch ? '' : ' plugin-mime-mismatch')
            + (depOk     ? '' : ' plugin-dep-missing');

        const countBadge = (p.func_count > 1)
            ? `<span class="plugin-badge badge-ops">${p.func_count} ops</span>`
            : '';
        const subtitle = p.module ? p.module : p.key;
        li.innerHTML = `
            <div class="plugin-item-body">
                <div class="plugin-item-label">
                    ${p.label || p.key}
                    ${countBadge}
                    ${!mimeMatch ? `<span class="plugin-badge badge-mime">type mismatch</span>` : ''}
                    ${!depOk    ? `<span class="plugin-badge badge-dep" title="Missing: ${(p.missing_deps||[]).join(', ')}">missing deps</span>` : ''}
                </div>
                <div class="plugin-item-key">${subtitle}</div>
                ${p.description ? `<div class="plugin-item-desc">${p.description}</div>` : ''}
                ${(p.tags||[]).length ? `<div class="plugin-item-tags">${p.tags.map(t=>`<span class="tag-label">${t}</span>`).join('')}</div>` : ''}
            </div>
            <button class="plugin-edit-btn" title="Edit ${p.key}.py">
                <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                </svg>
            </button>
            <svg class="plugin-item-arrow" width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>`;

        li.querySelector('.plugin-edit-btn').addEventListener('click', e => {
            e.stopPropagation();
            openPluginEditor(`${p.key}.py`);
        });
        li.addEventListener('click', () => {
            el.scriptList.appendChild(createStepEl({ pluginKey: p.key }));
            updateEmptyState(); pushHistoryAndSave(); closePluginDropdown();
        });
        el.pluginList.appendChild(li);
    });
}

// ── Settings panel ─────────────────────────────────────────────────────────

let settingsOpen = false;

async function openSettings() {
    if (settingsOpen) { closeSettings(); return; }
    settingsOpen = true;
    el.settingsPanel.classList.add('open');
    el.settingsBody.innerHTML = '<div class="settings-loading">Loading…</div>';

    let d;
    try {
        d = await (await fetch(`${API_BASE}/settings_info`)).json();
    } catch (e) {
        el.settingsBody.innerHTML = `<div class="settings-loading">Could not load settings.</div>`;
        return;
    }

    const apiStatus = d.api_key_set
        ? `<span class="settings-status ok">✓ Set</span>`
        : `<span class="settings-status warn">✗ Not set</span>`;

    el.settingsBody.innerHTML = `
        <div class="settings-section">Workspace</div>
        <div class="settings-row settings-edit-row">
            <input class="settings-input" id="wsInput" type="text"
                   value="${d.workspace.replace(/"/g, '&quot;')}" spellcheck="false">
            <button class="settings-save-btn" id="wsSaveBtn">Save</button>
        </div>
        <div class="settings-section">Claude API Key</div>
        <div class="settings-row settings-edit-row">
            <input class="settings-input" id="apiInput" type="password"
                   placeholder="${d.api_key_set ? '(stored — paste to replace)' : 'sk-ant-api…'}"
                   spellcheck="false">
            <button class="settings-save-btn" id="apiSaveBtn">Save</button>
        </div>
        <div class="settings-row">
            <span class="settings-key">Status</span>
            ${apiStatus}
        </div>
        <div class="settings-section">File History</div>
        <div class="settings-row settings-edit-row">
            <label class="settings-key" for="fileUndoLimitInput">Undo limit</label>
            <input class="settings-input" id="fileUndoLimitInput" type="number"
                   min="1" max="100" value="${d.file_undo_limit}" style="width:70px">
            <button class="settings-save-btn" id="fileUndoLimitSaveBtn">Save</button>
        </div>
        <div class="settings-row">
            <span class="settings-meta">Max file snapshots kept in memory per file. Older states are dropped when the limit is reached.</span>
        </div>
        <div class="settings-section">Plugins</div>
        <div class="settings-row">
            <code class="settings-val">${d.plugin_dir}</code>
            <span class="settings-meta">${d.plugin_count} plugin${d.plugin_count !== 1 ? 's' : ''}</span>
        </div>
        `;

    function flashBtn(btn, ok) {
        btn.textContent = ok ? '✓' : '✗';
        btn.disabled = true;
        setTimeout(() => { btn.textContent = 'Save'; btn.disabled = false; }, 1600);
    }

    // Workspace
    const wsInput   = document.getElementById('wsInput');
    const wsSaveBtn = document.getElementById('wsSaveBtn');
    const saveWorkspace = async () => {
        const path = wsInput.value.trim();
        if (!path) return;
        try {
            const r = await fetch(`${API_BASE}/set_workspace`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path }),
            });
            flashBtn(wsSaveBtn, !(await r.json()).error);
        } catch (_) { flashBtn(wsSaveBtn, false); }
    };
    wsSaveBtn.addEventListener('click', saveWorkspace);
    wsInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveWorkspace(); });

    // API key
    const apiInput   = document.getElementById('apiInput');
    const apiSaveBtn = document.getElementById('apiSaveBtn');
    const saveApiKey = async () => {
        const key = apiInput.value.trim();
        if (!key) return;
        try {
            const r = await fetch(`${API_BASE}/set_api_key`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key }),
            });
            const result = await r.json();
            if (!result.error) {
                apiInput.value = '';
                apiInput.placeholder = '(stored — paste to replace)';
                const s = el.settingsBody.querySelector('.settings-status');
                if (s) { s.className = 'settings-status ok'; s.textContent = '✓ Set'; }
            }
            flashBtn(apiSaveBtn, !result.error);
        } catch (_) { flashBtn(apiSaveBtn, false); }
    };
    apiSaveBtn.addEventListener('click', saveApiKey);
    apiInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveApiKey(); });

    // File undo limit
    const fileUndoLimitInput   = document.getElementById('fileUndoLimitInput');
    const fileUndoLimitSaveBtn = document.getElementById('fileUndoLimitSaveBtn');
    const saveFileUndoLimit = async () => {
        const limit = parseInt(fileUndoLimitInput.value, 10);
        if (!limit || limit < 1) return;
        try {
            const r = await fetch(`${API_BASE}/set_file_undo_limit`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ limit }),
            });
            flashBtn(fileUndoLimitSaveBtn, !(await r.json()).error);
        } catch (_) { flashBtn(fileUndoLimitSaveBtn, false); }
    };
    fileUndoLimitSaveBtn.addEventListener('click', saveFileUndoLimit);
    fileUndoLimitInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveFileUndoLimit(); });
}

function closeSettings() {
    settingsOpen = false;
    el.settingsPanel.classList.remove('open');
}

// ── Plugin editor navigation ───────────────────────────────────────────────

function openPluginEditor(file) {
    const url = '/plugin-editor' + (file ? `?file=${encodeURIComponent(file)}` : '');
    window.open(url, '_blank');
}

// ── Filename rename modal ──────────────────────────────────────────────────

function splitFilename(name) {
    const dot  = name.lastIndexOf('.');
    return dot > 0
        ? { stem: name.slice(0, dot), ext: name.slice(dot) }
        : { stem: name, ext: '' };
}

function truncateFilename(name) {
    const { stem, ext } = splitFilename(name);
    return stem.slice(0, FILENAME_TRUNC_LEN) + ext;
}

function renameFile(file, newName) {
    return new File([file], newName, { type: file.type, lastModified: file.lastModified });
}

function showRenameDialog(file) {
    return new Promise(resolve => {
        const { stem, ext } = splitFilename(file.name);
        const suggested     = stem.slice(0, FILENAME_TRUNC_LEN);

        document.getElementById('renameModalTitle').textContent = 'Long filename detected';
        document.getElementById('renameModalBody').innerHTML = `
            <p class="rename-original"><code>${file.name}</code></p>
            <p class="rename-hint">This filename is ${file.name.length} characters — long names can hit OS path limits.
               Edit the stem below or keep the original.</p>
            <div class="rename-row">
                <input class="rename-stem-input" id="renameStemInput"
                       value="${suggested.replace(/"/g,'&quot;')}" spellcheck="false">
                <span class="rename-ext-label">${ext}</span>
            </div>
            <div class="rename-actions">
                <button class="rename-btn-primary" id="renameConfirm">Use this name</button>
                <button class="rename-btn-ghost"   id="renameKeep">Keep original</button>
            </div>`;

        el.renameModal.classList.add('open');
        const input = document.getElementById('renameStemInput');
        input.focus(); input.select();

        const finish = newFile => { el.renameModal.classList.remove('open'); resolve(newFile); };

        document.getElementById('renameConfirm').onclick = () => {
            const newStem = input.value.trim() || suggested;
            finish(renameFile(file, newStem + ext));
        };
        document.getElementById('renameKeep').onclick    = () => finish(file);
        el.renameModalClose.onclick                      = () => finish(file);

        input.addEventListener('keydown', e => {
            if (e.key === 'Enter')  { e.preventDefault(); document.getElementById('renameConfirm').click(); }
            if (e.key === 'Escape') { e.preventDefault(); finish(file); }
        }, { once: true });
    });
}

function showBatchRenameDialog(longFiles) {
    return new Promise(resolve => {
        const rows = longFiles.map(f => {
            const shortened = truncateFilename(f.name);
            return `<li class="rename-batch-row">
                <span class="rename-batch-orig">${f.name}</span>
                <span class="rename-arrow">→</span>
                <span class="rename-batch-new">${shortened}</span>
            </li>`;
        }).join('');

        document.getElementById('renameModalTitle').textContent = `${longFiles.length} long filename${longFiles.length !== 1 ? 's' : ''}`;
        document.getElementById('renameModalBody').innerHTML = `
            <p class="rename-hint">These filenames exceed ${FILENAME_WARN_LEN} characters and will be auto-shortened to
               ${FILENAME_TRUNC_LEN}-char stems. You can keep originals if you prefer.</p>
            <ul class="rename-batch-list">${rows}</ul>
            <div class="rename-actions">
                <button class="rename-btn-primary" id="renameConfirm">Auto-rename all</button>
                <button class="rename-btn-ghost"   id="renameKeep">Keep originals</button>
            </div>`;

        el.renameModal.classList.add('open');

        const finish = doRename => { el.renameModal.classList.remove('open'); resolve(doRename); };
        document.getElementById('renameConfirm').onclick = () => finish(true);
        document.getElementById('renameKeep').onclick    = () => finish(false);
        el.renameModalClose.onclick                      = () => finish(false);
    });
}

async function checkLongFilenames(files) {
    const longFiles = files.filter(f => f.name.length > FILENAME_WARN_LEN);
    if (!longFiles.length) return files;

    if (files.length === 1) {
        return [await showRenameDialog(files[0])];
    }

    const doRename = await showBatchRenameDialog(longFiles);
    if (!doRename) return files;
    return files.map(f => f.name.length > FILENAME_WARN_LEN ? renameFile(f, truncateFilename(f.name)) : f);
}

// ── Target file / Batch upload ─────────────────────────────────────────────

const WARN_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB
const WARN_FILE_COUNT = 50;
const ASSUMED_THROUGHPUT = 5 * 1024 * 1024; // 5 MB/s (conservative localhost estimate)
const FILENAME_WARN_LEN  = 60;             // chars; prompt user when filename exceeds this
const FILENAME_TRUNC_LEN = 40;             // max stem length after auto-truncation

async function handleFilesSelected(fileList) {
    let files = Array.from(fileList);
    if (!files.length) return;

    files = await checkLongFilenames(files);

    const totalBytes = files.reduce((s, f) => s + f.size, 0);
    const estSeconds = totalBytes / ASSUMED_THROUGHPUT;
    const needsWarn  = totalBytes > WARN_SIZE_BYTES || files.length > WARN_FILE_COUNT || estSeconds > 10;

    if (needsWarn) {
        state.pendingFiles = files;
        showBatchWarning(files.length, totalBytes, estSeconds);
    } else {
        startUpload(files);
    }
}

function showBatchWarning(count, totalBytes, estSeconds) {
    const est = estSeconds < 60
        ? `~${Math.ceil(estSeconds)}s`
        : `~${(estSeconds / 60).toFixed(1)} min`;
    el.batchWarnText.textContent =
        `${count} file${count !== 1 ? 's' : ''} · ${fmtBytes(totalBytes)} — estimated upload time ${est}. Continue?`;
    el.batchWarn.style.display     = '';
    el.batchProgress.style.display = 'none';
    el.batchStrip.style.display    = '';
}

function hideBatchStrip() {
    el.batchStrip.style.display    = 'none';
    el.batchWarn.style.display     = 'none';
    el.batchProgress.style.display = 'none';
}

async function startUpload(files) {
    if (state.fileEditDirty) await saveFileEdits();
    if (state.sessionDir) resetFileHistory();
    state.uploadAbortFlag = false;
    state.sessionDir      = null;
    state.outputFilename  = null;
    state.batchFiles      = [];
    state.isBatchSession  = files.length > 1;
    state.batchRunDone    = false;

    // Reset display
    state.selectedFile     = files[0];
    state.selectedFileMime = guessMime(files[0].name);
    el.batchWarn.style.display     = 'none';
    el.batchProgress.style.display = '';
    el.batchStrip.style.display    = '';

    const totalBytes = files.reduce((s, f) => s + f.size, 0);
    let bytesDone = 0;

    updateUploadProgress(0, files.length, 0, totalBytes);

    for (let i = 0; i < files.length; i++) {
        if (state.uploadAbortFlag) {
            log(`Upload aborted after ${i} of ${files.length} file(s).`, 'warn');
            break;
        }

        const file = files[i];
        el.batchProgressText.textContent = `Uploading ${i + 1}/${files.length}: ${file.name}`;

        const form = new FormData();
        form.append('file', file);
        if (state.sessionDir) form.append('session_dir', state.sessionDir);

        try {
            const data = await (await fetch(`${API_BASE}/upload`, { method: 'POST', body: form })).json();
            if (data.error) { log(`Upload failed (${file.name}): ${data.error}`, 'error'); continue; }
            if (!state.sessionDir) state.sessionDir = data.session_dir;
            state.batchFiles.push({ name: data.filename, size: file.size });
            bytesDone += file.size;
            updateUploadProgress(i + 1, files.length, bytesDone, totalBytes);
            if (!state.isBatchSession) state.outputFilename = data.filename;
        } catch (e) {
            log(`Upload failed (${file.name}): ${e.message}`, 'error');
        }
    }

    hideBatchStrip();
    updateOutputState();
    refreshFileUndoRedoButtons();
    refreshFilePreview();

    const n = state.batchFiles.length;
    if (n === 0) {
        log('No files were uploaded.', 'error');
    } else if (state.isBatchSession) {
        const names = state.batchFiles.map(f => f.name);
        el.fileDisplay.textContent = `${n} files (${fmtBytes(totalBytes)})`;
        el.fileDisplay.classList.add('named');
        log(`${n} file${n !== 1 ? 's' : ''} loaded: ${names.join(', ')}`, 'success');
        log('Run the pipeline to process all files, then Save Output to download a zip.', 'system');
    } else {
        el.fileDisplay.textContent = state.batchFiles[0].name;
        el.fileDisplay.classList.add('named');
        log(`Workspace ready: ${state.batchFiles[0].name}`, 'success');
    }
}

function updateUploadProgress(done, total, bytesDone, bytesTotal) {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    el.uploadBarFill.style.width       = `${pct}%`;
    el.batchProgressCount.textContent  = `${done}/${total} files · ${fmtBytes(bytesDone)} / ${fmtBytes(bytesTotal)}`;
}

function abortUpload() {
    state.uploadAbortFlag = true;
    state.pendingFiles    = [];
}

function cancelBatchWarn() {
    state.pendingFiles = [];
    hideBatchStrip();
}

// ── Run ────────────────────────────────────────────────────────────────────

async function executeSingleFile(filename, sessionDir, activeSteps) {
    const r = await fetch(`${API_BASE}/execute`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ filename, session_dir: sessionDir, scripts: activeSteps }),
    });
    return r.json();
}

async function runSequence() {
    if (state.fileEditDirty) await saveFileEdits();
    if (!state.sessionDir) { log('No file loaded. Select a file or folder first.', 'error'); return; }

    const activeSteps = getSequence().filter(s => s.isChecked);
    if (!activeSteps.length) { log('No active steps to run.', 'warn'); return; }

    const depErrors = activeSteps
        .map(s => state.functionCache.find(p => p.key === s.pluginKey)
                || state.pluginCache.find(p => p.key === s.pluginKey))
        .filter(p => p && p.deps_ok === false);
    if (depErrors.length) {
        depErrors.forEach(p => log(`'${p.label}' missing: ${p.missing_deps.join(', ')}`, 'warn'));
        log('Fix missing dependencies before running.', 'error');
        return;
    }

    el.playAll.disabled = true;
    state.batchRunDone  = false;

    if (state.isBatchSession) {
        const files  = state.batchFiles;
        let failures = 0;
        log(`Batch run: ${activeSteps.length} step(s) × ${files.length} file(s)…`);

        for (let i = 0; i < files.length; i++) {
            const f = files[i];
            el.playAll.innerHTML = `<svg width="13" height="13" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> ${i + 1}/${files.length}`;
            try {
                const result = await executeSingleFile(f.name, state.sessionDir, activeSteps);
                if (result.error) {
                    log(`  [${f.name}] Error: ${result.error}`, 'error');
                    if (result.trace) result.trace.split('\n').filter(l => l.trim()).forEach(l => log(`    ${l}`, 'error'));
                    failures++;
                } else {
                    (result.steps||[]).forEach(s => { if (s.warning) log(`  [${f.name}] ${s.step}: ${s.warning}`, 'warn'); });
                    log(`  [${f.name}] Done`, 'success');
                }
            } catch (e) {
                log(`  [${f.name}] Failed: ${e.message}`, 'error');
                failures++;
            }
        }

        el.playAll.disabled = false;
        el.playAll.innerHTML = `<svg width="13" height="13" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Run`;

        if (failures === 0) {
            log(`Batch complete — ${files.length} file(s) processed.`, 'success');
            log('Use "Save Output" to download a zip of all results.', 'system');
            state.batchRunDone = true;
            if (state.currentPresetName) recordPresetEvent(state.currentPresetName, 'success');
        } else {
            log(`Batch done with ${failures} failure(s).`, 'warn');
        }
        updateOutputState();
    } else {
        const filename = state.batchFiles[0]?.name || state.selectedFile?.name;
        if (!filename) { log('No file available.', 'error'); el.playAll.disabled = false; return; }
        log(`Running ${activeSteps.length} step(s) on ${filename}…`);
        try {
            const result = await executeSingleFile(filename, state.sessionDir, activeSteps);
            if (result.error) {
                log(`Error: ${result.error}`, 'error');
                if (result.trace) result.trace.split('\n').filter(l => l.trim()).forEach(l => log(`  ${l}`, 'error'));
                if (result.completed?.length) log(`Completed before failure: ${result.completed.join(', ')}`, 'warn');
            } else {
                (result.steps||[]).forEach(s => { if (s.warning) log(`  ${s.step}: ${s.warning}`, 'warn'); });
                log(`Done — ${result.message}  [${result.mime_type}]`, 'success');
                log('Use "Save Output" to download the result.', 'system');
                state.outputFilename = filename;
                updateOutputState();
                refreshFileUndoRedoButtons();
                refreshFilePreview();
                if (state.currentPresetName) recordPresetEvent(state.currentPresetName, 'success');
            }
        } catch (e) { log('Execution failed: ' + e.message, 'error'); }
        el.playAll.disabled = false;
    }
}

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {

    el = {
        scriptList:           document.getElementById('scriptList'),
        emptyState:           document.getElementById('emptyState'),
        fileDisplay:          document.getElementById('fileDisplay'),
        consoleContent:       document.getElementById('consoleContent'),
        consoleToolbar:       document.getElementById('consoleToolbar'),
        resizeHandle:         document.getElementById('resizeHandle'),
        filePicker:           document.getElementById('filePicker'),
        folderPicker:         document.getElementById('folderPicker'),
        // import dropdown
        importWrap:           document.getElementById('importWrap'),
        importBtn:            document.getElementById('importBtn'),
        importDropdown:       document.getElementById('importDropdown'),
        importFilesOpt:       document.getElementById('importFilesOpt'),
        importFolderOpt:      document.getElementById('importFolderOpt'),
        // settings
        settingsBtn:          document.getElementById('settingsBtn'),
        settingsPanel:        document.getElementById('settingsPanel'),
        settingsBody:         document.getElementById('settingsBody'),
        settingsWrap:         document.getElementById('settingsWrap'),
        // batch strip
        batchStrip:           document.getElementById('batchStrip'),
        batchWarn:            document.getElementById('batchWarn'),
        batchWarnText:        document.getElementById('batchWarnText'),
        batchProgress:        document.getElementById('batchProgress'),
        batchProgressText:    document.getElementById('batchProgressText'),
        batchProgressCount:   document.getElementById('batchProgressCount'),
        uploadBarFill:        document.getElementById('uploadBarFill'),
        // split panes
        splitContainer:       document.getElementById('splitContainer'),
        splitLeft:            document.getElementById('splitLeft'),
        splitRight:           document.getElementById('splitRight'),
        splitHandle:          document.getElementById('splitHandle'),
        // workflow canvas / viewport
        workflowPaneContent:  document.getElementById('workflowPaneContent'),
        workflowCanvas:       document.getElementById('workflowCanvas'),
        // file preview
        filePaneContent:      document.getElementById('filePaneContent'),
        filePreview:          document.getElementById('filePreview'),
        filePreviewEmpty:     document.getElementById('filePreviewEmpty'),
        filePreviewTruncation:document.getElementById('filePreviewTruncation'),
        applyFileEditBtn:     document.getElementById('applyFileEditBtn'),
        fileEditStatus:       document.getElementById('fileEditStatus'),
        // pane headers — workflow history
        undoBtn:              document.getElementById('undoBtn'),
        redoBtn:              document.getElementById('redoBtn'),
        // pane headers — file-content history
        fileUndoBtn:          document.getElementById('fileUndoBtn'),
        fileRedoBtn:          document.getElementById('fileRedoBtn'),
        exportBtn:            document.getElementById('exportBtn'),
        outputFilename:       document.getElementById('outputFilename'),
        // choose plugins
        choosePluginsBtn:     document.getElementById('choosePluginsBtn'),
        choosePluginsPanel:   document.getElementById('choosePluginsPanel'),
        choosePluginsBadge:   document.getElementById('choosePluginsBadge'),
        chooseSearch:         document.getElementById('chooseSearch'),
        chooseTagBar:         document.getElementById('chooseTagBar'),
        chooseList:           document.getElementById('chooseList'),
        chooseCount:          document.getElementById('chooseCount'),
        // preset bar
        presetLibraryBtn:     document.getElementById('presetLibraryBtn'),
        savePresetBtn:        document.getElementById('savePresetBtn'),
        savePresetAsBtn:      document.getElementById('savePresetAsBtn'),
        loadPresetBtn:        document.getElementById('loadPresetBtn'),
        presetFilePicker:     document.getElementById('presetFilePicker'),
        presetSaveAsBar:      document.getElementById('presetSaveAsBar'),
        presetSaveAsInput:    document.getElementById('presetSaveAsInput'),
        presetFilename:       document.getElementById('presetFilename'),
        // preset library
        presetLibraryOverlay: document.getElementById('presetLibraryOverlay'),
        presetLibraryBody:    document.getElementById('presetLibraryBody'),
        presetSortSelect:     document.getElementById('presetSortSelect'),
        // add step picker
        addStepBtn:           document.getElementById('add-global-step'),
        addStepLabel:         document.getElementById('addStepLabel'),
        pluginDropdown:       document.getElementById('pluginDropdown'),
        pluginSearch:         document.getElementById('pluginSearch'),
        pluginList:           document.getElementById('pluginList'),
        tagBar:               document.getElementById('tagBar'),
        // plugin panel buttons
        openPluginsFolderBtn: document.getElementById('openPluginsFolderBtn'),
        // run / console
        playAll:              document.getElementById('playAll'),
        consoleClear:         document.getElementById('consoleClear'),
        consoleCopy:          document.getElementById('consoleCopy'),
        consoleDebugToggle:   document.getElementById('consoleDebugToggle'),
        // rename modal
        renameModal:          document.getElementById('renameModal'),
        renameModalClose:     document.getElementById('renameModalClose'),
    };

    // Sortable
    if (typeof Sortable !== 'undefined') {
        Sortable.create(el.scriptList, {
            animation: 150, handle: '.step-drag-handle',
            ghostClass: 'sortable-ghost', dragClass: 'sortable-drag',
            onEnd: pushHistoryAndSave,
        });
    }

    // Console resize
    el.resizeHandle.addEventListener('mousedown', () => {
        const onMove = e => {
            const h = window.innerHeight - e.clientY;
            if (h >= 50 && h <= 400) el.consoleToolbar.style.height = `${h}px`;
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', () =>
            document.removeEventListener('mousemove', onMove), { once: true });
    });
    el.consoleClear.addEventListener('click', () => {
        el.consoleContent.innerHTML = '';
        log('Console cleared.', 'system');
    });
    el.consoleCopy.addEventListener('click', copyConsoleToClipboard);
    el.consoleDebugToggle.addEventListener('click', () => {
        if (_logSource) stopServerDebug(); else startServerDebug();
    });

    // File / folder pickers
    el.filePicker.addEventListener('change', e => {
        if (e.target.files.length) handleFilesSelected(e.target.files);
        e.target.value = '';
    });
    el.folderPicker.addEventListener('change', e => {
        if (e.target.files.length) handleFilesSelected(e.target.files);
        e.target.value = '';
    });

    // Import dropdown
    let importOpen = false;
    function openImportDropdown()  { importOpen = true;  el.importDropdown.classList.add('open'); el.importBtn.classList.add('open'); }
    function closeImportDropdown() { importOpen = false; el.importDropdown.classList.remove('open'); el.importBtn.classList.remove('open'); }
    el.importBtn.addEventListener('click', e => { e.stopPropagation(); importOpen ? closeImportDropdown() : openImportDropdown(); });
    el.importFilesOpt.addEventListener('click', () => { closeImportDropdown(); el.filePicker.click(); });
    el.importFolderOpt.addEventListener('click', () => { closeImportDropdown(); el.folderPicker.click(); });

    // Batch strip controls
    document.getElementById('batchWarnCancel').addEventListener('click',   cancelBatchWarn);
    document.getElementById('batchWarnContinue').addEventListener('click', () => {
        const files = state.pendingFiles;
        state.pendingFiles = [];
        startUpload(files);
    });
    document.getElementById('batchAbortBtn').addEventListener('click', abortUpload);

    el.exportBtn.addEventListener('click', saveOutputAs);

    // Settings panel
    el.settingsBtn.addEventListener('click', e => { e.stopPropagation(); openSettings(); });

    // Choose Plugins panel
    el.choosePluginsBtn.addEventListener('click', e => { e.stopPropagation(); openChoosePlugins(); });
    el.chooseSearch.addEventListener('input', renderChooseList);
    el.chooseSearch.addEventListener('keydown', e => { if (e.key === 'Escape') closeChoosePlugins(); });
    document.getElementById('clearChooseBtn').addEventListener('click', clearSessionPlugins);
    document.getElementById('newPluginTrigger').addEventListener('click', () => { closeChoosePlugins(); openPluginEditor(); });
    el.openPluginsFolderBtn.addEventListener('click', () => fetch(`${API_BASE}/open_plugins_folder`).catch(() => {}));

    // Preset bar
    el.presetLibraryBtn.addEventListener('click',  openPresetLibrary);
    el.savePresetBtn.addEventListener('click',     savePreset);
    el.savePresetAsBtn.addEventListener('click',   openPresetSaveAsBar);
    el.loadPresetBtn.addEventListener('click',     () => el.presetFilePicker.click());
    el.presetFilePicker.addEventListener('change', e => {
        if (e.target.files[0]) loadPresetFromPicker(e.target.files[0]);
        e.target.value = '';
    });
    document.getElementById('presetSaveAsConfirm').addEventListener('click', confirmPresetSaveAs);
    document.getElementById('presetSaveAsCancel').addEventListener('click',  closePresetSaveAsBar);
    el.presetSaveAsInput.addEventListener('keydown', e => {
        if (e.key === 'Enter')  confirmPresetSaveAs();
        if (e.key === 'Escape') closePresetSaveAsBar();
    });

    // Preset library
    document.getElementById('presetLibraryClose').addEventListener('click', closePresetLibrary);
    el.presetLibraryOverlay.addEventListener('click', e => { if (e.target === el.presetLibraryOverlay) closePresetLibrary(); });
    el.presetSortSelect.addEventListener('change', renderPresetLibrary);

    // Add Step picker
    el.undoBtn.addEventListener('click', performUndo);
    el.redoBtn.addEventListener('click', performRedo);
    el.fileUndoBtn.addEventListener('click', performFileUndo);
    el.fileRedoBtn.addEventListener('click', performFileRedo);
    el.applyFileEditBtn.addEventListener('click', saveFileEdits);
    el.filePreview.addEventListener('input', () => {
        state.fileEditDirty = true;
        updateFileEditControls();
        clearTimeout(fileEditTimer);
        fileEditTimer = setTimeout(saveFileEdits, 700);
    });
    el.filePreview.addEventListener('keydown', e => {
        if (e.key === 'Tab') {
            e.preventDefault();
            const start = el.filePreview.selectionStart;
            const end = el.filePreview.selectionEnd;
            el.filePreview.setRangeText('    ', start, end, 'end');
            el.filePreview.dispatchEvent(new Event('input'));
        }
    });
    el.addStepBtn.addEventListener('click', e => { e.stopPropagation(); openPluginDropdown(); });
    el.pluginSearch.addEventListener('input', () => renderPluginList(filteredForAddStep(state.functionCache)));
    el.pluginSearch.addEventListener('keydown', e => { if (e.key === 'Escape') closePluginDropdown(); });


    // Run
    el.playAll.addEventListener('click', runSequence);

    // Global close
    document.addEventListener('click', e => {
        if (state.pluginDropdownOpen &&
            !el.addStepBtn.contains(e.target) &&
            !el.pluginDropdown.contains(e.target))
            closePluginDropdown();
        if (state.chooseOpen &&
            !el.choosePluginsBtn.contains(e.target) &&
            !el.choosePluginsPanel.contains(e.target))
            closeChoosePlugins();
        if (settingsOpen &&
            !el.settingsWrap.contains(e.target))
            closeSettings();
        if (importOpen &&
            !el.importWrap.contains(e.target))
            closeImportDropdown();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
        const ctrl = e.ctrlKey || e.metaKey;
        const editingFile = e.target === el.filePreview;
        if (ctrl && e.key === 's' && editingFile) { e.preventDefault(); saveFileEdits(); return; }
        if (editingFile) return;
        if (ctrl && e.key === 'z' && !e.shiftKey) { e.preventDefault(); performUndo(); }
        if (ctrl && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); performRedo(); }
        if (ctrl && e.key === 's' && !e.shiftKey) { e.preventDefault(); saveOutput(); }
        if (ctrl && e.key === 's' &&  e.shiftKey) { e.preventDefault(); saveOutputAs(); }
        if (ctrl && e.key === 'p') { e.preventDefault(); savePreset(); }
        if (e.key === 'Escape') { closePresetLibrary(); closeChoosePlugins(); closeSettings(); closeImportDropdown(); el.renameModal.classList.remove('open'); }
    });

    // Boot
    try {
        const [steps, modules, fns] = await Promise.all([
            fetch(`${API_BASE}/load`).then(r => r.json()),
            fetch(`${API_BASE}/list_plugins`).then(r => r.json()).catch(() => []),
            fetch(`${API_BASE}/list_functions`).then(r => r.json()).catch(() => []),
        ]);
        state.pluginCache   = modules;
        state.functionCache = fns;
        renderSequence(steps);
        if (steps.length) log(`Restored ${steps.length} step(s) from last session.`);
    } catch (_) { log('No previous session found.', 'system'); }

    initSplitDrag();
    initCanvasPan();
    await refreshUndoRedoButtons();
    await refreshFileUndoRedoButtons();
    refreshFilePreview();
    updateOutputState();
    updatePresetFilenameDisplay();
    if (localStorage.getItem('serverDebug') === '1') startServerDebug();
    else updateDebugToggle();
    log('System ready.', 'system');
});
