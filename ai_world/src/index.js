import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader';
import Grass from './Grass';


const mainBackendWebSocket = new WebSocket('wss://' + window.location.host + '/ws');
let mediaRecorder;
let audioChunks = [];

mainBackendWebSocket.onopen = function(event) {
    console.log('Connected to the WebSocket.');
};

mainBackendWebSocket.onmessage = function(event) {
    if (event.data instanceof Blob) {
        const audioUrl = URL.createObjectURL(event.data);
        new Audio(audioUrl).play();
    } else {
        console.log('Message from server:', event.data);
    }
};

// Add event listeners for recording and stopping audio
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
const fbxLoader = new FBXLoader();
fbxLoader.load(
  'src/CartoonGirl.fbx60AAAED5-3FC2-4496-9F30-0800D1DC368A.fbx', // Replace with the path to your FBX file
  function (fbx) {
    const model = fbx;
    scene.add(model);

    // Update the model scale, position, and rotation
    model.scale.set(8, 8, 8);
    model.position.set(2, 2, 2);
    model.rotation.set(0, 0, 0);

    const normal = new THREE.Vector3(0, 1, 0);
    const light = new THREE.DirectionalLight(0xffffff, 1);
    light.position.set(normal.x, normal.y, normal.z);
    scene.add(light);

    light.target.position.copy(model.position);
    scene.add(light.target);


    model.traverse((child) => {
        if (child.isMesh) {
                child.rotation.y = 60 * (Math.PI / 180);
                child.material.emissive = new THREE.Color(0x404040);
                child.material.emissiveIntensity = 0.8;
        }
        });


    // Update camera to look at the model
    camera.lookAt(model.position);
    controls.target.set(model.position.x, model.position.y, model.position.z);

    // Update the camera's projection matrix
    camera.updateProjectionMatrix();
  },
  function ( xhr ) {
    console.log((xhr.loaded / xhr.total) * 100 + '% loaded');
  },-                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          
  function ( error ) {                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         
    console.log('An error happened', error);                                                                                                                                                                                                                                                                                                                                                                                                                                                                   
  }                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            
);                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               
// Animation loop                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              
renderer.setAnimationLoop((time) => {                                                                                                                                                                                                                                                                                                                                                                                                                                                                          
  grass.update(time);                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               
  controls.update();                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           
  renderer.render(scene, camera);                                                                                                                                                                                                                                                                                                                                                                                                                                                                              
});                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               

