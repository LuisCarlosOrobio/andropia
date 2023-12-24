import os
import uuid
import time
from fastapi import FastAPI, WebSocket, Form
from fastapi.responses import FileResponse
from tortoise.api import TextToSpeech
from tortoise.utils.audio import load_voice
import torchaudio
from apscheduler.schedulers.background import BackgroundScheduler
from starlette.background import BackgroundTasks

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
app = FastAPI()

# Initialize Tortoise TTS
tts = TextToSpeech(use_deepspeed=True, kv_cache=True, half=True)

AUDIO_FOLDER = "temporary_audio_files"
if not os.path.exists(AUDIO_FOLDER):
    os.mkdir(AUDIO_FOLDER)

# Helper function to convert text to wav file and return filepath
async def text_to_wav(text, voice='lain', preset='fast'):
    voice_samples, conditioning_latents = load_voice(voice)
    gen_audio = tts.tts_with_preset(text, voice_samples=voice_samples, conditioning_latents=conditioning_latents, preset=preset)
    filename = f"{uuid.uuid4()}.wav"
    filepath = os.path.join(AUDIO_FOLDER, filename)
    torchaudio.save(filepath, gen_audio.squeeze(0).cpu(), 24000)
    return filepath

@app.post("/text_to_speech")
async def tts_endpoint(text: str = Form(...)):
    audio_filepath = await text_to_wav(text)
    return {"audio_file": audio_filepath.split("/")[-1]}

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    return FileResponse(os.path.join(AUDIO_FOLDER, filename))

# Cleanup function that deletes files older than 1 hour
def cleanup_old_audio_files():
    now = time.time()
    for file in os.listdir(AUDIO_FOLDER):
        file_path = os.path.join(AUDIO_FOLDER, file)
        if os.path.getctime(file_path) < now - 1 * 3600:
            try:
                os.remove(file_path)
            except:
                pass

# Schedule the cleanup function to run every hour
scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_old_audio_files, trigger="interval", seconds=3600)
scheduler.start()

# WebSocket endpoint (example)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        audio_filepath = await text_to_wav(data)
        await websocket.send_text(audio_filepath.split("/")[-1])

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, port=5002, log_level="debug")
