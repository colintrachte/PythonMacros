/**
 * PY-AUTOMATE Unified Script
 * Consolidates modal logic and fixes "Add Step" functionality.
 */

const API_BASE = 'http://localhost:5000';

// --- DOM Element Map ---
const elements = {
    scriptList: document.getElementById('scriptList'),
    workspaceDisplay: document.getElementById('workspaceDisplay'),
    fileDisplay: document.getElementById('fileDisplay'),
    consoleContent: document.getElementById('consoleContent'),
    selectionModal: document.getElementById('selectionModal'),
    modalList: document.getElementById('modalList'),
    modalTitle: document.getElementById('modalTitle'),
    filePicker: document.getElementById('filePicker')
};

// --- Core Logic ---

/**
 * Logs messages to the UI console with timestamps and types
 */
function showConsoleMessage(msg, type = 'info') {
    const entry = document.createElement('div');
    const colorClass = {
        error: 'text-red-400',
        success: 'text-green-400',
        info: 'text-blue-300'
    }[type] || 'text-white';

    entry.className = `${colorClass} font-mono text-xs mb-1`;
    entry.textContent = `> [${new Date().toLocaleTimeString()}] ${msg}`;
    
    elements.consoleContent.appendChild(entry);
    elements.consoleContent.scrollTop = elements.consoleContent.scrollHeight;
}

/**
 * Creates the HTML for a single processing step
 */
function createScriptEntry({ pluginKey, description = '', isChecked = true }) {
    const li = document.createElement('li');
    li.className = "bg-white p-4 rounded shadow-md flex items-center justify-between border-l-4 border-blue-500 transition-all hover:shadow-lg";
    li.dataset.pluginKey = pluginKey;

    li.innerHTML = `
        <div class="flex items-center space-x-4 flex-grow">
            <input type="checkbox" ${isChecked ? 'checked' : ''} class="h-5 w-5 text-blue-600 cursor-pointer">
            <div class="flex flex-col flex-grow">
                <span class="text-sm font-mono font-bold text-gray-700">${pluginKey}</span>
                <input type="text" value="${description}" placeholder="Add a note..." 
                       class="step-note text-xs text-gray-500 bg-transparent border-none focus:ring-0 p-0">
            </div>
        </div>
        <button class="delete-btn p-1 text-red-400 hover:text-red-600 transition">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
        </button>
    `;

    li.querySelector('.delete-btn').onclick = () => {
        li.remove();
        saveConfiguration();
    };
    return li;
}

// --- Modal Controller ---

function showSelectionModal(title, items, onSelect) {
    elements.modalTitle.textContent = title;
    elements.modalList.innerHTML = '';
    
    items.forEach(item => {
        const li = document.createElement('li');
        li.className = "group flex items-center justify-between p-4 hover:bg-blue-50 rounded-xl cursor-pointer transition border border-transparent hover:border-blue-100";
        li.innerHTML = `
            <span class="font-mono text-sm text-gray-700">${item}</span>
            <svg class="w-5 h-5 text-blue-500 opacity-0 group-hover:opacity-100" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg>
        `;
        li.onclick = () => {
            onSelect(item);
            closeModal();
        };
        elements.modalList.appendChild(li);
    });
    
    elements.selectionModal.classList.remove('hidden');
}

function closeModal() {
    elements.selectionModal.classList.add('hidden');
}

// --- API Actions ---

async function saveConfiguration() {
    const steps = Array.from(elements.scriptList.children).map(li => ({
        pluginKey: li.dataset.pluginKey,
        description: li.querySelector('.step-note').value,
        isChecked: li.querySelector('input[type="checkbox"]').checked
    }));

    try {
        await fetch(`${API_BASE}/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(steps)
        });
        showConsoleMessage("Configuration saved.", 'success');
    } catch (e) {
        showConsoleMessage("Save failed: " + e.message, 'error');
    }
}

async function loadConfiguration() {
    try {
        const response = await fetch(`${API_BASE}/load`);
        const steps = await response.json();
        elements.scriptList.innerHTML = '';
        steps.forEach(step => elements.scriptList.appendChild(createScriptEntry(step)));
        showConsoleMessage("Sequence loaded from last session.", 'info');
    } catch (e) {
        showConsoleMessage("No saved configuration found.", 'info');
    }
}

async function openPluginModal() {
    try {
        const response = await fetch(`${API_BASE}/list_plugins`);
        const plugins = await response.json();
        showSelectionModal("Add Processing Step", plugins, (pluginKey) => {
            const entry = createScriptEntry({ pluginKey });
            elements.scriptList.appendChild(entry);
            saveConfiguration();
        });
    } catch (e) {
        showConsoleMessage("Could not load plugins.", 'error');
    }
}

async function changeWorkspace() {
    try {
        const response = await fetch(`${API_BASE}/list_workspaces`);
        const workspaces = await response.json();
        showSelectionModal("Switch Workspace", workspaces, async (path) => {
            const res = await fetch(`${API_BASE}/set_workspace`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ path })
            });
            const data = await res.json();
            elements.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
            showConsoleMessage("Workspace changed to: " + data.workspace, 'success');
        });
    } catch (e) {
        showConsoleMessage("Could not list workspaces.", 'error');
    }
}

// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    // 1. Drag and Drop
    Sortable.create(elements.scriptList, { 
        animation: 150, 
        ghostClass: 'sortable-ghost',
        onEnd: saveConfiguration 
    });

    // 2. Button Listeners
    document.getElementById('add-global-step').onclick = openPluginModal;
    document.getElementById('saveConfig').onclick = saveConfiguration;
    document.getElementById('loadConfig').onclick = loadConfiguration;
    
    let selectedFile = null;
    elements.filePicker.onchange = (e) => {
        if (e.target.files[0]) {
            selectedFile = e.target.files[0];
            elements.fileDisplay.textContent = selectedFile.name;
            showConsoleMessage(`Selected file: ${selectedFile.name}`);
        }
    };

    document.getElementById('playAll').onclick = async () => {
        if (!selectedFile) return showConsoleMessage("Error: No file selected.", 'error');
        
        const activeScripts = Array.from(elements.scriptList.children)
            .filter(li => li.querySelector('input[type="checkbox"]').checked)
            .map(li => ({ pluginKey: li.dataset.pluginKey }));

        try {
            const response = await fetch(`${API_BASE}/execute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: selectedFile.name, scripts: activeScripts })
            });
            const result = await response.json();
            result.error ? showConsoleMessage(result.error, 'error') : showConsoleMessage("Process complete!", 'success');
        } catch (e) {
            showConsoleMessage("Execution failed: " + e.message, 'error');
        }
    };

    // 3. Initial Data Load
    loadConfiguration();
    fetch(`${API_BASE}/get_workspace`)
        .then(r => r.json())
        .then(data => {
            elements.workspaceDisplay.textContent = data.workspace.split(/[\\/]/).pop();
        });
});

// --- Console Resize ---
const resizeHandle = document.getElementById('resizeHandle');
const toolbar = document.getElementById('consoleToolbar');
resizeHandle.onmousedown = () => {
    document.onmousemove = (e) => {
        const h = window.innerHeight - e.clientY;
        if (h > 50 && h < 400) toolbar.style.height = `${h}px`;
    };
    document.onmouseup = () => document.onmousemove = null;
};