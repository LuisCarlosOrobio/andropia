from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI()

# Get the absolute path to the 'static/dist' directory
dist_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), "static/dist"))

# Serve the 'dist' directory
app.mount("/dist", StaticFiles(directory=dist_directory), name="dist")

@app.get("/")
async def read_root():
    return FileResponse('static/dist/index.html')

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")

# Add a print statement to check if this route is hit
@app.get("/dist/{file_path:path}")
async def serve_static_file(file_path: str):
    print("Serving file:", file_path)
    return FileResponse(dist_directory + "/" + file_path)

