const scriptList = document.getElementById('scriptList');
const playAllButton = document.getElementById('playAll');
const loadConfigButton = document.getElementById('loadConfig');
// Initialize drag-and-drop list using SortableJS
Sortable.create(scriptList, { 
    animation: 150,
    onEnd: () => {
        // Automatically save the new order to the backend
        document.getElementById('saveConfig').click();
    }
});

const consoleToolbar = document.getElementById('consoleToolbar');
const resizeHandle = document.getElementById('resizeHandle');

let isResizing = false;

resizeHandle.addEventListener('mousedown', (e) => {
    isResizing = true;
    document.body.style.cursor = 'ns-resize'; // Change cursor to resize
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;

    const newHeight = window.innerHeight - e.clientY;
    const minHeight = 50;
    const maxHeight = 400;

    // Clamp the height within allowed bounds
    if (newHeight >= minHeight && newHeight <= maxHeight) {
        consoleToolbar.style.height = `${newHeight}px`;
    }
});

document.addEventListener('mouseup', () => {
    if (isResizing) {
        isResizing = false;
        document.body.style.cursor = ''; // Reset cursor
    }
});

function showMessage(message) {
    const consoleContent = document.getElementById('consoleContent');

    // Clear the default message if no other message exists
    if (consoleContent.children[0].textContent === 'No messages yet.') {
        consoleContent.innerHTML = '';
    }

    // Create and append the new message
    const messageElement = document.createElement('p');
    messageElement.textContent = message;
    consoleContent.appendChild(messageElement);

    // Scroll to the bottom to display the latest message
    consoleContent.scrollTop = consoleContent.scrollHeight;
}

// Add these functions to scripts.js

async function openPluginModal() {
    const response = await fetch('http://localhost:5000/list_plugins');
    const plugins = await response.json();
    const list = document.getElementById('pluginList');
    list.innerHTML = '';

    plugins.forEach(pluginKey => {
        const li = document.createElement('li');
        li.className = "p-2 hover:bg-blue-100 cursor-pointer border-b";
        li.textContent = pluginKey;
        li.onclick = () => {
            addStepToUI(pluginKey);
            closePluginModal();
        };
        list.appendChild(li);
    });
    document.getElementById('pluginModal').classList.remove('hidden');
}

function addStepToUI(pluginKey) {
    const scriptList = document.getElementById('scriptList');
    const entry = createScriptEntry({ 
        name: pluginKey, 
        isChecked: true,
        pluginKey: pluginKey 
    });
    scriptList.appendChild(entry);
}

function closePluginModal() {
    document.getElementById('pluginModal').classList.add('hidden');
}

// Update the "Add Step" button listener
document.getElementById('add-global-step').onclick = openPluginModal;
function createScriptEntry({name = '', description = '', filePath = '', isChecked = false, pluginKey = ''} = {}) {
    const li = document.createElement('li');
    li.className = "bg-white p-4 rounded shadow-md flex items-center justify-between border-l-4 border-blue-500";
    
    // Store the plugin identifier in a data attribute
    li.dataset.pluginKey = pluginKey || name;

    const mainControls = document.createElement('div');
    mainControls.className = "flex items-center space-x-4 flex-grow";

    // Checkbox
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = isChecked;
    checkbox.className = "h-5 w-5 text-blue-600 cursor-pointer";

    // Text Container
    const textInfo = document.createElement('div');
    textInfo.className = "flex flex-col flex-grow";
    
    const title = document.createElement('span');
    title.textContent = pluginKey || "Select a function...";
    title.className = "text-sm font-mono font-bold text-gray-700";
    
    const descInput = document.createElement('input');
    descInput.type = 'text';
    descInput.value = description;
    descInput.placeholder = "Add a note about this step...";
    descInput.className = "text-xs text-gray-500 bg-transparent border-none focus:ring-0 p-0";

    textInfo.appendChild(title);
    textInfo.appendChild(descInput);

    mainControls.appendChild(checkbox);
    mainControls.appendChild(textInfo);

    // Delete Button
    const deleteBtn = document.createElement('button');
    deleteBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-red-400 hover:text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>`;
    deleteBtn.onclick = () => li.remove();

    li.appendChild(mainControls);
    li.appendChild(deleteBtn);

    return li;
}

// Load Configuration (Reads a text file with script names)
loadConfigButton.addEventListener('click', async () => {
    try {
        const response = await fetch('http://localhost:5000/load');
        if (response.ok) {
            const scripts = await response.json();
            // Clear the existing list and add new scripts
            scriptList.innerHTML = '';
            scripts.forEach(({ name, description, filePath, isChecked }) => {
                scriptList.appendChild(createScriptEntry(name, description, filePath, isChecked));
            });
        } else {
            alert('Failed to load configuration!');
        }
    } catch (error) {
        console.error('Error loading configuration:', error);
    }
});

// Save Configuration (Sends script data to the Python backend)
document.getElementById('saveConfig').addEventListener('click', async () => {
    const scriptsData = Array.from(scriptList.children).map(li => ({
        name: li.querySelector('span').textContent,
        description: li.querySelector('input[placeholder="Description"]').value,
        filePath: li.querySelector('input[placeholder="File Path"]').value,
        isChecked: li.querySelector('input[type="checkbox"]').checked
    }));

    try {
        const response = await fetch('http://localhost:5000/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(scriptsData)
        });

        if (response.ok) {
            showMessage('Configuration saved successfully!');
        } else {
            showMessage('Failed to save configuration!');
        }
    } catch (error) {
        console.error('Error saving configuration:', error);
    }
});

// Helper to update the UI console
function showConsoleMessage(msg, type) {
    const consoleContent = document.getElementById('consoleContent');
    const entry = document.createElement('div');
    entry.className = type === 'error' ? 'text-red-400 font-mono' : 'text-white font-mono';
    entry.textContent = `> [${new Date().toLocaleTimeString()}] ${msg}`;
    consoleContent.appendChild(entry);
}

// On page load, get the saved workspace
async function initWorkspace() {
    const response = await fetch('http://localhost:5000/get_workspace');
    const data = await response.json();
    document.getElementById('workspaceDisplay').textContent = data.workspace;
}

// Allow user to manually update the workspace
async function changeWorkspace() {
    const newPath = prompt("Enter the absolute path to your G-Code folder:", 
                          document.getElementById('workspaceDisplay').textContent);
    
    if (newPath) {
        const response = await fetch('http://localhost:5000/set_workspace', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ path: newPath })
        });
        
        const data = await response.json();
        if (response.ok) {
            document.getElementById('workspaceDisplay').textContent = data.workspace;
            showConsoleMessage("Workspace updated!", "success");
        } else {
            alert("Error: " + data.error);
        }
    }
}

initWorkspace();


let selectedFile = null;

document.getElementById('filePicker').addEventListener('change', function(e) {
    if (e.target.files.length > 0) {
        selectedFile = e.target.files[0];
        
        // Update the display (Abbreviated name)
        const display = document.getElementById('fileDisplay');
        display.textContent = selectedFile.name; 
        display.title = "Full path not available via browser security"; // Tooltip explanation
        
        showConsoleMessage(`Selected file: ${selectedFile.name}`, 'info');
    }
});

playAllButton.addEventListener('click', async () => {
    if (!selectedFile) {
        showConsoleMessage("Error: No file selected.", 'error');
        return;
    }

    const activeScripts = Array.from(document.querySelectorAll('#scriptList li'))
        .filter(li => li.querySelector('input[type="checkbox"]').checked)
        .map(li => ({
            // This matches the key expected by the Python backend
            pluginKey: li.dataset.pluginKey 
        }));
        
    if (activeScripts.length === 0) {
        showConsoleMessage("Warning: No active steps to run.", 'info');
        return;
    }

    try {
        const response = await fetch('http://localhost:5000/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                filename: selectedFile.name, 
                scripts: activeScripts 
            })
        });
        
        const data = await response.json();
        if (response.ok) {
            showConsoleMessage(`Successfully processed ${selectedFile.name}`, 'success');
        } else {
            showConsoleMessage(`Backend Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showConsoleMessage(`Connection Error: ${error.message}`, 'error');
    }
});

