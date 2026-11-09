"""
Hardware Copilot - Python Local & Desktop Backend
FastAPI server providing SVD parsing, Datasheet RAG, and Ollama streaming proxy.

Run directly with:
    pip install -r requirements.txt
    uvicorn app:app --host 127.0.0.1 --port 8000 --reload
"""

import os
import json
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests

app = FastAPI(
    title="Hardware Copilot Python API",
    description="SVD register map parser, datasheet RAG engine, and Ollama bridge",
    version="1.4.0"
)

# Allow local desktop frontend from Vite (port 3000) or PyWebView
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = "qwen2.5-coder:32b"

class ChatRequest(BaseModel):
    prompt: str
    mcu: Optional[str] = "STM32H743ZI"
    model: Optional[str] = DEFAULT_MODEL
    history: Optional[List[Dict[str, str]]] = []

class RegisterCalcRequest(BaseModel):
    register: str
    fields: Dict[str, int]

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "active_model": DEFAULT_MODEL,
        "ollama_host": OLLAMA_HOST,
        "version": "1.4.0"
    }

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Streams token-by-token from local Ollama or returns SVD-grounded answer"""
    system_prompt = (
        f"You are Hardware Copilot, an expert embedded firmware & silicon engineer for {req.mcu}. "
        "Always cite exact datasheet chapters, reference manual pages, register bitfield offsets, "
        "and provide copy-paste ready CMSIS C code with bitmask definitions."
    )

    ollama_payload = {
        "model": req.model or DEFAULT_MODEL,
        "system": system_prompt,
        "prompt": req.prompt,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_ctx": 32768
        }
    }

    try:
        def generate():
            with requests.post(f"{OLLAMA_HOST}/api/generate", json=ollama_payload, stream=True) as r:
                for line in r.iter_lines():
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        yield chunk.get("response", "")
        
        return StreamingResponse(generate(), media_type="text/plain")
    except Exception:
        # Fallback if Ollama isn't currently booted
        return {
            "content": f"[Python Backend] Connected to Python bridge for {req.mcu}. Processed prompt: '{req.prompt}'. Ensure Ollama is running at {OLLAMA_HOST} for live LLM inference."
        }

@app.post("/api/index-svd")
async def parse_svd_file(file: UploadFile = File(...)):
    """Parses CMSIS-SVD XML files into structured register maps & bitfields"""
    content = await file.read()
    root = ET.fromstring(content)
    peripherals = []
    
    for periph_elem in root.findall(".//peripheral"):
        name = periph_elem.findtext("name", "")
        base_addr = periph_elem.findtext("baseAddress", "0x00000000")
        desc = periph_elem.findtext("description", "")
        registers = []
        
        for reg_elem in periph_elem.findall(".//register"):
            r_name = reg_elem.findtext("name", "")
            r_offset = reg_elem.findtext("addressOffset", "0x0")
            r_reset = reg_elem.findtext("resetValue", "0x0")
            fields = []
            
            for field_elem in reg_elem.findall(".//field"):
                f_name = field_elem.findtext("name", "")
                f_offset = int(field_elem.findtext("bitOffset", "0"))
                f_width = int(field_elem.findtext("bitWidth", "1"))
                fields.append({
                    "name": f_name,
                    "bitStart": f_offset,
                    "bitEnd": f_offset + f_width - 1,
                    "access": field_elem.findtext("access", "RW"),
                    "description": field_elem.findtext("description", "")
                })
            
            registers.append({
                "name": r_name,
                "offset": r_offset,
                "resetValue": r_reset,
                "fields": fields
            })
            
        peripherals.append({
            "name": name,
            "baseAddress": base_addr,
            "description": desc,
            "registers": registers
        })
        
    return {"peripherals": peripherals, "count": len(peripherals)}

@app.post("/api/registers/calculate")
def calculate_register(req: RegisterCalcRequest):
    """Calculates composite 32-bit register value from named bitfields"""
    total_value = 0
    breakdown = {}
    for name, val in req.fields.items():
        total_value |= val
        breakdown[name] = f"0x{val:08X}"
    return {
        "register": req.register,
        "hex_value": f"0x{total_value:08X}",
        "decimal_value": total_value,
        "binary_string": f"{total_value:032b}",
        "breakdown": breakdown
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
