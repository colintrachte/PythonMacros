/**
 * PY-AUTOMATE — scripts.js
 */

const API_BASE = 'http://localhost:5000';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
    selectedFile:       null,
    selectedFileMime:   null,
    sessionDir:         null,       // workspace session subfolder name
    outputFilename:     null,       // filename inside session dir
    currentPresetName:  null,
    pluginCache:        [],
    pluginDropdownOpen: false,
    activeTagFilter:    null,
};

// ── DOM refs ───────────────────────────────────────────────────────────────

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
        mkv: 'video/x-matroska',
        pdf: 'application/pdf',
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

// ── Step rendering ─────────────────────────────────────────────────────────

function createStepEl({ pluginKey, description = '', isChecked = true }) {
    const li = document.createElement('li');
    li.dataset.pluginKey = pluginKey;
    if (!isChecked) li.classList.add('step-disabled');

    const info    = state.pluginCache.find(p => p.key === pluginKey) || {};
    const label   = info.label || pluginKey;
    const depsOk  = info.deps_ok !== false;
    const missing = info.missing_deps || [];

    const depWarning = !depsOk
        ? `<div class="step-dep-warning" title="Missing: ${missing.join(', ')}">
               <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
               </svg>
               Missing deps
           </div>`
        : '';

    li.innerHTML = `
        <div class="step-drag-handle" title="Drag to reorder">
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
                ${depWarning}
            </div>
            <input type="text" class="step-note" value="${description.replace(/"/g, '&quot;')}" placeholder="Add a note…">
        </div>
        <button class="step-delete" title="Remove step">
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
        </button>
    `;

    li.querySelector('.step-checkbox').addEventListener('change', (e) => {
        li.classList.toggle('step-disabled', !e.target.checked);
        pushHistoryAndSave();
    });
    li.querySelector('.step-note').addEventListener('change', pushHistoryAndSave);
    li.querySelector('.step-delete').addEventListener('click', () => {
        li.remove();
        updateEmptyState();
        pushHistoryAndSave();
    });

    return li;
}

function getSequence() {
    return Array.from(el.scriptList.children).map(li => ({
        pluginKey:   li.dataset.pluginKey,
        description: li.querySelector('.step-note').value,
        isChecked:   li.querySelector('.step-checkbox').checked,
    }));
}

function renderSequence(steps) {
    el.scriptList.innerHTML = '';
    steps.forEach(step => el.scriptList.appendChild(createStepEl(step)));
    updateEmptyState();
}

function updateEmptyState() {
    el.emptyState.classList.toggle('visible', el.scriptList.children.length === 0);
}

// ── Autosave ───────────────────────────────────────────────────────────────

async function autosave() {
    try {
        await fetch(`${API_BASE}/save`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(getSequence()),
        });
    } catch (_) { /* silent */ }
}

// ── History ────────────────────────────────────────────────────────────────

async function pushHistoryAndSave() {
    autosave();
    try {
        await fetch(`${API_BASE}/history/push`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(getSequence()),
        });
        await refreshUndoRedoButtons();
    } catch (_) { /* non-critical */ }
}

async function refreshUndoRedoButtons() {
    try {
        const r = await fetch(`${API_BASE}/history/status`);
        const s = await r.json();
        el.undoBtn.disabled = !s.can_undo;
        el.redoBtn.disabled = !s.can_redo;
    } catch (_) { /* ignore */ }
}

async function performUndo() {
    try {
        const r = await fetch(`${API_BASE}/history/undo`);
        if (!r.ok) { log("Nothing to undo.", 'warn'); return; }
        renderSequence((await r.json()).state);
        autosave();
        await refreshUndoRedoButtons();
        log("Undone.", 'info');
    } catch (e) { log("Undo failed: " + e.message, 'error'); }
}

