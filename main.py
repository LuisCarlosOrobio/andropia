from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import websockets
import json

app = FastAPI()

# Serve static files, including the HTML frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

async def transcribe_audio(audio_data):
    async with websockets.connect("ws://localhost:5000/ws") as ws:
        await ws.send(audio_data)
        task_id = await ws.recv()

        # Fetch the result of the transcription task
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

        except websockets.exceptions.ConnectionClosed as e:
            print(f"WebSocket connection closed: {e}")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            break
