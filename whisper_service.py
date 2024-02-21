import os
from fastapi import FastAPI, WebSocket
import websockets
import tempfile
from whisper_jax import FlaxWhisperPipline
import jax.numpy as jnp

# Set CUDA_VISIBLE_DEVICES environment variable
os.environ["CUDA_VISIBLE_DEVICES"] = "1"

app = FastAPI()

# Initialize Whisper model
MODEL_NAME = "openai/whisper-large-v2"
whisper_pipeline = FlaxWhisperPipline(MODEL_NAME, dtype=jnp.bfloat16, batch_size=16)

# Function to transcribe audio from a file
async def transcribe_audio(audio_data):
    try:
        # Transcribe using Whisper pipeline
        result = whisper_pipeline(audio_data)
        return result['text']
    except Exception as e:
        # Log the error or handle it appropriately
        return str(e)

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Receive audio file as binary data
            audio_data = await websocket.receive_bytes()
            
            # Transcribe the audio data
            transcribed_text = await transcribe_audio(audio_data)
            
            # Send the transcribed text back through WebSocket
            await websocket.send_text(transcribed_text)
    
    except websockets.exceptions.ConnectionClosed as e:
        if e.code == 1000:
            print("Normal WebSocket disconnection.")
        else:
            print(f"WebSocket disconnected with error code: {e.code}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
