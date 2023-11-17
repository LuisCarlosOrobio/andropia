import os
import asyncio
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from whisper_jax import FlaxWhisperPipline
import jax.numpy as jnp
import tempfile
import rq
import redis
from rq.job import Job

# Set CUDA_VISIBLE_DEVICES environment variable
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

app = FastAPI()

app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
)

# Initialize Whisper model
MODEL_NAME = "openai/whisper-large-v2"
whisper_pipeline = FlaxWhisperPipline(MODEL_NAME, dtype=jnp.bfloat16, batch_size=16)

redis_conn = redis.Redis()
queue = rq.Queue(connection=redis_conn)

# Function to transcribe audio from a file
def transcribe_audio_task(file_path):
    try:
        with open(file_path, 'rb') as f:
            audio_data = f.read()
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

            # Save the audio data to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name

            # Enqueue the transcription task
            job = queue.enqueue('whisper_service.transcribe_audio_task', temp_file_path)
            # Send the task ID back through WebSocket
            await websocket.send_text(job.get_id())

    except WebSocketDisconnect as e:
        if e.code == 1000:
            print("Normal WebSocket disconnection.")
        else:
            print(f"WebSocket disconnected with error code: {e.code}")
    except Exception as e:
        print(f"An error occurred: {e}")

# Endpoint to get task status
@app.get("/status/{task_id}")
def get_task_status(task_id: str):
    job = Job.fetch(task_id, connection=redis_conn)

    if job.is_finished:
        return JSONResponse({"task_id": task_id, "status": "SUCCESS"})
    elif job.is_failed:
        return JSONResponse({"task_id": task_id, "status": "FAILURE"})
    else:
        return JSONResponse({"task_id": task_id, "status": "IN PROGRESS"})

# Endpoint to get task result
@app.get("/result/{task_id}")
def get_task_result(task_id: str):
    job = Job.fetch(task_id, connection=redis_conn)

    if job.is_finished:
        result_text = job.result

        return JSONResponse({"task_id": task_id, "status": "SUCCESS", "result": job.result})
    else:
        return JSONResponse({"task_id": task_id, "status": "IN PROGRESS or FAILED"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
