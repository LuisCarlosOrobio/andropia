import json
import requests
import chromadb
import uuid
from datetime import datetime

# Function to send text for processing to a specified URL
def send_text_for_processing(text, url):
    # Prepare the data payload as JSON with all specified parameters
    data = {
        "prompt": text,
        "n_predict": 30,
        "sampling": {
            "repeat_last_n": 64,
            "repeat_penalty": 1.1,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "top_k": 40,
            "tfs_z": 1.0,
            "top_p": 0.95,
            "typical_p": 1.0,
            "temperature": 0.7,
            "mirostat": 0,
            "mirostat_lr": 0.1,
            "mirostat_ent": 5.0,
            "stream": True
        }
    }
    headers = {'Content-Type': 'application/json'}

    # Send the request to the specified URL
    response = requests.post(url, headers=headers, json=data)

    # Return the response from the server
    return response.json()

def send_text_for_embedding(text, url):
    # Prepare the data payload as JSON with the specified parameters
    data = {"content": text}
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# URL of the text processing service
text_processing_service_url = "http://127.0.0.1:5002/completion"
embedding_service_url = "http://127.0.0.1:5002/embedding"

chroma_client = chromadb.Client()
collection = chroma_client.get_or_create_collection("llm_memory")
prompt_text = "Are you doing alright?"

processing_result = send_text_for_processing(prompt_text, text_processing_service_url)
current_timestamp = datetime.now().isoformat()
embedding_result = send_text_for_embedding(prompt_text, embedding_service_url)

print("Attempting to save embedding to ChromaDB...")

print("Attempting to save embedding to ChromaDB...")

try:
    # Extract the embedding list from the result
    embedding_list = embedding_result.get('embedding', [])
    print("Embedding List:", embedding_list)

    # Ensure embedding_list is a list of numbers
    if isinstance(embedding_list, list) and all(isinstance(x, (int, float)) for x in embedding_list):
        # Create a nested list for the embedding to match the expected format of ChromaDB
        nested_embedding_list = [embedding_list]

        # Define basic metadata
        metadata = {
            "prompt": prompt_text,
            "timestamp": current_timestamp
        }

        # Add embedding to the collection
        collection.add(
            documents=[prompt_text],
            embeddings=nested_embedding_list,  # Nested list format for embedding
            metadatas=[metadata],  # Basic metadata including prompt and timestamp
            ids=[str(uuid.uuid4())]
        )
        print("Embedding successfully saved to ChromaDB.")
    else:
        print("Invalid format for embedding result.")
except Exception as e:
    print(f"An error occurred while saving to ChromaDB: {e}")
