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
    pluginCache:           [],
    // Choose Plugins
    sessionPlugins:        null,   // null = all available; Set = restricted set
    chooseTagFilter:       null,   // tag filter inside the choose panel
    chooseOpen:            false,
    // Add Step picker
    addStepTagFilter:      null,   // persists across opens
    pluginDropdownOpen:    false,
    // Modals
    presetLibraryOpen:     false,
    newPluginOpen:         false,
    cachedPresets:         [],
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

// ── Step list ──────────────────────────────────────────────────────────────

function createStepEl({ pluginKey, description = '', isChecked = true }) {
    const li = document.createElement('li');
    li.dataset.pluginKey = pluginKey;
    if (!isChecked) li.classList.add('step-disabled');

    const info   = state.pluginCache.find(p => p.key === pluginKey) || {};
    const label  = info.label || pluginKey;
    const depsOk = info.deps_ok !== false;
    const missing = info.missing_deps || [];

    const depWarn = !depsOk
        ? `<div class="step-dep-warning" title="Missing: ${missing.join(', ')}">
               <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
               </svg>Missing deps</div>`
        : '';

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
        </div>
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
    li.querySelector('.step-delete').addEventListener('click', () => {
        li.remove(); updateEmptyState(); pushHistoryAndSave();
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
    steps.forEach(s => el.scriptList.appendChild(createStepEl(s)));
    updateEmptyState();
}

function updateEmptyState() {
    el.emptyState.classList.toggle('visible', el.scriptList.children.length === 0);
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

function updateOutputState() {
    const ready = !!(state.sessionDir && state.outputFilename);
    el.saveOutputBtn.disabled    = !ready;
    el.saveOutputAsBtn.disabled  = !ready;
    el.outputFilename.textContent = ready ? state.outputFilename : '';
    el.outputFilename.classList.toggle('named', ready);
}

function saveOutput() {
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
            </label>`;

        li.querySelector('.choose-checkbox').addEventListener('change', e => {
            toggleSessionPlugin(p.key, e.target.checked);
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
        el.addStepLabel.textContent = `Add Step  (${state.sessionPlugins.size} available)`;
    } else {
        el.addStepLabel.textContent = 'Add Processing Step';
    }
}

// ── Add Processing Step picker ─────────────────────────────────────────────

async function openPluginDropdown() {
    if (state.pluginDropdownOpen) { closePluginDropdown(); return; }
    try {
        const r = await fetch(`${API_BASE}/list_plugins`);
        state.pluginCache = await r.json();
    } catch (e) { log('Could not load plugins: ' + e.message, 'error'); return; }

    el.pluginSearch.value = '';
    renderTagBar();
    renderPluginList(filteredForAddStep(state.pluginCache));

    el.pluginDropdown.classList.add('open');
    state.pluginDropdownOpen = true;
    el.pluginSearch.focus();
}

function closePluginDropdown() {
    el.pluginDropdown.classList.remove('open');
    state.pluginDropdownOpen = false;
}

function filteredForAddStep(plugins) {
    const q   = (el.pluginSearch.value || '').toLowerCase();
    const tag = state.addStepTagFilter;

    return plugins.filter(p => {
        const inSession   = !state.sessionPlugins || state.sessionPlugins.has(p.key);
        const matchesTag  = !tag || (p.tags||[]).includes(tag);
        const matchSearch = !q
            || p.key.toLowerCase().includes(q)
            || (p.label||'').toLowerCase().includes(q)
            || (p.description||'').toLowerCase().includes(q)
            || (p.tags||[]).some(t => t.includes(q));
        return inSession && matchesTag && matchSearch;
    });
}

function renderTagBar() {
    // Tags from session-available plugins only
    const available = state.sessionPlugins
        ? state.pluginCache.filter(p => state.sessionPlugins.has(p.key))
        : state.pluginCache;
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
            renderPluginList(filteredForAddStep(state.pluginCache));
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

        li.innerHTML = `
            <div class="plugin-item-body">
                <div class="plugin-item-label">
                    ${p.label || p.key}
                    ${!mimeMatch ? `<span class="plugin-badge badge-mime">type mismatch</span>` : ''}
                    ${!depOk    ? `<span class="plugin-badge badge-dep" title="Missing: ${(p.missing_deps||[]).join(', ')}">missing deps</span>` : ''}
                </div>
                <div class="plugin-item-key">${p.key}</div>
                ${p.description ? `<div class="plugin-item-desc">${p.description}</div>` : ''}
                ${(p.tags||[]).length ? `<div class="plugin-item-tags">${p.tags.map(t=>`<span class="tag-label">${t}</span>`).join('')}</div>` : ''}
            </div>
            <svg class="plugin-item-arrow" width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>`;

        li.addEventListener('click', () => {
            el.scriptList.appendChild(createStepEl({ pluginKey: p.key }));
            updateEmptyState(); pushHistoryAndSave(); closePluginDropdown();
        });
        el.pluginList.appendChild(li);
    });
}

// ── New Plugin with AI ─────────────────────────────────────────────────────

function openNewPluginModal() {
    closeChoosePlugins();
    state.newPluginOpen = true;
    el.newPluginOverlay.classList.add('open');
    el.pluginDescription.value = '';
    el.pluginFilename.value    = '';
    el.codePreviewWrap.style.display = 'none';
    el.pluginDescription.focus();
}

function closeNewPluginModal() {
    state.newPluginOpen = false;
    el.newPluginOverlay.classList.remove('open');
}

async function generatePlugin() {
    const desc = el.pluginDescription.value.trim();
    if (!desc) { log('Please describe what the plugin should do.', 'warn'); return; }

    el.generatePluginBtn.disabled   = true;
    el.generatePluginBtn.textContent = 'Generating…';
    el.codePreviewWrap.style.display = 'none';

    try {
        const r    = await fetch(`${API_BASE}/generate_plugin`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ description: desc }),
        });
        const data = await r.json();
        if (data.error) throw new Error(data.error);

        el.codePreview.textContent       = data.code;
        el.codePreviewWrap.style.display = '';
        el.codePreviewTitle.textContent  = 'Generated plugin — review before saving';
        log('Plugin generated. Review the code, then save.', 'success');
    } catch (e) {
        log('Generation failed: ' + e.message, 'error');
    } finally {
        el.generatePluginBtn.disabled    = false;
        el.generatePluginBtn.innerHTML   = `<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
        </svg> Generate`;
    }
}

async function savePlugin() {
    const code     = el.codePreview.textContent.trim();
    const filename = el.pluginFilename.value.trim() || 'generated_plugin.py';
    if (!code) return;
    try {
        const r    = await fetch(`${API_BASE}/save_plugin`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ code, filename }),
        });
        const data = await r.json();
        if (data.error) throw new Error(data.error);
        log(`Plugin saved → plugins/${data.filename}`, 'success');
        // Refresh plugin cache so it shows up immediately
        try {
            const pr = await fetch(`${API_BASE}/list_plugins`);
            state.pluginCache = await pr.json();
            updateChoosePluginsBtn();
            updateAddStepLabel();
        } catch (_) {}
        closeNewPluginModal();
    } catch (e) { log('Save failed: ' + e.message, 'error'); }
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
        const data = await (await fetch(`${API_BASE}/upload`, { method: 'POST', body: form })).json();
        if (data.error) { log(`Upload failed: ${data.error}`, 'error'); return; }
        state.sessionDir     = data.session_dir;
        state.outputFilename = data.filename;
        updateOutputState();
        log(`Workspace ready: ${data.filename}`, 'success');
    } catch (e) { log(`Upload failed: ${e.message}`, 'error'); }
}

// ── Run ────────────────────────────────────────────────────────────────────

async function runSequence() {
    if (!state.selectedFile) { log('No target file selected.', 'error'); return; }
    if (!state.sessionDir)   { log('File not yet uploaded to workspace.', 'error'); return; }

    const activeSteps = getSequence().filter(s => s.isChecked);
    if (!activeSteps.length) { log('No active steps to run.', 'warn'); return; }

    const depErrors = activeSteps
        .map(s => state.pluginCache.find(p => p.key === s.pluginKey))
        .filter(p => p && p.deps_ok === false);
    if (depErrors.length) {
        depErrors.forEach(p => log(`'${p.label}' missing: ${p.missing_deps.join(', ')}`, 'warn'));
        log('Fix missing dependencies before running.', 'error');
        return;
    }

    log(`Running ${activeSteps.length} step(s) on ${state.selectedFile.name}…`);
    try {
        const r = await fetch(`${API_BASE}/execute`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                filename:    state.selectedFile.name,
                session_dir: state.sessionDir,
                scripts:     activeSteps,
            }),
        });
        const result = await r.json();
        if (result.error) {
            log(`Error: ${result.error}`, 'error');
            if (result.completed?.length) log(`Completed before failure: ${result.completed.join(', ')}`, 'warn');
        } else {
            (result.steps||[]).forEach(s => { if (s.warning) log(`  ${s.step}: ${s.warning}`, 'warn'); });
            log(`Done — ${result.message}  [${result.mime_type}]`, 'success');
            log('Use "Save Output" to download the result.', 'system');
            if (state.currentPresetName) recordPresetEvent(state.currentPresetName, 'success');
        }
    } catch (e) { log('Execution failed: ' + e.message, 'error'); }
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
        // toolbar
        undoBtn:              document.getElementById('undoBtn'),
        redoBtn:              document.getElementById('redoBtn'),
        saveOutputBtn:        document.getElementById('saveOutputBtn'),
        saveOutputAsBtn:      document.getElementById('saveOutputAsBtn'),
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
        // new plugin modal
        newPluginOverlay:     document.getElementById('newPluginOverlay'),
        pluginDescription:    document.getElementById('pluginDescription'),
        pluginFilename:       document.getElementById('pluginFilename'),
        generatePluginBtn:    document.getElementById('generatePluginBtn'),
        codePreviewWrap:      document.getElementById('codePreviewWrap'),
        codePreviewTitle:     document.getElementById('codePreviewTitle'),
        codePreview:          document.getElementById('codePreview'),
        // run / console
        playAll:              document.getElementById('playAll'),
        consoleClear:         document.getElementById('consoleClear'),
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

    // File picker
    el.filePicker.addEventListener('change', e => {
        if (e.target.files[0]) handleFileSelected(e.target.files[0]);
        e.target.value = '';
    });

    // Output
    el.saveOutputBtn.addEventListener('click',   saveOutput);
    el.saveOutputAsBtn.addEventListener('click', saveOutputAs);

    // Choose Plugins panel
    el.choosePluginsBtn.addEventListener('click', e => { e.stopPropagation(); openChoosePlugins(); });
    el.chooseSearch.addEventListener('input', renderChooseList);
    el.chooseSearch.addEventListener('keydown', e => { if (e.key === 'Escape') closeChoosePlugins(); });
    document.getElementById('clearChooseBtn').addEventListener('click', clearSessionPlugins);
    document.getElementById('newPluginTrigger').addEventListener('click', openNewPluginModal);

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
    el.addStepBtn.addEventListener('click', e => { e.stopPropagation(); openPluginDropdown(); });
    el.pluginSearch.addEventListener('input', () => renderPluginList(filteredForAddStep(state.pluginCache)));
    el.pluginSearch.addEventListener('keydown', e => { if (e.key === 'Escape') closePluginDropdown(); });

    // New Plugin modal
    document.getElementById('newPluginClose').addEventListener('click', closeNewPluginModal);
    el.newPluginOverlay.addEventListener('click', e => { if (e.target === el.newPluginOverlay) closeNewPluginModal(); });
    el.generatePluginBtn.addEventListener('click', generatePlugin);
    document.getElementById('savePluginBtn').addEventListener('click', savePlugin);
    el.pluginDescription.addEventListener('keydown', e => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); generatePlugin(); }
    });

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
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
        const ctrl = e.ctrlKey || e.metaKey;
        if (ctrl && e.key === 'z' && !e.shiftKey) { e.preventDefault(); performUndo(); }
        if (ctrl && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); performRedo(); }
        if (ctrl && e.key === 's' && !e.shiftKey) { e.preventDefault(); saveOutput(); }
        if (ctrl && e.key === 's' &&  e.shiftKey) { e.preventDefault(); saveOutputAs(); }
        if (ctrl && e.key === 'p') { e.preventDefault(); savePreset(); }
        if (e.key === 'Escape') { closePresetLibrary(); closeNewPluginModal(); closeChoosePlugins(); }
    });

    // Boot
    try {
        const steps = await (await fetch(`${API_BASE}/load`)).json();
        try {
            state.pluginCache = await (await fetch(`${API_BASE}/list_plugins`)).json();
        } catch (_) {}
        renderSequence(steps);
        if (steps.length) log(`Restored ${steps.length} step(s) from last session.`);
    } catch (_) { log('No previous session found.', 'system'); }

    await refreshUndoRedoButtons();
    updateOutputState();
    updatePresetFilenameDisplay();
    log('System ready.', 'system');
});
