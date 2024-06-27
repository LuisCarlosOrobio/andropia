import os
import asyncio
from fastapi import FastAPI, WebSocket
import websockets
import tempfile
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

app = FastAPI()

model_id = "distil-whisper/distil-large-v2"

model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id,
    torch_dtype=torch_dtype,
    low_cpu_mem_usage=True,
    use_safetensors=True
).to(device)

processor = AutoProcessor.from_pretrained(model_id)

pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    max_new_tokens=128,
    torch_dtype=torch_dtype,
    device=device
)

async def transcribe_audio(file_path):
    try:
        inputs = processor(file_path, return_tensors="pt", sampling_rate=16000)
        inputs = inputs.to(device)
        with torch.no_grad():
            generated_ids = model.generate(inputs.input_features, max_length=128, num_beams=5)
        transcription = processor.batch_decode(generated_ids, skip_special_tokens=True)
        return transcription[0]
    except Exception as e:
        return str(e)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            audio_data = await websocket.receive_bytes()
            with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as tmpfile:
                tmpfile.write(audio_data)
                tmpfile.flush()
                transcribed_text = await transcribe_audio(tmpfile.name)
            await websocket.send_text(transcribed_text)
    except asyncio.exceptions.CancelledError:
        print("WebSocket connection was cancelled.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
