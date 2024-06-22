# Importing necessary libraries and modules
import os  # For interacting with the operating system
import asyncio  # For asynchronous programming
from fastapi import FastAPI, WebSocket  # FastAPI framework for building web applications
import websockets  # For WebSocket communication
import tempfile  # For creating temporary files
import torch  # PyTorch library for deep learning
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline  # Transformers library for pre-trained models

# Determine the device to use for computation (GPU if available, otherwise CPU)
device = "cuda:0" if torch.cuda.is_available() else "cpu"

# Set the appropriate data type for the model (16-bit floats if using GPU, otherwise 32-bit floats)
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

# Create an instance of the FastAPI application
app = FastAPI()

# Define the model ID for the speech recognition model
model_id = "distil-whisper/distil-large-v2"

# Load the pre-trained speech-to-sequence model with specified parameters
model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id,
    torch_dtype=torch_dtype,  # Use the determined data type
    low_cpu_mem_usage=True,  # Optimize for lower CPU memory usage
    use_safetensors=True  # Use safe tensors for model weights
).to(device)  # Move the model to the appropriate device

# Load the processor associated with the model
processor = AutoProcessor.from_pretrained(model_id)

# Create a pipeline for automatic speech recognition
pipe = pipeline(
    "automatic-speech-recognition",  # Specify the task type
    model=model,  # Use the loaded model
    tokenizer=processor.tokenizer,  # Use the tokenizer from the processor
    feature_extractor=processor.feature_extractor,  # Use the feature extractor from the processor
    max_new_tokens=128,  # Set the maximum number of new tokens to generate
    torch_dtype=torch_dtype,  # Use the determined data type
    device=device  # Use the determined device
)

# Asynchronous function to transcribe audio from a file
async def transcribe_audio(file_path):
    try:
        # Use the pipeline to transcribe the audio file
        result = pipe(file_path)
        # Return the transcribed text
        return result['text']
    except Exception as e:
        # Return the error message if an exception occurs
        return str(e)

# Define a WebSocket endpoint for real-time communication
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Accept the WebSocket connection
    await websocket.accept()
    try:
        while True:
            # Receive audio data from the WebSocket connection
            audio_data = await websocket.receive_bytes()
            # Create a temporary file to store the received audio data
            with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as tmpfile:
                tmpfile.write(audio_data)  # Write the audio data to the file
                tmpfile.flush()  # Ensure all data is written to the file
                # Transcribe the audio data using the transcribe_audio function
                transcribed_text = await transcribe_audio(tmpfile.name)
            # Send the transcribed text back to the client via WebSocket
            await websocket.send_text(transcribed_text)
    
    # Handle WebSocket connection cancellation
    except asyncio.exceptions.CancelledError:
        print("WebSocket connection was cancelled.")
    # Handle any other exceptions that occur
    except Exception as e:
        print(f"An error occurred: {e}")

# Entry point to run the FastAPI application using Uvicorn
if __name__ == "__main__":
    import uvicorn
    # Run the FastAPI application on host 0.0.0.0 and port 5000
    uvicorn.run(app, host="0.0.0.0", port=5000)
