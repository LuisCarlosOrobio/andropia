# Importing necessary libraries and modules
import os  # For interacting with the operating system
import websockets  # For WebSocket communication
import uuid  # For generating unique identifiers
import json  # For handling JSON data
import asyncio  # For asynchronous programming
import time  # For working with time-related functions
from fastapi import FastAPI, WebSocket, HTTPException  # FastAPI framework for building web applications
from fastapi.staticfiles import StaticFiles  # For serving static files
from fastapi.responses import FileResponse  # For sending file responses

# Create an instance of the FastAPI application
app = FastAPI()

# Define a folder to store temporary audio files
AUDIO_FOLDER = "temporary_audio_files"

# Check if the audio folder exists, if not, create it
if not os.path.exists(AUDIO_FOLDER):
    os.makedirs(AUDIO_FOLDER)

# Dictionary to keep track of active WebSocket connections
active_websockets = {}

# Define a WebSocket endpoint
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    # Accept the WebSocket connection
    await websocket.accept()
    # Store the WebSocket connection in the dictionary
    active_websockets[client_id] = websocket
    try:
        while True:
            # Receive JSON data from the client
            data = await websocket.receive_json()
            # Process the JSON data and generate an audio file
            audio_file = await process_json_and_generate_audio(data)
            # Send the audio file to the client
            await send_audio_file(active_websockets[client_id], audio_file)
    except Exception as e:
        # Print any errors that occur
        print(f"Error: {e}")
    finally:
        # Remove the WebSocket connection from the dictionary when done
        del active_websockets[client_id]

# Asynchronous function to process JSON data and generate an audio file
async def process_json_and_generate_audio(data):
    # Extract the text content from the received JSON data
    text_to_speak = data.get("text", "")

    # Prepare the JSON input for piper, containing only the text to be synthesized
    piper_input = json.dumps({"text": text_to_speak})

    # Specify the model and output file
    model = "/root/piper-voices/en/en_US/lessac/medium/en_US-lessac-medium.onnx"  # or dynamically determined
    output_file = os.path.join(AUDIO_FOLDER, f"{uuid.uuid4()}.wav")

    # Prepare the piper command
    piper_command = [
        "piper",
        "--model", model,
        "--output_file", output_file,
        "--json-input"  # Since we are providing JSON input
    ]

    # Create an asynchronous subprocess to execute the piper command
    process = await asyncio.create_subprocess_exec(
        *piper_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE
    )

    # Write the modified JSON input to piper's stdin
    process.stdin.write(piper_input.encode())
    await process.stdin.drain()
    process.stdin.close()
    await process.wait()

    # Check if the output file was created successfully
    if not os.path.exists(output_file):
        print(f"File not found: {output_file}")
    else:
        print(f"File successfully created: {output_file}")

    # Return the path to the generated audio file
    return output_file

# Asynchronous function to send an audio file via WebSocket
async def send_audio_file(websocket: WebSocket, file_path):
    # Open the audio file and read its contents
    with open(file_path, 'rb') as f:
        audio_data = f.read()
    # Send the audio file data over the WebSocket connection
    await websocket.send_bytes(audio_data)

# Define an HTTP endpoint to serve audio files
@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    # Determine the file path of the requested audio file
    file_path = os.path.join(AUDIO_FOLDER, filename)
    # Check if the file exists, if not, raise a 404 error
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    # Return the audio file as a response
    return FileResponse(file_path)

# Define the root HTTP endpoint to serve the index.html file
@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

# Asynchronous function to clean up old audio files
async def cleanup_old_audio_files():
    # Get the current time
    now = time.time()
    # Iterate through the files in the audio folder
    for file in os.listdir(AUDIO_FOLDER):
        file_path = os.path.join(AUDIO_FOLDER, file)
        # Check if the file is older than 1 hour
        if os.stat(file_path).st_mtime < now - 3600:  # 1 hour
            try:
                # Remove the old file
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")

# Define a startup event handler to start the periodic cleanup task
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(run_periodic_cleanup())

# Define a shutdown event handler (no specific logic required here)
@app.on_event("shutdown")
async def on_shutdown():
    pass  # No specific shutdown logic required

# Asynchronous function to periodically run the cleanup task
async def run_periodic_cleanup():
    while True:
        await asyncio.sleep(3600)  # Wait for 1 hour
        await cleanup_old_audio_files()

# Entry point to run the FastAPI application using Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)  # internal service: loopback only
