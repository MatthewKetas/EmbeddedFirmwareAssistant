"""
Hardware Copilot - Native Desktop Runner (PyWebView + FastAPI)
Launches the full embedded engineering copilot as a native desktop application
without the weight of Electron.

Usage:
    python desktop_main.py
"""

import sys
import threading
import time
import webview
import uvicorn
from app import app

def start_backend():
    """Runs the FastAPI backend in a daemon thread on port 8000"""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

if __name__ == "__main__":
    print("[*] Booting Hardware Copilot local Python backend...")
    t = threading.Thread(target=start_backend, daemon=True)
    t.start()
    time.sleep(1.0) # Wait for port binding

    print("[*] Launching Hardware Copilot Desktop Window...")
    # Point to the Vite development server (port 3000) or built dist/index.html
    window = webview.create_window(
        title="Hardware Copilot · Datasheet & SVD Studio",
        url="http://localhost:3000",
        width=1440,
        height=920,
        resizable=True,
        fullscreen=False,
        background_color="#0b0f14",
        min_size=(1024, 700)
    )

    webview.start(debug=False)
