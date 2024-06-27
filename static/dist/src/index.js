import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import Grass from './Grass';

const mainBackendWebSocket = new WebSocket('wss://' + window.location.host + '/ws');
let menuContainer;
let scene;
let mixer, actions = {}, model, isWalking = false;
let audio;
let mediaRecorder;
let audioChunks = [];
let locationMessage = '';

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    document.body.appendChild(renderer.domElement);

    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.set(-7, 3, 7);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.maxPolarAngle = Math.PI / 2.2;
    controls.maxDistance = 15;
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x8FBCD4);

    const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 1.4);
    directionalLight.position.set(0, 1, 0);
    scene.add(directionalLight);

    const grass = new Grass(30, 100000);
    scene.add(grass);


const boundaries = {
minX: -7,
maxX: 7,
minZ: -7,
maxZ: 7
};

const warningThreshold = {
minX: -6.5,
maxX: 6.5,
minZ: -6.5,
maxZ: 6.5
};

const actionMappings = {
"walk": "Walking",
"walks": "Walking",
"walking": "Walking",
"move": "MovingArms",
"moves": "MovingArms",
"moving": "MovingArms",
"blink": "Blinking",
"blinks": "Blinking",
"blinking": "Blinking",
"smile": "Smiling",
"smiles": "Smiling",
"smiling": "Smiling",
};

mainBackendWebSocket.onopen = function(event) {
console.log('Connected to the WebSocket.');
};

function handleProcessedText(text) {
// Mapping of textual commands to animation actions

const matches = text.match(/Ava(?::|\])\[(.*?)\]/gi);
if (matches) {
    matches.forEach((match) => {
        const commands = match.slice(match.indexOf('[') + 1, -1).split(',').map(cmd => cmd.trim().toLowerCase());

        commands.forEach(command => {
            let stopAction = command.startsWith("stops") || command.startsWith("stop");

            // Normalize and split the command to check each part against action mappings
            let words = command.replace(/^(starts|start|stops|stop|begins|begin)\s*/gi, "").split(/\s+/);

            words.forEach(word => {
                let actionName = Object.keys(actionMappings).find(key => word.startsWith(key));
                if (actionName) {
                    let mappedAction = actionMappings[actionName];
                    if (stopAction) {
                        actions[mappedAction]?.stop();
                        if (mappedAction === 'Walking') isWalking = false;
                    } else {
                        actions[mappedAction]?.play();
                        if (mappedAction === 'Walking') isWalking = true;
                    }
                }
            });
        });
    });
}
}

document.addEventListener('keydown', (event) => {
if (event.key === 'r') {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.start();
        mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
    }).catch(err => {
        console.error("Error accessing media devices:", err);
    });
} else if (event.key === 's') {
    mediaRecorder.stop();
    mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        const messageData = JSON.stringify({
            type: 'audio_and_location',
            locationMessage: locationMessage
        });
        mainBackendWebSocket.send(audioBlob);
        mainBackendWebSocket.send(messageData);
        audioChunks = [];
        locationMessage = ''; 
    };
}
});

