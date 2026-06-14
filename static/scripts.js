/**
 * PY-AUTOMATE — scripts.js
 * Undo/redo, autosave, save/save-as/load, inline plugin picker with metadata.
 */

const API_BASE = 'http://localhost:5000';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
    selectedFile:        null,
    selectedFileMime:    null,       // guessed MIME of the target file
    currentSeqFilename:  null,
    pluginCache:         [],         // array of plugin descriptor objects from /list_plugins
    pluginDropdownOpen:  false,
    activeTagFilter:     null,       // tag string or null for "all"
};

// ── DOM refs ───────────────────────────────────────────────────────────────

let el = {};

// ── MIME guessing (client-side, rough) ────────────────────────────────────

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

/**
 * Build a step <li> from a step descriptor.
 * descriptor: { pluginKey, description, isChecked }
 * We look up rich metadata from pluginCache to show label + dep warnings.
 */
function createStepEl({ pluginKey, description = '', isChecked = true }) {
    const li = document.createElement('li');
    li.dataset.pluginKey = pluginKey;
    if (!isChecked) li.classList.add('step-disabled');

    // Look up cached metadata for this plugin
    const info    = state.pluginCache.find(p => p.key === pluginKey) || {};
    const label   = info.label || pluginKey;
    const depsOk  = info.deps_ok !== false;   // true if not in cache yet (optimistic)
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

// ── Save / Save As / Load ──────────────────────────────────────────────────

async function saveSequence() {
    if (!state.currentSeqFilename) { openSaveAsBar(); return; }
    try {
        await fetch(`${API_BASE}/save_as`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ filename: state.currentSeqFilename, scripts: getSequence() }),
        });
        log(`Saved → ${state.currentSeqFilename}`, 'success');
    } catch (e) { log("Save failed: " + e.message, 'error'); }
}

function openSaveAsBar() {
    el.saveAsBar.classList.add('open');
    el.saveAsInput.value = state.currentSeqFilename || '';
    el.saveAsInput.focus();
    el.saveAsInput.select();
}

function closeSaveAsBar() {
    el.saveAsBar.classList.remove('open');
}

async function confirmSaveAs() {
    let name = el.saveAsInput.value.trim();
    if (!name) return;
    if (!name.endsWith('.json')) name += '.json';
    try {
        const r    = await fetch(`${API_BASE}/save_as`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ filename: name, scripts: getSequence() }),
        });
        const data = await r.json();
        if (data.error) throw new Error(data.error);
        state.currentSeqFilename = data.filename;
        updateSeqFilenameDisplay();
        log(`Saved as → ${data.filename}`, 'success');
        closeSaveAsBar();
    } catch (e) { log("Save As failed: " + e.message, 'error'); }
}

function updateSeqFilenameDisplay() {
    if (state.currentSeqFilename) {
        el.seqFilename.textContent = state.currentSeqFilename;
        el.seqFilename.classList.add('named');
    } else {
        el.seqFilename.textContent = 'unsaved';
        el.seqFilename.classList.remove('named');
    }
}

function openLoadPicker() { el.seqFilePicker.click(); }

async function loadFromPicker(file) {
    try {
        const steps = JSON.parse(await file.text());
        renderSequence(steps);
        state.currentSeqFilename = file.name;
        updateSeqFilenameDisplay();
        await pushHistoryAndSave();
        log(`Loaded: ${file.name}`, 'success');
    } catch (e) { log("Load failed: " + e.message, 'error'); }
}

// ── Plugin picker ──────────────────────────────────────────────────────────

