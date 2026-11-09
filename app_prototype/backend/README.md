# Hardware Copilot · Python Backend & Desktop Runner

This directory contains the Python backend and desktop wrapper for the Hardware Copilot UI.

## Architecture

- **`app.py`**: FastAPI server handling:
  - `/api/chat`: Token-by-token streaming inference via local Ollama (`qwen2.5-coder:32b`, `deepseek-coder-v2`, etc.).
  - `/api/index-svd`: CMSIS-SVD 1.3 XML parser extracting peripheral registers, bit offsets, and masks.
  - `/api/registers/calculate`: Bitfield calculator mapping logical register flags to 32-bit hex values.
  - `/api/health`: Bridge status and model heartbeat.
- **`desktop_main.py`**: PyWebView native desktop window runner that starts the FastAPI server in a background thread and presents the UI in a native macOS/Windows/Linux window.
- **`requirements.txt`**: Python dependencies.

## Quickstart

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. (Optional) Run Ollama locally with the desired model:
   ```bash
   ollama run qwen2.5-coder:32b
   ```

3. Launch the desktop application:
   ```bash
   python desktop_main.py
   ```
