from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
import json
import random

app = FastAPI()

# Serve static files, including the HTML frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

# Define URLs for external services
image_processing_service_url = "http://127.0.0.1:5000/completion"
text_processing_service_url = "http://127.0.0.1:5002/completion"

@app.post("/process-data")
async def process_data(request: Request):
    data = await request.json()

    if "image_data" in data and "text" in data:
        # Both image and transcribed text available
        url = image_processing_service_url
        payload = {
            "prompt": data["text"],
            "image_data": [{"data": data["image_data"], "id": generate_random_id()}]
        }
    elif "image_data" in data:
        # Only image available
        url = image_processing_service_url
        payload = {
            "image_data": [{"data": data["image_data"], "id": generate_random_id()}]
        }
    elif "text" in data:
        # Only transcribed text available
        url = text_processing_service_url
        payload = {"prompt": data["text"]}
    else:
        return JSONResponse(content={"error": "No valid data received"}, status_code=400)

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        if response.status_code == 200:
            return response.json()
        else:
            return JSONResponse(content={"error": "Failed to process data"}, status_code=response.status_code)

def generate_random_id():
    return random.randint(1, 1000000)                                                                                                                                                                                                         

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
                                                                                                                                                                                                                                                                                        
        except websockets.exceptions.ConnectionClosed as e:                                                                                                                                                                                                                             
            print(f"WebSocket connection closed: {e}")                                                                                                                                                                                                                                  
            break                                                                                                                                                                                                                                                                       
        except Exception as e:                                                                                                                                                                                                                                                          
            print(f"An error occurred: {e}")                                                                                                                                                                                                                                            
            break     
