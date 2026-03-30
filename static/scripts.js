/**
 * PY-AUTOMATE — scripts.js
 * Undo/redo, autosave, save, save-as, load, inline plugin picker.
 */

const API_BASE = 'http://localhost:5000';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
    selectedFile: null,
    currentSeqFilename: null,   // null = unsaved / "last_session"
    pluginCache: [],
    pluginDropdownOpen: false,
};

// ── DOM refs (populated on DOMContentLoaded) ───────────────────────────────

let el = {};

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

    li.innerHTML = `
        <div class="step-drag-handle" title="Drag to reorder">
            <svg width="12" height="16" viewBox="0 0 12 16" fill="currentColor">
                <circle cx="3.5" cy="3" r="1.5"/><circle cx="8.5" cy="3" r="1.5"/>
                <circle cx="3.5" cy="8" r="1.5"/><circle cx="8.5" cy="8" r="1.5"/>
                <circle cx="3.5" cy="13" r="1.5"/><circle cx="8.5" cy="13" r="1.5"/>
            </svg>
        </div>
        <input type="checkbox" class="step-checkbox" ${isChecked ? 'checked' : ''}>
        <div class="step-body">
            <span class="step-key">${pluginKey}</span>
            <input type="text" class="step-note" value="${description}" placeholder="Add a note…">
        </div>
        <button class="step-delete" title="Remove step">
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
        </button>
    `;

    const checkbox = li.querySelector('.step-checkbox');
    checkbox.addEventListener('change', () => {
        li.classList.toggle('step-disabled', !checkbox.checked);
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
        pluginKey: li.dataset.pluginKey,
        description: li.querySelector('.step-note').value,
        isChecked: li.querySelector('.step-checkbox').checked,
    }));
}

function renderSequence(steps) {
    el.scriptList.innerHTML = '';
    steps.forEach(step => el.scriptList.appendChild(createStepEl(step)));
    updateEmptyState();
}

function updateEmptyState() {
    const isEmpty = el.scriptList.children.length === 0;
    el.emptyState.classList.toggle('visible', isEmpty);
}

// ── Autosave (silent) ──────────────────────────────────────────────────────

async function autosave() {
    try {
        await fetch(`${API_BASE}/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getSequence()),
        });
    } catch (e) {
        // Autosave failures are silent — don't spam the console
    }
}

// ── History ────────────────────────────────────────────────────────────────

async function pushHistoryAndSave() {
    autosave();
    try {
        await fetch(`${API_BASE}/history/push`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getSequence()),
        });
        await refreshUndoRedoButtons();
    } catch (e) {
        // history push failure is non-critical
    }
}

async function refreshUndoRedoButtons() {
    try {
        const r = await fetch(`${API_BASE}/history/status`);
        const s = await r.json();
        el.undoBtn.disabled = !s.can_undo;
        el.redoBtn.disabled = !s.can_redo;
    } catch (e) {
        // ignore
    }
}

async function performUndo() {
    try {
        const r = await fetch(`${API_BASE}/history/undo`);
        if (!r.ok) { log("Nothing to undo.", 'warn'); return; }
        const data = await r.json();
        renderSequence(data.state);
        autosave();
        await refreshUndoRedoButtons();
        log("Undone.", 'info');
    } catch (e) {
        log("Undo failed: " + e.message, 'error');
    }
}

async function performRedo() {
    try {
        const r = await fetch(`${API_BASE}/history/redo`);
        if (!r.ok) { log("Nothing to redo.", 'warn'); return; }
        const data = await r.json();
        renderSequence(data.state);
        autosave();
        await refreshUndoRedoButtons();
        log("Redone.", 'info');
    } catch (e) {
        log("Redo failed: " + e.message, 'error');
    }
}

// ── Save / Save As / Load ──────────────────────────────────────────────────

async function saveSequence() {
    if (!state.currentSeqFilename) {
        // No name yet — open Save As
        openSaveAsBar();
        return;
    }
    try {
        await fetch(`${API_BASE}/save_as`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: state.currentSeqFilename, scripts: getSequence() }),
        });
        log(`Saved → ${state.currentSeqFilename}`, 'success');
    } catch (e) {
        log("Save failed: " + e.message, 'error');
    }
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
        const r = await fetch(`${API_BASE}/save_as`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: name, scripts: getSequence() }),
        });
        const data = await r.json();
        if (data.error) throw new Error(data.error);
        state.currentSeqFilename = data.filename;
        updateSeqFilenameDisplay();
        log(`Saved as → ${data.filename}`, 'success');
        closeSaveAsBar();
    } catch (e) {
        log("Save As failed: " + e.message, 'error');
    }
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

function openLoadPicker() {
    el.seqFilePicker.click();
}

async function loadFromPicker(file) {
    try {
        const text = await file.text();
        const steps = JSON.parse(text);
        renderSequence(steps);
        state.currentSeqFilename = file.name;
        updateSeqFilenameDisplay();
        await pushHistoryAndSave();
        log(`Loaded sequence: ${file.name}`, 'success');
    } catch (e) {
        log("Load failed: " + e.message, 'error');
    }
}

// ── Plugin picker (inline dropdown) ───────────────────────────────────────

async function openPluginDropdown() {
    if (state.pluginDropdownOpen) {
        closePluginDropdown();
        return;
    }
    // Load plugins if cache is empty
    if (state.pluginCache.length === 0) {
        try {
            const r = await fetch(`${API_BASE}/list_plugins`);
            state.pluginCache = await r.json();
        } catch (e) {
            log("Could not load plugins: " + e.message, 'error');
            return;
        }
    }
    renderPluginList(state.pluginCache);
    el.pluginDropdown.classList.add('open');
    state.pluginDropdownOpen = true;
    el.pluginSearch.value = '';
    el.pluginSearch.focus();
}

function closePluginDropdown() {
    el.pluginDropdown.classList.remove('open');
    state.pluginDropdownOpen = false;
}

function renderPluginList(plugins) {
    el.pluginList.innerHTML = '';
    if (plugins.length === 0) {
        el.pluginList.innerHTML = '<div class="plugin-empty">No plugins found in /plugins folder.</div>';
        return;
    }
    plugins.forEach(key => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${key}</span>
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>
        `;
        li.addEventListener('click', () => {
            el.scriptList.appendChild(createStepEl({ pluginKey: key }));
            updateEmptyState();
            pushHistoryAndSave();
            closePluginDropdown();
        });
        el.pluginList.appendChild(li);
    });
}

