#!/bin/bash

# Navigate to the directory where the server is located
cd /root/llama.cpp

# Execute the server command with the specified model and port
./llama-server -m models/Mistral-Pygmalion-7B-GGUF/mistral-pygmalion-7b.Q4_K_M.gguf --port 5002 -ngl 50