let currentModalContext = 'workspace'; // 'plugins' or 'workspace'

async function changeWorkspace() {
    const response = await fetch('http://localhost:5000/list_workspaces'); // New endpoint
    const workspaces = await response.json();
    
    showModal("Switch Workspace", workspaces, (path) => {
        setWorkspace(path);
    });
}

function showModal(title, items, onSelect) {
    const modal = document.getElementById('selectionModal');
    const modalList = document.getElementById('modalList');
    document.getElementById('modalTitle').textContent = title;
    
    modalList.innerHTML = '';
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
        modalList.appendChild(li);
    });
    
    modal.classList.remove('hidden');
}

async function setWorkspace(path) {
    const response = await fetch('http://localhost:5000/set_workspace', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: path })
    });
    const data = await response.json();
    document.getElementById('workspaceDisplay').textContent = data.workspace;
}



window.addEventListener('DOMContentLoaded', async () => {
    // 1. Get Workspace Name
    try {
        const resp = await fetch('http://localhost:5000/get_workspace');
        const data = await resp.json();
        // Extract just the folder name from the full path for a cleaner look
        const folderName = data.workspace.split(/[\\/]/).pop() || data.workspace;
        document.getElementById('workspaceDisplay').textContent = folderName;
        document.getElementById('workspaceDisplay').title = data.workspace; // Full path on hover
    } catch (e) {
        document.getElementById('workspaceDisplay').textContent = "Default";
    }

    // 2. Automatically load the last saved sequence
    loadConfiguration();
});

function closeModal() { document.getElementById('selectionModal').classList.add('hidden'); }

// Load Button Logic
async function loadConfiguration() {
    try {
        const response = await fetch('http://localhost:5000/load');
        const steps = await response.json();
        const list = document.getElementById('scriptList');
        list.innerHTML = ''; // Clear current
        
        steps.forEach(step => {
            const entry = createScriptEntry(step);
            list.appendChild(entry);
        });
        showConsoleMessage("Configuration loaded.", 'info');
    } catch (e) {
        showConsoleMessage("No saved configuration found.", 'info');
    }
}

// Save Button Logic
async function saveConfiguration() {
    const steps = Array.from(document.querySelectorAll('#scriptList li')).map(li => ({
        pluginKey: li.dataset.pluginKey,
        description: li.querySelector('input[type="text"]').value,
        isChecked: li.querySelector('input[type="checkbox"]').checked
    }));

    await fetch('http://localhost:5000/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(steps)
    });
    showConsoleMessage("Sequence saved to configuration.json", 'success');
}
document.getElementById('saveConfig').onclick = saveConfiguration;
document.getElementById('loadConfig').onclick = loadConfiguration;