// ── Target file picker ─────────────────────────────────────────────────────

function handleFileSelected(file) {
    state.selectedFile = file;
    el.fileDisplay.textContent = file.name;
    el.fileDisplay.classList.add('active');
    log(`Target file: ${file.name}`);
}

// ── Workspace ──────────────────────────────────────────────────────────────

async function changeWorkspace() {
    // Use the native directory picker if available; fall back to prompt
    if (window.showDirectoryPicker) {
        try {
            const dir = await window.showDirectoryPicker();
            const r = await fetch(`${API_BASE}/set_workspace`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: dir.name }),
            });
            const data = await r.json();
            el.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
            log(`Workspace set: ${data.workspace}`, 'success');
        } catch (e) {
            if (e.name !== 'AbortError') log("Workspace change failed: " + e.message, 'error');
        }
    } else {
        // Fallback: show current options as a tiny list in console
        try {
            const r = await fetch(`${API_BASE}/list_workspaces`);
            const options = await r.json();
            log("Available workspaces:", 'system');
            options.forEach(p => log("  " + p, 'system'));
            const input = prompt("Enter workspace path:");
            if (!input) return;
            const r2 = await fetch(`${API_BASE}/set_workspace`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: input }),
            });
            const data = await r2.json();
            el.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
            log(`Workspace set: ${data.workspace}`, 'success');
        } catch (e) {
            log("Workspace change failed: " + e.message, 'error');
        }
    }
}

// ── Run ────────────────────────────────────────────────────────────────────

