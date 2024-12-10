const targetpath = document.getElementById('targetPath');
const scriptList = document.getElementById('scriptList');
const playAllButton = document.getElementById('playAll');
const loadConfigButton = document.getElementById('loadConfig');
// Initialize drag-and-drop list using SortableJS
Sortable.create(scriptList, { 
    animation: 150,
    onEnd: (event) => {
        // Logic to handle reordering if necessary
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

// Function to create a script entry with plus button, description, and file path
function createScriptEntry(name, description = '', filePath = '', checked = '') {
    const li = document.createElement('li');
    li.className = "bg-white p-2 rounded shadow-md flex items-center justify-between relative";

    // Checkbox + Script Name
    const label = document.createElement('label');
    label.className = "flex items-center space-x-3";

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = checked;
    checkbox.className = "h-5 w-5 text-blue-600";

    const span = document.createElement('span');
    span.textContent = name;
    span.className = "text-lg font-medium";

    label.appendChild(checkbox);
    label.appendChild(span);

    // Create description input
    const descriptionInput = document.createElement('input');
    descriptionInput.type = 'text';
    descriptionInput.placeholder = 'Description';
    descriptionInput.value = description;
    descriptionInput.className = "ml-4 border border-gray-300 rounded px-2 py-1 w-1/2";

    // Create file path input
    const filePathInput = document.createElement('input');
    filePathInput.type = 'text';
    filePathInput.placeholder = 'File Path';
    filePathInput.value = filePath;
    filePathInput.className = "ml-2 border border-gray-300 rounded px-2 py-1 w-1/2";

    // Create a plus sign button
    const plusButton = document.createElement('button');
    updateActionButton(); // Set initial state
    
    // Append elements to the list item
    li.appendChild(label);
    li.appendChild(descriptionInput);
    li.appendChild(filePathInput);
    li.appendChild(plusButton);
    scriptList.appendChild(li);

    // Show the plus button when mouse is over the item
    li.addEventListener('mouseenter', () => {
        //plusButton.querySelector('svg').classList.remove('hidden');
    });

    // Hide the plus button when mouse leaves the item
    li.addEventListener('mouseleave', () => {
        //plusButton.querySelector('svg').classList.add('hidden');
    });

    // Update the button state based on checkbox
    checkbox.addEventListener('change', () => {
        updateActionButton();
    });

    // Handle adding a new step when the plus button is clicked
    plusButton.addEventListener('click', () => {
        if (checkbox.checked) {
            const newEntry = createScriptEntry();
            scriptList.insertBefore(newEntry, li);
        } else {
            // Remove the item from the list
            li.remove();
        }
    });

    function updateActionButton() {
        if (checkbox.checked) {
            plusButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                </svg>`;
            plusButton.className = "bg-slate-100 text-white px-2 py-1 rounded ml-2"; // Style for the plus button
        } else {
            plusButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4" />
                </svg>`;
            plusButton.className = "bg-slate-100 px-2 py-1 rounded ml-2"; // Style for the minus button
        }
    }

    return li; // Return the created list item
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

// Execute the active scripts in order when "Play" is clicked
playAllButton.addEventListener('click', async () => {
    const activeScripts = Array.from(scriptList.children)
        .filter(li => li.querySelector('input[type="checkbox"]').checked)
        .map(li => ({
            name: li.querySelector('span').textContent,
            description: li.querySelector('input[placeholder="Description"]').value,
            filePath: li.querySelector('input[placeholder="File Path"]').value,
        }));

    if (activeScripts.length === 0) {
        alert('No scripts selected to run!');
        return;
    }

    try {
        const response = await fetch('http://localhost:5000/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ scripts: activeScripts })
        });

        const results = await response.json();
        console.log('Execution Results:', results);
    } catch (error) {
        console.error('Error executing scripts:', error);
        showError(`Error executing ${error.script}: ${error.stderr}`)
    }
});

// Load Example Scripts on startup
async function loadExampleScripts() {
    try {
        const response = await fetch('http://localhost:5000/example_scripts');
        if (response.ok) {
            const exampleScripts = await response.json();
            exampleScripts.forEach(({ name, description, filePath, isChecked }) => {
                scriptList.appendChild(createScriptEntry(name, description, filePath, isChecked));
            });
        }
    } catch (error) {
        console.error('Error loading example scripts:', error);
    }
}

loadExampleScripts();  // Call function to load example scripts on startup