async function openPluginDropdown() {
    if (state.pluginDropdownOpen) { closePluginDropdown(); return; }

    // Always refresh the cache when opening so dep status stays current
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

/** Collect all unique tags from the cache and render filter chips. */
function renderTagBar() {
    const allTags = [...new Set(state.pluginCache.flatMap(p => p.tags || []))].sort();
    el.tagBar.innerHTML = '';

    if (allTags.length === 0) {
        el.tagBar.style.display = 'none';
        return;
    }
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

/**
 * Render plugin list items.
 * Each item shows: label (bold), key (mono sub-line), description, dep warning if needed.
 * Items incompatible with the selected file MIME are visually dimmed but still addable.
 */
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
    el.fileDisplay.textContent = file.name;
    el.fileDisplay.classList.add('active');
    log(`Target: ${file.name}  [${state.selectedFileMime}]`);

    const form = new FormData();
    form.append('file', file);
    try {
        const r    = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form });
        const data = await r.json();
        if (data.error) log(`Upload failed: ${data.error}`, 'error');
        else log(`Copied to workspace: ${data.filename}`, 'success');
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

    const activeSteps = getSequence().filter(s => s.isChecked);
    if (activeSteps.length === 0) { log("No active steps to run.", 'warn'); return; }

    // Client-side dep pre-check so we warn before even hitting the server
    const depErrors = activeSteps
        .map(s => state.pluginCache.find(p => p.key === s.pluginKey))
        .filter(p => p && p.deps_ok === false);

    if (depErrors.length > 0) {
        depErrors.forEach(p =>
            log(`⚠ '${p.label}' is missing: ${p.missing_deps.join(', ')}`, 'warn')
        );
        log("Fix missing dependencies before running.", 'error');
        return;
    }

    log(`Running ${activeSteps.length} step(s) on ${state.selectedFile.name}…`);

    try {
        const r      = await fetch(`${API_BASE}/execute`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ filename: state.selectedFile.name, scripts: activeSteps }),
        });
        const result = await r.json();

        if (result.error) {
            log(`Error: ${result.error}`, 'error');
            if (result.completed && result.completed.length > 0)
                log(`Completed before failure: ${result.completed.join(', ')}`, 'warn');
        } else {
            // Log any per-step warnings (e.g. MIME mismatches at runtime)
            (result.steps || []).forEach(s => {
                if (s.warning) log(`  ⚠ ${s.step}: ${s.warning}`, 'warn');
            });
            log(`Done — ${result.message}  [output: ${result.mime_type}]`, 'success');
        }
    } catch (e) { log("Execution failed: " + e.message, 'error'); }
}

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {

    el = {
        scriptList:       document.getElementById('scriptList'),
        emptyState:       document.getElementById('emptyState'),
        workspaceDisplay: document.getElementById('workspaceDisplay'),
        fileDisplay:      document.getElementById('fileDisplay'),
        consoleContent:   document.getElementById('consoleContent'),
        consoleToolbar:   document.getElementById('consoleToolbar'),
        resizeHandle:     document.getElementById('resizeHandle'),
        filePicker:       document.getElementById('filePicker'),
        seqFilePicker:    document.getElementById('seqFilePicker'),
        // toolbar
        undoBtn:          document.getElementById('undoBtn'),
        redoBtn:          document.getElementById('redoBtn'),
        saveBtn:          document.getElementById('saveBtn'),
        saveAsBtn:        document.getElementById('saveAsBtn'),
        loadSeqBtn:       document.getElementById('loadSeqBtn'),
        seqFilename:      document.getElementById('seqFilename'),
        saveAsBar:        document.getElementById('saveAsBar'),
        saveAsInput:      document.getElementById('saveAsInput'),
        // plugin dropdown
        addStepBtn:       document.getElementById('add-global-step'),
        pluginDropdown:   document.getElementById('pluginDropdown'),
        pluginSearch:     document.getElementById('pluginSearch'),
        pluginList:       document.getElementById('pluginList'),
        tagBar:           document.getElementById('tagBar'),
        // run / workspace / console
        playAll:          document.getElementById('playAll'),
        workspaceBtn:     document.getElementById('workspaceBtn'),
        consoleClear:     document.getElementById('consoleClear'),
    };

    // Sortable
    if (typeof Sortable !== 'undefined') {
        Sortable.create(el.scriptList, {
            animation:   150,
            handle:      '.step-drag-handle',
            ghostClass:  'sortable-ghost',
            dragClass:   'sortable-drag',
            onEnd:       pushHistoryAndSave,
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

    // File pickers
    el.filePicker.addEventListener('change',    e => { if (e.target.files[0]) handleFileSelected(e.target.files[0]); e.target.value = ''; });
    el.seqFilePicker.addEventListener('change', e => {
        if (e.target.files[0]) loadFromPicker(e.target.files[0]);
        e.target.value = '';
    });

    // Toolbar
    el.undoBtn.addEventListener('click',   performUndo);
    el.redoBtn.addEventListener('click',   performRedo);
    el.saveBtn.addEventListener('click',   saveSequence);
    el.saveAsBtn.addEventListener('click', openSaveAsBar);
    el.loadSeqBtn.addEventListener('click',openLoadPicker);

    document.getElementById('saveAsConfirm').addEventListener('click', confirmSaveAs);
    document.getElementById('saveAsCancel').addEventListener('click',  closeSaveAsBar);
    el.saveAsInput.addEventListener('keydown', e => {
        if (e.key === 'Enter')  confirmSaveAs();
        if (e.key === 'Escape') closeSaveAsBar();
    });

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
        if (ctrl && e.key === 's' && !e.shiftKey) { e.preventDefault(); saveSequence(); }
        if (ctrl && e.key === 's' &&  e.shiftKey) { e.preventDefault(); openSaveAsBar(); }
    });

    // Boot
    try {
        const r     = await fetch(`${API_BASE}/load`);
        const steps = await r.json();
        // Prefetch plugin cache so createStepEl can render labels on restore
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
    updateSeqFilenameDisplay();
    log('System ready.', 'system');
});