async function runSequence() {
    if (!state.selectedFile) {
        log("No target file selected.", 'error');
        return;
    }

    const activeSteps = getSequence().filter(s => s.isChecked);
    if (activeSteps.length === 0) {
        log("No active steps to run.", 'warn');
        return;
    }

    log(`Running ${activeSteps.length} step(s) on ${state.selectedFile.name}…`, 'info');

    try {
        const r = await fetch(`${API_BASE}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: state.selectedFile.name, scripts: activeSteps }),
        });
        const result = await r.json();
        if (result.error) {
            log("Error: " + result.error, 'error');
        } else {
            log("Process complete: " + result.message, 'success');
        }
    } catch (e) {
        log("Execution failed: " + e.message, 'error');
    }
}

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {

    el = {
        scriptList:      document.getElementById('scriptList'),
        emptyState:      document.getElementById('emptyState'),
        workspaceDisplay:document.getElementById('workspaceDisplay'),
        fileDisplay:     document.getElementById('fileDisplay'),
        consoleContent:  document.getElementById('consoleContent'),
        consoleToolbar:  document.getElementById('consoleToolbar'),
        resizeHandle:    document.getElementById('resizeHandle'),
        filePicker:      document.getElementById('filePicker'),
        seqFilePicker:   document.getElementById('seqFilePicker'),
        // toolbar strip buttons
        undoBtn:         document.getElementById('undoBtn'),
        redoBtn:         document.getElementById('redoBtn'),
        saveBtn:         document.getElementById('saveBtn'),
        saveAsBtn:       document.getElementById('saveAsBtn'),
        loadSeqBtn:      document.getElementById('loadSeqBtn'),
        seqFilename:     document.getElementById('seqFilename'),
        // save-as inline bar
        saveAsBar:       document.getElementById('saveAsBar'),
        saveAsInput:     document.getElementById('saveAsInput'),
        // plugin dropdown
        addStepBtn:      document.getElementById('add-global-step'),
        pluginDropdown:  document.getElementById('pluginDropdown'),
        pluginSearch:    document.getElementById('pluginSearch'),
        pluginList:      document.getElementById('pluginList'),
        // run
        playAll:         document.getElementById('playAll'),
        // workspace
        workspaceBtn:    document.getElementById('workspaceBtn'),
        // console
        consoleClear:    document.getElementById('consoleClear'),
    };

    // ── Sortable drag-and-drop
    if (typeof Sortable !== 'undefined') {
        Sortable.create(el.scriptList, {
            animation: 150,
            handle: '.step-drag-handle',
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            onEnd: pushHistoryAndSave,
        });
    }

    // ── Console resize
    el.resizeHandle.addEventListener('mousedown', () => {
        const onMove = (e) => {
            const h = window.innerHeight - e.clientY;
            if (h >= 50 && h <= 400) el.consoleToolbar.style.height = `${h}px`;
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', () => document.removeEventListener('mousemove', onMove), { once: true });
    });

    // ── Console clear
    el.consoleClear.addEventListener('click', () => {
        el.consoleContent.innerHTML = '';
        log('Console cleared.', 'system');
    });

    // ── Target file picker
    el.filePicker.addEventListener('change', (e) => {
        if (e.target.files[0]) handleFileSelected(e.target.files[0]);
    });

    // ── Sequence file picker (for load)
    el.seqFilePicker.addEventListener('change', (e) => {
        if (e.target.files[0]) loadFromPicker(e.target.files[0]);
        e.target.value = ''; // reset so same file can be re-loaded
    });

    // ── Toolbar buttons
    el.undoBtn.addEventListener('click', performUndo);
    el.redoBtn.addEventListener('click', performRedo);
    el.saveBtn.addEventListener('click', saveSequence);
    el.saveAsBtn.addEventListener('click', openSaveAsBar);
    el.loadSeqBtn.addEventListener('click', openLoadPicker);

    // ── Save-As bar
    document.getElementById('saveAsConfirm').addEventListener('click', confirmSaveAs);
    document.getElementById('saveAsCancel').addEventListener('click', closeSaveAsBar);
    el.saveAsInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') confirmSaveAs();
        if (e.key === 'Escape') closeSaveAsBar();
    });

    // ── Plugin dropdown
    el.addStepBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openPluginDropdown();
    });

    el.pluginSearch.addEventListener('input', () => {
        const q = el.pluginSearch.value.toLowerCase();
        const filtered = state.pluginCache.filter(k => k.toLowerCase().includes(q));
        renderPluginList(filtered);
    });

    el.pluginSearch.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closePluginDropdown();
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (state.pluginDropdownOpen && !el.addStepBtn.contains(e.target) && !el.pluginDropdown.contains(e.target)) {
            closePluginDropdown();
        }
    });

    // ── Run button
    el.playAll.addEventListener('click', runSequence);

    // ── Workspace
    el.workspaceBtn.addEventListener('click', changeWorkspace);

    // ── Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        const ctrl = e.ctrlKey || e.metaKey;
        if (ctrl && e.key === 'z' && !e.shiftKey) { e.preventDefault(); performUndo(); }
        if (ctrl && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); performRedo(); }
        if (ctrl && e.key === 's' && !e.shiftKey) { e.preventDefault(); saveSequence(); }
        if (ctrl && e.key === 's' && e.shiftKey) { e.preventDefault(); openSaveAsBar(); }
    });

    // ── Initial data load
    try {
        const r = await fetch(`${API_BASE}/load`);
        const steps = await r.json();
        renderSequence(steps);
        if (steps.length > 0) log(`Restored ${steps.length} step(s) from last session.`, 'info');
    } catch (e) {
        log("No previous session found.", 'system');
    }

    try {
        const r = await fetch(`${API_BASE}/get_workspace`);
        const data = await r.json();
        el.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
    } catch (e) {
        el.workspaceDisplay.textContent = 'default';
    }

    await refreshUndoRedoButtons();
    updateSeqFilenameDisplay();
    log('System ready.', 'system');
});
