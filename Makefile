# Define the names of the Python environments
ENV_NAMES = whisper tts main

# Define tmux session name
TMUX_SESSION = mysession

# Define virtual environment directory
VENV_DIR = venv

# Define requirements files for each environment
WHISPER_REQS = whisper/requirements.txt
TTS_REQS = tts/requirements.txt
MAIN_REQS = main/requirements.txt

# CMake repository URL and directory
CMAKE_REPO_URL = https://github.com/Kitware/CMake.git
CMAKE_DIR = CMake
PIPER_REPO_URL = https://github.com/rhasspy/piper.git
PIPER_DIR = piper
PIPER_PHONEMIZE_URL = https://github.com/rhasspy/piper-phonemize/releases/download/v1.0.0/libpiper_phonemize-amd64.tar.gz
PIPER_PHONEMIZE_TAR = libpiper_phonemize-amd64.tar.gz
PIPER_PHONEMIZE_DIR = lib/Linux-x86_64/piper_phonemize
PIPER_VOICES_REPO_URL = https://huggingface.co/rhasspy/piper-voices
LLAMA_CPP_REPO_URL = https://github.com/ggerganov/llama.cpp.git
MISTRAL_PYGMALION_REPO_URL = https://huggingface.co/TheBloke/Mistral-Pygmalion-7B-GGUF

# Default target
all: install_system_deps install_cmake setup_llama_cpp create_requirements setup_tmux setup_environments verify_node

# Install system dependencies
install_system_deps:
	sudo apt-get update
	sudo apt-get install -y ffmpeg build-essential libssl-dev espeak-ng curl git-lfs
	curl -fsSL https://deb.nodesource.com/setup_22.x -o nodesource_setup.sh
	sudo -E bash nodesource_setup.sh
	sudo apt-get install -y nodejs
	npm install -g parcel-bundler
	git lfs install
	git clone $(PIPER_VOICES_REPO_URL)

# Clone and install CMake
install_cmake:
	git clone $(CMAKE_REPO_URL)
	cd $(CMAKE_DIR) && ./bootstrap && make && sudo make install

# Set up llama.cpp and Mistral-Pygmalion-7B-GGUF
setup_llama_cpp:
	git clone $(LLAMA_CPP_REPO_URL)
	cd llama.cpp/models && git lfs install
	git clone $(MISTRAL_PYGMALION_REPO_URL)
	cd .. && make GGML_CUDA=1

# Create requirements.txt files
create_requirements:
	echo "transformers\naccelerate\ndatasets[audio]\nfastapi\nwebsockets" > $(WHISPER_REQS)
	echo "websockets\nuuid\njson\nfastapi\nfastapi[staticfiles]\nfastapi[responses]\nonruntime" > $(TTS_REQS)
	echo "fastapi\nwebsockets\nhttpx\njson\nbase64\nuuid\nre\nshutil\nsubprocess" > $(MAIN_REQS)

# Set up tmux session and windows
setup_tmux:
	tmux new-session -d -s $(TMUX_SESSION) -n whisper
	tmux new-window -t $(TMUX_SESSION):1 -n tts
	tmux new-window -t $(TMUX_SESSION):2 -n main

# Create virtual environments and install dependencies for each environment
setup_environments: setup_whisper setup_tts setup_main

setup_whisper:
	tmux send-keys -t $(TMUX_SESSION):0 'python3 -m venv $(VENV_DIR)/whisper && source $(VENV_DIR)/whisper/bin/activate && pip install --upgrade pip && pip install -r $(WHISPER_REQS)' C-m

setup_tts:
	tmux send-keys -t $(TMUX_SESSION):1 'python3 -m venv $(VENV_DIR)/tts && source $(VENV_DIR)/tts/bin/activate && pip install --upgrade pip && pip install -r $(TTS_REQS) && export ESPEAK_DATA_PATH=/usr/lib/x86_64-linux-gnu/espeak-ng-data && cd $(PIPER_DIR) && git clone $(PIPER_REPO_URL) && cd $(PIPER_DIR) && curl -L $(PIPER_PHONEMIZE_URL) -o $(PIPER_PHONEMIZE_TAR) && mkdir -p $(PIPER_PHONEMIZE_DIR) && tar -xvzf $(PIPER_PHONEMIZE_TAR) -C $(PIPER_PHONEMIZE_DIR) && sudo ln -s $$PWD/$(PIPER_DIR)/install/piper /usr/local/bin/piper && pip install -r requirements.txt && python setup.py install' C-m

setup_main:
	tmux send-keys -t $(TMUX_SESSION):2 'python3 -m venv $(VENV_DIR)/main && source $(VENV_DIR)/main/bin/activate && pip install --upgrade pip && pip install -r $(MAIN_REQS) && cd /root/maip3/static && parcel build dist/src/index.js -d dist && cd ..' C-m

# Verify Node.js installation
verify_node:
	node -v

.PHONY: all install_system_deps install_cmake setup_llama_cpp create_requirements setup_tmux setup_environments setup_whisper setup_tts setup_main verify_node
