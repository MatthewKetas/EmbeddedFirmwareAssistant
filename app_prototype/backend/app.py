"""Local web API for the firmware assistant."""

import json
import logging
import sys
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager, closing
from pathlib import Path
from threading import Lock
from typing import Literal

from defusedxml.common import DefusedXmlException
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from openai import OpenAIError
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from RAG import rag

MAX_BOARD_BYTES = 16 * 1024 * 1024
FRONTEND_ORIGINS = {
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (3000, 4173)
}
library_lock = Lock()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    with (
        rag.OpenAI(base_url=rag.BASE_URL, api_key=rag.API_KEY, timeout=180, max_retries=0) as client,
        closing(rag.QdrantClient(path=rag.QDRANT_PATH, force_disable_check_same_thread=True)) as library,
    ):
        rag.client, rag.qdrant = client, library
        try:
            yield
        finally:
            rag.client = rag.qdrant = None


app = FastAPI(title="Hardware Copilot", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])


@app.middleware("http")
async def local_writes_only(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin not in FRONTEND_ORIGINS:
        return JSONResponse({"detail": "Open the local frontend to use this API."}, status_code=403)
    return await call_next(request)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    board_id: str
    prompt: str
    history: list[ChatMessage] = Field(default_factory=list)


class RegisterCalcRequest(BaseModel):
    register: str
    fields: dict[str, int]


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "active_model": rag.CHAT_MODEL}


@app.get("/api/boards")
def list_boards():
    return rag.board_map.list_boards()


@app.post("/api/boards")
def upload_board(file: UploadFile):
    data = file.file.read(MAX_BOARD_BYTES + 1)
    if len(data) > MAX_BOARD_BYTES:
        raise HTTPException(413, "Board XML must be 16 MB or smaller.")
    try:
        return rag.board_map.import_board(data)
    except (ET.ParseError, DefusedXmlException, LookupError) as exc:
        raise HTTPException(422, "Choose a valid CMSIS-SVD XML file without a DTD.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    if not req.prompt.strip():
        raise HTTPException(422, "Enter a message.")
    if not any(board["id"] == req.board_id for board in rag.board_map.list_boards()):
        raise HTTPException(404, "This board is missing from the local board database.")

    def generate():
        try:
            history = [message.model_dump() for message in req.history]
            board_context = rag.board_map.context(req.board_id, req.prompt)
            with library_lock:
                hits = rag.retrieve(req.prompt, board_id=req.board_id)
            if any("file" in hit.payload for hit in hits):
                hits = rag.fit_code_context(req.prompt, hits, history, board_context)
            prompt = rag.build_rag_prompt(req.prompt, hits, board_context)
            with rag.open_chat_stream([*history, {"role": "user", "content": prompt}]) as stream:
                for chunk in stream:
                    if chunk.choices and (text := chunk.choices[0].delta.content):
                        yield json.dumps({"text": text}) + "\n"
            yield '{"done": true}\n'
        except (rag.httpx.HTTPError, OpenAIError, RuntimeError):
            logger.exception("Local chat failed")
            yield json.dumps({"error": "Local chat failed. Check that Lemonade is running with the configured models, then try again."}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


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
