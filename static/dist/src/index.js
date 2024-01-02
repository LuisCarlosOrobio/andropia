import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import Grass from './Grass';

const mainBackendWebSocket = new WebSocket('wss://' + window.location.host + '/ws');

let mixer, action;
let audio;
let morphTargetMesh;
let mediaRecorder;
let audioChunks = [];

mainBackendWebSocket.onopen = function(event) {
    console.log('Connected to the WebSocket.');
};

mainBackendWebSocket.onmessage = function(event) {
    if (event.data instanceof Blob) {
        const audioUrl = URL.createObjectURL(event.data);
        audio = new Audio(audioUrl);
        audio.onplay = () => { if (action) action.paused = false; };
        audio.onended = () => { if (action) action.paused = true; };
        audio.play();
    } else {
        console.log('Message from server:', event.data);
    }
};

// Add event listeners for recording and stopping audio
let mediaRecorder;
let audioChunks = [];
document.addEventListener('keydown', (event) => {
    if (event.key === 'r') { // Press 'r' to start recording
        navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.start();
            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
        }).catch(err => {
            console.error("Error accessing media devices:", err);
        });
    }
    else if (event.key === 's') { // Press 's' to stop recording
        mediaRecorder.stop();
        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            mainBackendWebSocket.send(audioBlob);
            audioChunks = []; // Reset chunks for next recording
        };
    }
});

// Renderer setup
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// Camera setup
const camera = new THREE.PerspectiveCamera(
  75,
  window.innerWidth / window.innerHeight,
  0.1,
  100
);
camera.position.set(-7, 3, 7);

// OrbitControls setup
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.enablePan = false;
controls.maxPolarAngle = Math.PI / 2.2;
controls.maxDistance = 15;

// Scene setup
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x8FBCD4); // A light blue background color

// Lighting setup
const ambientLight = new THREE.AmbientLight(0x404040, 0.5); // soft white light
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xffffff, 1.4);
directionalLight.position.set(0, 1, 0);
scene.add(directionalLight);

// Grass setup
const grass = new Grass(30, 100000);
scene.add(grass);

// GLTF Model Loading
const gltfLoader = new GLTFLoader();
gltfLoader.load(
  'dist/src/textures/suit girl update NEW.gltf', // Replace with the path to your glTF file
  function (gltf) {
    const model = gltf.scene;
    model.scale.set(0.02, 0.02, 0.02); // Set the scale of the model
    model.position.set(0.5, 0.5, 0.5); // Set the position of the model
    scene.add(model); // Add the model to the scene

    mixer = new THREE.AnimationMixer(model)
    action = mixer.clipAction(gltf.animations[0]);
    action.play();
    action.paused = true;
    
    // Set up the lighting to illuminate the model
    const light = new THREE.DirectionalLight(0xffffff, 1);
    light.position.set(0, 1, 0); // Position the light
    scene.add(light); // Add the light to the scene

    // Update camera to look at the model
    camera.lookAt(model.position);
    controls.target.copy(model.position);
    camera.updateProjectionMatrix(); // Update the camera's projection matrix

    // Discover and log all morph targets that match the pattern
model.traverse((object) => {
      if (object.isMesh && object.morphTargetInfluences) {
        console.log('Morph Target Mesh found:', object);

        // Log all morph target names
        if (object.morphTargetDictionary) {
          console.log('Morph Target Names:', Object.keys(object.morphTargetDictionary));
        }
      }
    });
  },
  function (xhr) {
    console.log(`${(xhr.loaded / xhr.total * 100).toFixed(2)}% loaded`); // Log the loading progress
  },
  function (error) {
    console.error('An error happened', error); // Log any errors that occur
  }
);

// Animation loop
renderer.setAnimationLoop((time) => {
    if (mixer) mixer.update(time * 0.001); // Update the animation mixer
    grass.update(time);
    controls.update();
    renderer.render(scene, camera);
});
