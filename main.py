import os
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

app = FastAPI()

# Get the absolute path to the 'static/dist' directory
dist_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), "static/dist"))

# Serve the 'dist' directory
app.mount("/dist", StaticFiles(directory=dist_directory), name="dist")

@app.get("/")
async def read_root():
    return FileResponse('static/dist/index.html')

@app.get("/dist/{file_path:path}")
async def serve_static_file(file_path: str):
    print("Serving file:", file_path)
    return FileResponse(dist_directory + "/" + file_path)

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

async def send_text_for_processing(text):
    # Prepare the data payload as JSON with all specified parameters
    data = json.dumps({
        "prompt": text,
        "n_predict": 30,
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
@app.post("/process-text-image")
async def process_text_image(text: str = Form(...), image: UploadFile = File(...)):
    # Convert image to base64 string
    image_content = await image.read()
    base64_string = base64.b64encode(image_content).decode()

    # Generate a unique ID for the image
    image_id = uuid.uuid4().int

    # Assemble data for the request
    data = {
        "prompt": text,
        "image_data": [
            {"data": base64_string, "id": image_id}
        ]
    }
    json_data = json.dumps(data)

    timeout = Timeout(10.0, connect=60.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post("http://127.0.0.1:5001/completion", headers={'Content-Type': 'application/json'}, content=json_data)
        if response.status_code == 200:
            decoded_response = response.json()
            return decoded_response.get('content')
        else:
            return f"Error: Received response code {response.status_code}"
    except httpx.ReadTimeout:
        return {"error": "Request timed out"}

# WebSocket endpoint for the frontend
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()                                                                                                                                                                                                                                                                                                                  
    while True:                                                                                                                                                                                                                                                                                                                               
        try:                                                                                                                                                                                                                                                                                                                                  
            # Receive audio data from the frontend                                                                                                                                                                                                                                                                                            
            audio_data = await websocket.receive_bytes()                                                                                                                                                                                                                                                                                      
                                                                                                                                                                                                                                                                                                                                              
            # Transcribe the audio using the external Whisper service                                                                                                                                                                                                                                                                         
            async with websockets.connect("ws://localhost:5000/ws") as ws:                                                                                                                                                                                                                                                                    
                await ws.send(audio_data)                                                                                                                                                                                                                                                                                                     
                transcribed_text = await ws.recv()                                                                                                                                                                                                                                                                                            
                                                                                                                                                                                                                                                                                                                                              
            # Send the transcribed text back to the frontend                                                                                                                                                                                                                                                                                  
            await websocket.send_text(json.dumps({"text": transcribed_text}))                                                                                                                                                                                                                                                                 
                                                                                                                                                                                                                                                                                                                                              
            processed_text = await send_text_for_processing(transcribed_text)                                                                                                                                                                                                                                                                 
            await websocket.send_text(json.dumps({"processed_text": processed_text}))                                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                                                                                                                              
            # Send the processed text to the Piper FastAPI service via WebSocket                                                                                                                                                                                                                                                              
            async with websockets.connect("ws://localhost:8000/ws/1") as piper_ws:                                                                                                                                                                                                                                                            
                # Prepare and send JSON data to Piper service                                                                                                                                                                                                                                                                                 
                json_data = json.dumps({"text": processed_text})                                                                                                                                                                                                                                                                              
                await piper_ws.send(json_data)                                                                                                                                                                                                                                                                                                
                                                                                                                                                                                                                                                                                                                                              
                # Receive the audio data from Piper service                                                                                                                                                                                                                                                                                   
                audio_data = await piper_ws.recv()                                                                                                                                                                                                                                                                                            
                                                                                                                                                                                                                                                                                                                                              
                # Send the audio data back to the client as binary data                                                                                                                                                                                                                                                                       
                await websocket.send_bytes(audio_data)                                                                                                                                                                                                                                                                                        
                                                                                                                                                                                                                                                                                                                                              
        except websockets.exceptions.ConnectionClosed as e:                                                                                                                                                                                                                                                                                   
            print(f"WebSocket connection closed: {e}")                                                                                                                                                                                                                                                                                        
            break                                                                                                                                                                                                                                                                                                                             
        except Exception as e:                                                                                                                                                                                                                                                                                                                
            print(f"An error occurred: {e}")                                                                                                                                                                                                                                                                                                  
            break                  