async function performRedo() {
    try {
        const r = await fetch(`${API_BASE}/history/redo`);
        if (!r.ok) { log("Nothing to redo.", 'warn'); return; }
        renderSequence((await r.json()).state);
        autosave();
        await refreshUndoRedoButtons();
        log("Redone.", 'info');
    } catch (e) { log("Redo failed: " + e.message, 'error'); }
}

// ── Output file management ─────────────────────────────────────────────────

function updateOutputState() {
    const ready = !!(state.sessionDir && state.outputFilename);
    el.saveOutputBtn.disabled   = !ready;
    el.saveOutputAsBtn.disabled = !ready;
    el.outputFilename.textContent = ready ? state.outputFilename : '';
    el.outputFilename.classList.toggle('named', ready);
}

function saveOutput() {
    if (!state.sessionDir || !state.outputFilename) return;
    const url = `${API_BASE}/download_output`
        + `?session_dir=${encodeURIComponent(state.sessionDir)}`
        + `&filename=${encodeURIComponent(state.outputFilename)}`;
    const a = document.createElement('a');
    a.href     = url;
    a.download = state.outputFilename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    log(`Downloading: ${state.outputFilename}`, 'success');
}

async function saveOutputAs() {
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
            const resp = await fetch(url);
            const blob = await resp.blob();
            const ws   = await fh.createWritable();
            await ws.write(blob);
            await ws.close();
            log(`Saved: ${fh.name}`, 'success');
        } catch (e) {
            if (e.name !== 'AbortError') log('Save As failed: ' + e.message, 'error');
        }
    } else {
        saveOutput();
    }
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
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ filename: state.currentPresetName, scripts: getSequence() }),
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        log(`Preset saved → ${state.currentPresetName}`, 'success');
    } catch (e) { log("Save preset failed: " + e.message, 'error'); }
}

function openPresetSaveAsBar() {
    el.presetSaveAsBar.classList.add('open');
    el.presetSaveAsInput.value = state.currentPresetName || '';
    el.presetSaveAsInput.focus();
    el.presetSaveAsInput.select();
}

function closePresetSaveAsBar() {
    el.presetSaveAsBar.classList.remove('open');
}

async function confirmPresetSaveAs() {
    let name = el.presetSaveAsInput.value.trim();
    if (!name) return;
    if (!name.endsWith('.json')) name += '.json';
    try {
        const r = await fetch(`${API_BASE}/save_preset`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ filename: name, scripts: getSequence() }),
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        state.currentPresetName = d.filename;
        updatePresetFilenameDisplay();
        log(`Preset saved as → ${d.filename}`, 'success');
        closePresetSaveAsBar();
    } catch (e) { log("Save As failed: " + e.message, 'error'); }
}

async function loadPresetFromPicker(file) {
    try {
        const steps = JSON.parse(await file.text());
        renderSequence(steps);
        state.currentPresetName = file.name;
        updatePresetFilenameDisplay();
        await pushHistoryAndSave();
        log(`Preset loaded: ${file.name}`, 'success');
    } catch (e) { log("Load failed: " + e.message, 'error'); }
}

// ── Plugin picker ──────────────────────────────────────────────────────────

async function openPluginDropdown() {
    if (state.pluginDropdownOpen) { closePluginDropdown(); return; }

    try {
        const r = await fetch(`${API_BASE}/list_plugins`);
        state.pluginCache = await r.json();
    } catch (e) {
        log("Could not load plugins: " + e.message, 'error');
        return;
    }

    state.activeTagFilter = null;
    el.pluginSearch.value = '';
    renderTagBar();
    renderPluginList(state.pluginCache);

    el.pluginDropdown.classList.add('open');
    state.pluginDropdownOpen = true;
    el.pluginSearch.focus();
}

function closePluginDropdown() {
    el.pluginDropdown.classList.remove('open');
    state.pluginDropdownOpen = false;
}

