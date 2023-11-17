from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx

app = FastAPI()

# Serve static files, including the HTML frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

# WebSocket endpoint for the frontend
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        audio_data = await websocket.receive_bytes()

        # Establish a WebSocket connection with the Whisper service
        async with httpx.AsyncClient() as client:
            async with client.websocket_connect("ws://localhost:5000/whisper") as whisper_websocket:
                await whisper_websocket.send_bytes(audio_data)
                transcribed_text = await whisper_websocket.receive_text()

                # Send the transcribed text back to frontend
                await websocket.send_text(transcribed_text)
