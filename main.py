from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import websockets
import asyncio

app = FastAPI()

# Serve static files, including the HTML frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

# Function to handle transcription using an external WebSocket service
async def transcribe_audio(audio_data):
    async with websockets.connect("ws://localhost:5000/whisper") as ws:
        await ws.send(audio_data)
        return await ws.recv()

# WebSocket endpoint for the frontend
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            # Receive audio data from the frontend
            audio_data = await websocket.receive_bytes()
            
            # Transcribe the audio using the external service
            transcribed_text = await transcribe_audio(audio_data)
            
            # Send the transcribed text back to the frontend
            await websocket.send_text(transcribed_text)

        except websockets.exceptions.ConnectionClosed as e:
            print(f"WebSocket connection closed: {e}")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            break