function renderTagBar() {
    const allTags = [...new Set(state.pluginCache.flatMap(p => p.tags || []))].sort();
    el.tagBar.innerHTML = '';

    if (allTags.length === 0) { el.tagBar.style.display = 'none'; return; }
    el.tagBar.style.display = 'flex';

    const makeChip = (label, value) => {
        const chip = document.createElement('button');
        chip.className = 'tag-chip' + (state.activeTagFilter === value ? ' active' : '');
        chip.textContent = label;
        chip.addEventListener('click', () => {
            state.activeTagFilter = (state.activeTagFilter === value) ? null : value;
            renderTagBar();
            applyPluginFilter();
        });
        return chip;
    };

    el.tagBar.appendChild(makeChip('all', null));
    allTags.forEach(tag => el.tagBar.appendChild(makeChip(tag, tag)));
}

function applyPluginFilter() {
    const q   = (el.pluginSearch.value || '').toLowerCase();
    const tag = state.activeTagFilter;

    const filtered = state.pluginCache.filter(p => {
        const matchesTag    = !tag || (p.tags || []).includes(tag);
        const matchesSearch = !q
            || p.key.toLowerCase().includes(q)
            || (p.label  || '').toLowerCase().includes(q)
            || (p.description || '').toLowerCase().includes(q)
            || (p.tags || []).some(t => t.includes(q));
        return matchesTag && matchesSearch;
    });

    renderPluginList(filtered);
}

function renderPluginList(plugins) {
    el.pluginList.innerHTML = '';

    if (plugins.length === 0) {
        el.pluginList.innerHTML = '<div class="plugin-empty">No matching plugins.</div>';
        return;
    }

    plugins.forEach(p => {
        const li = document.createElement('li');

        const mimeMatch  = !state.selectedFileMime
            || !p.accepts
            || p.accepts.length === 0
            || p.accepts.includes(state.selectedFileMime)
            || p.accepts.includes('*/*');

        const depOk      = p.deps_ok !== false;
        const missingStr = (p.missing_deps || []).join(', ');

        li.className = 'plugin-item'
            + (mimeMatch ? '' : ' plugin-mime-mismatch')
            + (depOk     ? '' : ' plugin-dep-missing');

        li.innerHTML = `
            <div class="plugin-item-body">
                <div class="plugin-item-label">
                    ${p.label || p.key}
                    ${!mimeMatch ? `<span class="plugin-badge badge-mime" title="This plugin does not declare support for '${state.selectedFileMime}'">type mismatch</span>` : ''}
                    ${!depOk    ? `<span class="plugin-badge badge-dep"  title="Missing: ${missingStr}">missing deps</span>` : ''}
                </div>
                <div class="plugin-item-key">${p.key}</div>
                ${p.description ? `<div class="plugin-item-desc">${p.description}</div>` : ''}
                ${(p.tags||[]).length ? `<div class="plugin-item-tags">${p.tags.map(t=>`<span class="tag-label">${t}</span>`).join('')}</div>` : ''}
            </div>
            <svg class="plugin-item-arrow" width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>
        `;

        li.addEventListener('click', () => {
            el.scriptList.appendChild(createStepEl({ pluginKey: p.key }));
            updateEmptyState();
            pushHistoryAndSave();
            closePluginDropdown();
        });

        el.pluginList.appendChild(li);
    });
}

// ── Target file ────────────────────────────────────────────────────────────

async function handleFileSelected(file) {
    state.selectedFile     = file;
    state.selectedFileMime = guessMime(file.name);
    state.sessionDir       = null;
    state.outputFilename   = null;
    updateOutputState();
    el.fileDisplay.textContent = file.name;
    el.fileDisplay.classList.add('active');
    log(`Target: ${file.name}  [${state.selectedFileMime}]`);

    const form = new FormData();
    form.append('file', file);
    try {
        const r    = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form });
        const data = await r.json();
        if (data.error) {
            log(`Upload failed: ${data.error}`, 'error');
        } else {
            state.sessionDir     = data.session_dir;
            state.outputFilename = data.filename;
            updateOutputState();
            log(`Workspace ready: ${data.filename}`, 'success');
        }
    } catch (e) { log(`Upload failed: ${e.message}`, 'error'); }
}