async function startModel() {
const brainInput = document.getElementById('brainSelect');
const promptInput = document.getElementById('promptInput');
const antiPromptInput = document.getElementById('antiPromptInput');
const assistantNameInput = document.getElementById('assistantNameInput');
const voiceInput = document.getElementById('voiceSelect');
const files = document.getElementById('gltfInput').files;

console.log('brainInput:', brainInput.value);
console.log('promptInput:', promptInput.value);
console.log('antiPromptInput:', antiPromptInput.value);
console.log('assistantNameInput:', assistantNameInput.value);
console.log('voiceInput:', voiceInput.value);
console.log('files:', files);

if (files.length === 0) {
    console.error("No files selected!");
    return;
}

let formData = new FormData();
Array.from(files).forEach(file => {
    if (!file.name.startsWith('.') && !file.name.endsWith('.DS_Store')) {
        formData.append('files', file);
    }
});

if (formData.has('files')) {
    try {
        const response = await fetch('/upload-gltf/', {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();
        console.log(result);
        if (response.ok) {
            processUploadedFiles(result.files); // Process files after successful upload
        } else {
            throw new Error(result.message || 'Upload failed');
        }
    } catch (error) {
        console.error('Error uploading files:', error);
    }
} else {
    console.error("No valid files to upload.");
}

// Send all these parameters to the backend
mainBackendWebSocket.send(JSON.stringify({ 
    command: 'start', 
    brain: brainInput.value, 
    system_prompt: promptInput.value,
    anti_prompt: antiPromptInput.value,
    assistant_name: assistantNameInput.value,
    voice: voiceInput.value
}));

if (menuContainer && document.body.contains(menuContainer)) {
    document.body.removeChild(menuContainer);
}

initScene(); // Initializes the 3D scene
}

function processUploadedFiles(files) {
const gltfFiles = files.filter(file => file.endsWith('.gltf'));
if (gltfFiles.length > 0) {
    gltfFiles.forEach(file => {
        loadModel(file);
    });
} else {
    console.error("No GLTF files found.");
}
}

document.body.onload = function() {

    const initialScreen = document.createElement('div');
    initialScreen.style.position = 'absolute';
    initialScreen.style.top = '50%';
    initialScreen.style.left = '50%';
    initialScreen.style.transform = 'translate(-50%, -50%)';
    initialScreen.style.textAlign = 'center';
    initialScreen.style.color = '#fff';
    initialScreen.style.fontFamily = 'Eurostile, Arial, sans-serif';
    initialScreen.innerHTML = `
    <style>
        @font-face {
            font-family: 'Eurostile';
            src: url('/dist/src/eurostile-2/eurostile.TTF') format('truetype');
        }

        @font-face {
            font-family: 'EuroStyleNormal';
            src: url('/dist/src/eurostile-2/EuroStyle Normal.ttf') format('truetype');
        }

        body {
            font-family: 'Eurostile', 'EuroStyleNormal', Arial, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            overflow: hidden; /* To prevent scrollbars */
            background: transparent; /* Ensure the body background is transparent */
        }

        .initial-logo {
            max-width: 1500px; /* Adjust logo size */
            margin-bottom: 20px;
        }

        .initial-message {
            font-size: 24px; /* Adjust message size */
        }
    </style>
    <audio id="background-audio" src="/dist/src/textures/SpokenRoses.m4a" loop></audio>
    <img src="/dist/src/textures/andropia.png" alt="Logo" class="initial-logo">
    <div class="initial-message">Press space to start</div>
    `;

    document.body.appendChild(initialScreen);

    const backgroundAudio = document.getElementById('background-audio');

    menuContainer = document.createElement('div');
    menuContainer.style.position = 'absolute';
    menuContainer.style.top = '50%';
    menuContainer.style.left = '50%';
    menuContainer.style.transform = 'translate(-50%, -50%)';
    menuContainer.style.display = 'none';
    menuContainer.innerHTML = `
    <style>
        .menu-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
            background-color: rgba(50, 50, 50, 0.7); /* Darker grey with more transparency */
            max-width: 400px;
            width: 100%;
            backdrop-filter: blur(10px); /* Adds a blur effect to the background */
        }

        .logo {
            max-width: 50px; /* Make the logo smaller */
            margin-bottom: 20px; /* Add some space below the logo */
        }

        .menu-container h1,
        .menu-container h2 {
            color: #fff; /* Change text color to white */
            margin: 15px 0;
            text-align: center;
            font-size: 20px; /* Slightly larger text */
        }

        .menu-container select,
        .menu-container input {
            width: 100%;
            padding: 12px;
            margin-bottom: 15px;
            border: 1px solid #ccc;
            border-radius: 10px;
            display: block; /* Ensure elements are block-level */
            background-color: rgba(255, 255, 255, 0.8); /* Slightly transparent white background for inputs */
        }

        .menu-container button {
            width: 100%; /* Ensure the button spans the width of the container */
            padding: 12px;
            margin-top: 20px; /* Add some space at the top to separate it from other elements */
            border: none;
            border-radius: 10px;
            background-color: #007bff;
            color: #fff;
            cursor: pointer;
            display: block; /* Ensure the button is block-level */
            font-size: 18px; /* Slightly larger button text */
        }

        .menu-container button:hover {
            background-color: #0056b3; /* Darker blue on hover */
        }
    </style>
    <div class="menu-container">
        <h1>CHOOSE YOUR AI'S BRAIN</h1>
        <select id="brainSelect">
            <option value="Mistral7B">Mistral 7B</option>
        </select>

        <h2>WRITE YOUR CONVERSATION PROMPT</h2>
        <input type="text" id="promptInput" placeholder="Enter conversation prompt" />

        <h2>WRITE YOUR NAME</h2>
        <input type="text" id="antiPromptInput" placeholder="Enter anti-prompt" />

        <h2>NAME YOUR AI</h2>
        <input type="text" id="assistantNameInput" placeholder="Enter assistant name" />

        <h2>UPLOAD YOUR AI'S BODY</h2>
        <input type="file" id="gltfInput" multiple accept=".gltf,.glb,.png,.jpg,.jpeg,.bin">

        <h2>CHOOSE YOUR AI'S VOICE</h2>
        <select id="voiceSelect">
            <option value="en_US-lessac-medium.onnx">en_US-lessac-medium.onnx</option>
        </select>

        <button id="startButton">START</button>
    </div>
    `;
    document.body.appendChild(menuContainer);
    document.getElementById('startButton').addEventListener('click', function() {
        startModel();
        backgroundAudio.pause(); // Stop the audio when the "START" button is clicked
    });

    document.addEventListener('keydown', function(event) {
        if (event.code === 'Space') {
            initialScreen.style.display = 'none';
            menuContainer.style.display = 'flex';
            backgroundAudio.play().catch(error => {
                console.log('Autoplay was prevented. User interaction is required to play the audio.');
            });
        }
    });
};

function initScene() {
    console.log("Scene initialized");
}

function loadModel(gltfUrl) {
console.log("Loading model from:", gltfUrl);
const loader = new GLTFLoader();
const fullPathToGLTF = `/dist/src/textures/${gltfUrl}`;
loader.load(fullPathToGLTF, function (gltf) {
    model = gltf.scene;
    model.scale.set(0.02, 0.02, 0.02);
    model.position.set(0.5, 0.5, 0.5);
    scene.add(model);
    
    mixer = new THREE.AnimationMixer(model);
    gltf.animations.forEach(clip => {
        actions[clip.name] = mixer.clipAction(clip);
    });
    
    setupWebSocketHandlers(); // Setup WebSocket handlers after the model is loaded
}, undefined, function (error) {
    console.error('An error occurred while loading the GLTF model:', error);
});
}

function setupWebSocketHandlers() {
mainBackendWebSocket.onmessage = function(event) {
    console.log('Received message from WebSocket:', event.data);
    try {
        if (event.data instanceof Blob) {
            const audioUrl = URL.createObjectURL(event.data);
            audio = new Audio(audioUrl);
            
            audio.onplay = () => {
                if (actions['Talking']) actions['Talking'].play();
                else console.log('No talking action found');
            };

            audio.onended = () => {
                if (actions['Talking']) actions['Talking'].stop();
                else console.log('No talking action found');
            };

            audio.play();
        } else {
            const data = JSON.parse(event.data);
            if (data.processed_text) {
                console.log("Processed text for animation:", data.processed_text);
                handleProcessedText(data.processed_text);
            } else {
                console.log('Message from server:', event.data);
            }
        }
    } catch (error) {
        console.error("Error processing message:", error);
    }
};
}

const clock = new THREE.Clock();
renderer.setAnimationLoop((time) => {
    const delta = clock.getDelta();
    if (mixer) mixer.update(delta);


if (isWalking) {
    let nextX = model.position.x + 0.01;  // Example movement increment
    let message = "";

    // Check and clamp the position within boundaries
    if (nextX < boundaries.minX || nextX > boundaries.maxX) {
        message = "You have now reached the limits of the world, either stop walking or turn around";
        isWalking = false;  // Optional: stop the model from walking
    } else if (nextX < warningThreshold.minX || nextX > warningThreshold.maxX) {
        message = "You are walking close to the limits of the world, be careful";
    }

    // Update position only if within outer boundaries
    if (nextX >= boundaries.minX && nextX <= boundaries.maxX) {
        model.position.x = nextX;
    }

    // Display the message if needed
    if (message) {
        console.log(message);
        locationMessage = message;
    }
}

grass.update(time);
controls.update();
renderer.render(scene, camera);

});
