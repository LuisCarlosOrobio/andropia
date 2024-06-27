import os
import subprocess
from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import websockets
from httpx import Timeout
import httpx
import json
import base64
import uuid
import re
import shutil

app = FastAPI()

dist_directory = "/root/maip3/static/dist"
textures_directory = "/root/maip3/static/dist/src/textures"

# Serve the 'dist' directory
app.mount("/dist", StaticFiles(directory=dist_directory), name="dist")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    # Serve 'index.html' from the 'dist' directory
    return FileResponse(os.path.join(dist_directory, "index.html"))

@app.get("/dist/{file_path:path}")
async def serve_static_file(file_path: str):
    print("Serving file:", file_path)
    return FileResponse(dist_directory + "/" + file_path)

def start_server(brain_model):
    if brain_model == "Mistral7B":
        # Execute the bash script to start the server
        subprocess.Popen(["/root/maip3/start_server.sh"])

@app.post("/upload-gltf/")
async def upload_gltf(files: list[UploadFile] = File(...)):
    uploaded_files = []
    os.makedirs(textures_directory, exist_ok=True)
    for file in files:
        file_path = os.path.join(textures_directory, file.filename)
        try:
            with open(file_path, "wb") as file_object:
                shutil.copyfileobj(file.file, file_object)
            uploaded_files.append(file.filename)
            print(f"Uploaded {file.filename} to {file_path}")
        except Exception as e:
            print(f"Failed to save {file.filename}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to save {file.filename}: {str(e)}")
    return {"files": uploaded_files}  # Return the list of uploaded file names


@app.get("/list-gltf-files")
async def list_gltf_files():
    gltf_files = [f for f in os.listdir(textures_directory) if f.endswith('.gltf')]
    return {"files": gltf_files}

@app.post("/start-server/{brain_model}")
async def start_server_endpoint(brain_model: str):
    # Call the function to start the server
    start_server(brain_model)
    return {"message": f"Server for {brain_model} starting asynchronously"}

async def transcribe_audio(audio_data):
    async with websockets.connect("ws://localhost:5000/ws") as ws:
        await ws.send(audio_data)
        task_id = await ws.recv()
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:5000/result/{task_id}")
            if response.status_code == 200:
                result = response.json()
                if result['status'] == 'SUCCESS':
                    return result['result']
                else:
                   return "Transcription in progress or failed"
            else:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch task result.")

text_processing_service_url = "http://127.0.0.1:5002/completion"

async def send_text_for_processing(prompt, anti_prompt, assistant_name, text):
    # Prepare the data payload as JSON with dynamically received parameters
    data = json.dumps({
        "system_prompt": {
            "prompt": prompt,  # This now takes the whole prompt string from the frontend
            "anti_prompt": anti_prompt,  # Specific words or phrases to avoid in responses
            "assistant_name": assistant_name  # Name of the AI assistant
        },
        "prompt": text,  # The text for which a response is being generated
        "n_predict": 30,  # Number of predictions to make (can be made dynamic as well)
         "sampling": {
            "repeat_last_n": 64,
            "repeat_penalty": 1.1,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "top_k": 40,
            "tfs_z": 1.0,
            "top_p": 0.95,
            "typical_p": 1.0,
            "temperature": 0.7,
            "mirostat": 0,
            "mirostat_lr": 0.1,
            "mirostat_ent": 5.0,
            "stream": True
        }
    })

    async with httpx.AsyncClient() as client:
        response = await client.post(text_processing_service_url, headers={'Content-Type': 'application/json'}, content=data)
        if response.status_code == 200:
            decoded_response = response.json()
            return decoded_response.get('content')
        else:
            return f"Error: Received response code {response.status_code}"

# Endpoint to process text and image
#@app.post("/process-text-image")
#async def process_text_image(text: str = Form(...), image: UploadFile = File(...)):
    # Convert image to base64 string
    #image_content = await image.read()
    #base64_string = base64.b64encode(image_content).decode()

    # Generate a unique ID for the image
    #image_id = uuid.uuid4().int

    # Assemble data for the request
    #data = {
    #    "prompt": text,
    #    "image_data": [
    #        {"data": base64_string, "id": image_id}
    #    ]
    #}
    #json_data = json.dumps(data)

    #timeout = Timeout(10.0, connect=60.0)

    #try:
    #    async with httpx.AsyncClient(timeout=timeout) as client:
    #        response = await client.post("http://127.0.0.1:5001/completion", headers={'Content-Type': 'application/json'}, content=json_data)
    #    if response.status_code == 200:
    #        decoded_response = response.json()
    #        return decoded_response.get('content')
    #    else:
    #        return f"Error: Received response code {response.status_code}"
    #except httpx.ReadTimeout:
    #    return {"error": "Request timed out"}
    
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    setup_complete = False
    brain_model = None
    prompt = None
    anti_prompt = None
    assistant_name = None
    voice_model = None

    try:
        while True:
            if not setup_complete:
                # First step: Handle initial setup including brain model selection
                message = await websocket.receive_text()
                try:
                    command_json = json.loads(message)
                    if command_json.get('command') == 'start' and all(k in command_json for k in ['brain', 'system_prompt', 'anti_prompt', 'assistant_name']):
                        brain_model = command_json['brain']
                        prompt = command_json['system_prompt']
                        anti_prompt = command_json['anti_prompt']
                        assistant_name = command_json['assistant_name']
                        voice_model = command_json['voice']

                        # Start the server using the specified brain model
                        start_server(brain_model)
                        await websocket.send_text(json.dumps({"status": "Model starting", "brain_model": brain_model}))

                        setup_complete = True  # Mark setup as complete, allowing other processes to proceed
                        await websocket.send_text(json.dumps({
                            "message": "Setup complete. You can now start sending data for processing."
                        }))
                    else:
                        await websocket.send_text(json.dumps({"error": "All setup parameters must be provided"}))
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
                    continue
        
            else:
                # Once the model is selected, handle other activities such as audio processing
                audio_data = await websocket.receive_bytes()

                # Transcribe the audio using the external Whisper service
                async with websockets.connect("ws://localhost:5000/ws") as ws:
                    await ws.send(audio_data)
                    transcribed_text = await ws.recv()

                # Assume location data might be sent right after audio
                try:
                    # Attempt to receive a JSON message with location data
                    json_data = await websocket.receive_text()
                    data = json.loads(json_data)
                    if "locationMessage" in data:
                        transcribed_text += " " + data["locationMessage"]
                except:
                    # If no JSON message or wrong format, just proceed
                    pass

                # Send the transcribed text back to the frontend
                await websocket.send_text(json.dumps({"text": transcribed_text}))

                processed_text = await send_text_for_processing(prompt, anti_prompt, assistant_name, transcribed_text)
                await websocket.send_text(json.dumps({"processed_text": processed_text}))

                #modified_text_search = re.search(r"\nAva:\s*(?:\[[^\]]*\])*\s*(.*?)(?=\n\w+:|$)", processed_text)
                #modified_text = modified_text_search.group(1) if modified_text_search else ""
                modified_text = processed_text

                # Send the processed text to the Piper FastAPI service via WebSocket
                async with websockets.connect("ws://localhost:8000/ws/1") as piper_ws:
                    json_data = json.dumps({"text": modified_text, "model": voice_model})
                    await piper_ws.send(json_data)

                    # Receive the audio data from Piper service
                    audio_data = await piper_ws.recv()

                    # Send the audio data back to the client as binary data
                    await websocket.send_bytes(audio_data)

    except websockets.exceptions.ConnectionClosed as e:
        print(f"WebSocket connection closed: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    import uvicorn