// ── Workspace ──────────────────────────────────────────────────────────────

async function changeWorkspace() {
    if (window.showDirectoryPicker) {
        try {
            const dir  = await window.showDirectoryPicker();
            const r    = await fetch(`${API_BASE}/set_workspace`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ path: dir.name }),
            });
            const data = await r.json();
            el.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
            log(`Workspace: ${data.workspace}`, 'success');
        } catch (e) {
            if (e.name !== 'AbortError') log("Workspace change failed: " + e.message, 'error');
        }
    } else {
        try {
            const r       = await fetch(`${API_BASE}/list_workspaces`);
            const options = await r.json();
            log("Available workspaces:", 'system');
            options.forEach(p => log("  " + p, 'system'));
            const input = prompt("Enter workspace path:");
            if (!input) return;
            const r2   = await fetch(`${API_BASE}/set_workspace`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ path: input }),
            });
            const data = await r2.json();
            el.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
            log(`Workspace: ${data.workspace}`, 'success');
        } catch (e) { log("Workspace change failed: " + e.message, 'error'); }
    }
}

// ── Run ────────────────────────────────────────────────────────────────────

async function runSequence() {
    if (!state.selectedFile) { log("No target file selected.", 'error'); return; }
    if (!state.sessionDir)   { log("File not yet uploaded to workspace.", 'error'); return; }

    const activeSteps = getSequence().filter(s => s.isChecked);
    if (activeSteps.length === 0) { log("No active steps to run.", 'warn'); return; }

    const depErrors = activeSteps
        .map(s => state.pluginCache.find(p => p.key === s.pluginKey))
        .filter(p => p && p.deps_ok === false);

    if (depErrors.length > 0) {
        depErrors.forEach(p =>
            log(`'${p.label}' is missing: ${p.missing_deps.join(', ')}`, 'warn')
        );
        log("Fix missing dependencies before running.", 'error');
        return;
    }

    log(`Running ${activeSteps.length} step(s) on ${state.selectedFile.name}…`);

    try {
        const r      = await fetch(`${API_BASE}/execute`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                filename:    state.selectedFile.name,
                session_dir: state.sessionDir,
                scripts:     activeSteps,
            }),
        });
        const result = await r.json();

        if (result.error) {
            log(`Error: ${result.error}`, 'error');
            if (result.completed && result.completed.length > 0)
                log(`Completed before failure: ${result.completed.join(', ')}`, 'warn');
        } else {
            (result.steps || []).forEach(s => {
                if (s.warning) log(`  ${s.step}: ${s.warning}`, 'warn');
            });
            log(`Done — ${result.message}  [${result.mime_type}]`, 'success');
            log(`Use "Save Output" in the toolbar to download the result.`, 'system');
        }
    } catch (e) { log("Execution failed: " + e.message, 'error'); }
}

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {

    el = {
        scriptList:        document.getElementById('scriptList'),
        emptyState:        document.getElementById('emptyState'),
        workspaceDisplay:  document.getElementById('workspaceDisplay'),
        fileDisplay:       document.getElementById('fileDisplay'),
        consoleContent:    document.getElementById('consoleContent'),
        consoleToolbar:    document.getElementById('consoleToolbar'),
        resizeHandle:      document.getElementById('resizeHandle'),
        filePicker:        document.getElementById('filePicker'),
        // toolbar — output
        undoBtn:           document.getElementById('undoBtn'),
        redoBtn:           document.getElementById('redoBtn'),
        saveOutputBtn:     document.getElementById('saveOutputBtn'),
        saveOutputAsBtn:   document.getElementById('saveOutputAsBtn'),
        outputFilename:    document.getElementById('outputFilename'),
        // preset bar
        savePresetBtn:     document.getElementById('savePresetBtn'),
        savePresetAsBtn:   document.getElementById('savePresetAsBtn'),
        loadPresetBtn:     document.getElementById('loadPresetBtn'),
        presetFilePicker:  document.getElementById('presetFilePicker'),
        presetSaveAsBar:   document.getElementById('presetSaveAsBar'),
        presetSaveAsInput: document.getElementById('presetSaveAsInput'),
        presetFilename:    document.getElementById('presetFilename'),
        // plugin dropdown
        addStepBtn:        document.getElementById('add-global-step'),
        pluginDropdown:    document.getElementById('pluginDropdown'),
        pluginSearch:      document.getElementById('pluginSearch'),
        pluginList:        document.getElementById('pluginList'),
        tagBar:            document.getElementById('tagBar'),
        // run / workspace / console
        playAll:           document.getElementById('playAll'),
        workspaceBtn:      document.getElementById('workspaceBtn'),
        consoleClear:      document.getElementById('consoleClear'),
    };

    // Sortable
    if (typeof Sortable !== 'undefined') {
        Sortable.create(el.scriptList, {
            animation:  150,
            handle:     '.step-drag-handle',
            ghostClass: 'sortable-ghost',
            dragClass:  'sortable-drag',
            onEnd:      pushHistoryAndSave,
        });
    }

    // Console resize
    el.resizeHandle.addEventListener('mousedown', () => {
        const onMove = (e) => {
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

    // File picker
    el.filePicker.addEventListener('change', e => {
        if (e.target.files[0]) handleFileSelected(e.target.files[0]);
        e.target.value = '';
    });

    // Output buttons
    el.saveOutputBtn.addEventListener('click',   saveOutput);
    el.saveOutputAsBtn.addEventListener('click', saveOutputAs);

    // Preset buttons
    el.savePresetBtn.addEventListener('click',   savePreset);
    el.savePresetAsBtn.addEventListener('click', openPresetSaveAsBar);
    el.loadPresetBtn.addEventListener('click',   () => el.presetFilePicker.click());
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

    // Undo / redo
    el.undoBtn.addEventListener('click', performUndo);
    el.redoBtn.addEventListener('click', performRedo);

    // Plugin dropdown
    el.addStepBtn.addEventListener('click', e => { e.stopPropagation(); openPluginDropdown(); });
    el.pluginSearch.addEventListener('input', applyPluginFilter);
    el.pluginSearch.addEventListener('keydown', e => { if (e.key === 'Escape') closePluginDropdown(); });
    document.addEventListener('click', e => {
        if (state.pluginDropdownOpen &&
            !el.addStepBtn.contains(e.target) &&
            !el.pluginDropdown.contains(e.target))
            closePluginDropdown();
    });

    // Run / workspace
    el.playAll.addEventListener('click',      runSequence);
    el.workspaceBtn.addEventListener('click', changeWorkspace);

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
        const ctrl = e.ctrlKey || e.metaKey;
        if (ctrl && e.key === 'z' && !e.shiftKey) { e.preventDefault(); performUndo(); }
        if (ctrl && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); performRedo(); }
        if (ctrl && e.key === 's' && !e.shiftKey) { e.preventDefault(); saveOutput(); }
        if (ctrl && e.key === 's' &&  e.shiftKey) { e.preventDefault(); saveOutputAs(); }
        if (ctrl && e.key === 'p') { e.preventDefault(); savePreset(); }
    });

    // Boot
    try {
        const r     = await fetch(`${API_BASE}/load`);
        const steps = await r.json();
        try {
            const pr = await fetch(`${API_BASE}/list_plugins`);
            state.pluginCache = await pr.json();
        } catch (_) {}
        renderSequence(steps);
        if (steps.length > 0) log(`Restored ${steps.length} step(s) from last session.`);
    } catch (e) { log("No previous session found.", 'system'); }

    try {
        const r    = await fetch(`${API_BASE}/get_workspace`);
        const data = await r.json();
        el.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
    } catch (_) { el.workspaceDisplay.textContent = 'default'; }

    await refreshUndoRedoButtons();
    updateOutputState();
    updatePresetFilenameDisplay();
    log('System ready.', 'system');
});
