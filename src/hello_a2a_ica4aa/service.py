from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

# ======================================================================================
# App
# ======================================================================================

app = FastAPI(
    title="Universal A2A Agent",
    version=os.getenv("A2A_VERSION", "1.2.0"),
    description="Universal A2A Agent - HTTP surface for agent pipelines (+ ICA4AA compatibility).",
)

# Permissive CORS so ICA4AA UI and other tools can discover your server easily
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ======================================================================================
# Helpers
# ======================================================================================

def _request_id(req: Request) -> str:
    return req.headers.get("x-request-id") or str(uuid.uuid4())


def _with_common_headers(rid: str) -> Dict[str, str]:
    return {"x-request-id": rid, "cache-control": "no-store"}


def _public_base_url(request: Request) -> str:
    return (os.getenv("PUBLIC_URL") or str(request.base_url)).rstrip("/")


def _backend_base_url(request: Request) -> str:
    return (
        os.getenv("A2A_BACKEND_BASE")
        or os.getenv("PUBLIC_URL")
        or str(request.base_url)
    ).rstrip("/")


def _extract_user_text_from_a2a(params: Dict[str, Any]) -> str:
    """
    Pull the first text part from A2A-shaped params:
      params = {"message": {"parts": [{"text": "..."}, {"type":"text","text":"..."}]}}
    """
    msg = (params or {}).get("message") or {}
    for p in (msg.get("parts") or []):
        if not isinstance(p, dict):
            continue
        if isinstance(p.get("text"), str) and p.get("text"):
            return p["text"]
    return ""


def _extract_context_id(params: Dict[str, Any]) -> str:
    """Best-effort context id extraction, or create one if missing."""
    return (
        (params or {}).get("contextId")
        or ((params or {}).get("message") or {}).get("contextId")
        or f"ctx-{uuid.uuid4()}"
    )


def _make_a2a_text_message(text: str, context_id: str) -> Dict[str, Any]:
    """
    Build a compliant final *message* event for the Inspector.

    The Inspector expects an event with:
      - kind: "message"
      - role: "agent"
      - messageId: <string>
      - contextId: <string>
      - parts: [{ "text": "..." }]
    """
    return {
        "kind": "message",
        "messageId": f"msg-{uuid.uuid4()}",  # use messageId (not id)
        "contextId": context_id,
        "role": "agent",
        "parts": [{"text": text}],
    }


def _ok() -> Dict[str, str]:
    return {"status": "ok"}


# ======================================================================================
# Root + health
# ======================================================================================

@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/healthz")
async def healthz(req: Request) -> JSONResponse:
    rid = _request_id(req)
    return JSONResponse(_ok(), headers=_with_common_headers(rid))


@app.get("/health", include_in_schema=False)
async def health_alias(req: Request) -> JSONResponse:
    rid = _request_id(req)
    return JSONResponse(_ok(), headers=_with_common_headers(rid))


@app.get("/readyz")
async def readyz(req: Request) -> JSONResponse:
    rid = _request_id(req)
    return JSONResponse(_ok(), headers=_with_common_headers(rid))


# ======================================================================================
# A2A Inspector-friendly agent card (rich schema)
# ======================================================================================

@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
async def well_known_agent_card(req: Request) -> JSONResponse:
    rid = _request_id(req)
    base = _public_base_url(req)
    card = {
        "protocolVersion": os.getenv("PROTOCOL_VERSION", "0.3.0"),
        "preferredTransport": "JSONRPC",
        "name": os.getenv("A2A_AGENT_NAME", "Universal A2A Agent"),
        "version": os.getenv("A2A_AGENT_VERSION", "1.2.0"),
        "description": "Universal A2A HTTP entry point.",
        "url": f"{base}/rpc",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "chat",
                "name": "chat",
                "description": "Basic chat response",
                "tags": ["chat", "greeting"],
            }
        ],
        "endpoints": {
            "a2a": f"{base}/a2a",
            "jsonrpc": f"{base}/rpc",
            "openai": f"{base}/openai/v1/chat/completions",
            "health": f"{base}/healthz",
        },
    }
    return JSONResponse(card, headers=_with_common_headers(rid))


# ======================================================================================
# A2A: message/send (canonical, non-JSON-RPC)
# ======================================================================================

@app.post("/a2a")
async def a2a_endpoint(req: Request) -> JSONResponse:
    rid = _request_id(req)
    body = await req.json()
    method = body.get("method")
    params = body.get("params") or {}

    if method != "message/send":
        return JSONResponse(
            {"error": {"code": -32601, "message": f"Unsupported method: {method}"}},
            status_code=400,
            headers=_with_common_headers(rid),
        )

    user_text = _extract_user_text_from_a2a(params).strip()
    if not user_text:
        return JSONResponse(
            {"error": {"code": -32602, "message": "No text found in message parts."}},
            status_code=400,
            headers=_with_common_headers(rid),
        )

    context_id = _extract_context_id(params)
    reply = os.getenv("A2A_ECHO_PREFIX", "") + user_text

    # FIXED: The result should be the message object directly.
    result = _make_a2a_text_message(reply, context_id)
    return JSONResponse({"result": result}, headers=_with_common_headers(rid))


# ======================================================================================
# JSON-RPC 2.0 mirror (what the Inspector calls)
# ======================================================================================

@app.post("/rpc")
async def jsonrpc(req: Request) -> JSONResponse:
    rid = _request_id(req)
    body = await req.json()

    if body.get("jsonrpc") != "2.0":
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": body.get("id")},
            status_code=400,
            headers=_with_common_headers(rid),
        )

    method = body.get("method")
    params = (body.get("params") or {})
    if method != "message/send":
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unsupported method: {method}"}, "id": body.get("id")},
            status_code=400,
            headers=_with_common_headers(rid),
        )

    user_text = _extract_user_text_from_a2a(params).strip()
    if not user_text:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32602, "message": "No text found in message parts."}, "id": body.get("id")},
            status_code=400,
            headers=_with_common_headers(rid),
        )

    context_id = _extract_context_id(params)
    reply = os.getenv("A2A_ECHO_PREFIX", "You said: ") + user_text

    # FIXED: The result should be the message object directly, not a container.
    result = _make_a2a_text_message(reply, context_id)
    return JSONResponse(
        {"jsonrpc": "2.0", "result": result, "id": body.get("id")},
        headers=_with_common_headers(rid)
    )


# ======================================================================================
# OpenAI-compatible passthrough (minimal)
# ======================================================================================

@app.post("/openai/v1/chat/completions")
async def openai_chat_completions(req: Request) -> JSONResponse:
    rid = _request_id(req)
    body = await req.json()
    messages = body.get("messages") or []
    user_text = ""
    for m in reversed(messages):
        if (m or {}).get("role") == "user":
            user_text = (m.get("content") or "").strip()
            if user_text:
                break
    if not user_text:
        return JSONResponse(
            {"error": {"message": "No user message found."}},
            status_code=400,
            headers=_with_common_headers(rid),
        )

    reply = os.getenv("A2A_ECHO_PREFIX", "") + user_text
    now = int(time.time())
    resp = {
        "id": f"cmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": now,
        "model": body.get("model", "dummy-a2a"),
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": reply}}
        ],
        "usage": {"prompt_tokens": len(user_text.split()), "completion_tokens": len(reply.split()), "total_tokens": 0},
    }
    return JSONResponse(resp, headers=_with_common_headers(rid))


# ======================================================================================
# -----------------------  ICA4AA compatibility extensions  ---------------------------
# ======================================================================================

HELLO_AGENT_ID = os.getenv("HELLO_AGENT_ID", "hello-world")
HELLO_AGENT_NAME = os.getenv("HELLO_AGENT_NAME", "Hello World")
HELLO_AGENT_VERSION = os.getenv("HELLO_AGENT_VERSION", "1.2.0")
HELLO_AGENT_DESC = os.getenv("HELLO_AGENT_DESC", "Universal A2A Hello")
HELLO_AGENT_TAGS = [t for t in (os.getenv("HELLO_AGENT_TAGS", "demo,tutorial").split(",")) if t]

SAY_HELLO_INPUT = {
    "type": "object",
    "properties": {"name": {"type": "string", "description": "Name to greet"}},
    "required": ["name"],
    "additionalProperties": False,
}
SAY_HELLO_OUTPUT = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}


def _invoke_via_local_a2a(base_url: str, prompt_text: str, timeout: float = 20.0) -> str:
    """
    Reuse our /a2a pipeline; tolerate all server shapes we might return.
    """
    payload = {
        "method": "message/send",
        "params": {"message": {"role": "user", "messageId": "ica4aa", "parts": [{"text": prompt_text}]}}
    }
    r = httpx.post(f"{base_url}/a2a", json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()

    # unwrap {"result": ...} if present
    data = data.get("result", data)

    # NOTE: The original _invoke_via_local_a2a expected a nested message.
    # Since we fixed the /a2a endpoint, this function can be simplified.
    # The 'result' is now the message object itself.
    if isinstance(data, dict):
        for p in (data.get("parts") or []):
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                return p["text"]

    return ""


@app.get("/a2a/manifest", tags=["ica4aa"], summary="Agent Manifest")
async def get_manifest(request: Request) -> JSONResponse:
    rid = _request_id(request)
    base = _public_base_url(request)
    manifest = {
        "apiVersion": "a2a/v1",
        "kind": "Agent",
        "metadata": {
            "id": HELLO_AGENT_ID,
            "name": HELLO_AGENT_NAME,
            "version": HELLO_AGENT_VERSION,
            "description": HELLO_AGENT_DESC,
            "tags": HELLO_AGENT_TAGS,
        },
        "spec": {
            "endpoints": {
                "invoke": f"{base}/api/v1/agents/{HELLO_AGENT_ID}/invoke",
                "health": f"{base}/healthz",
            },
            "auth": {"type": "none"},
            "inputSchema": SAY_HELLO_INPUT,
            "outputSchema": SAY_HELLO_OUTPUT,
            "endpointBaseUrl": base,
            "openapi": "/openapi.json",
            "actions": [
                {
                    "name": "say_hello",
                    "description": "Return a friendly greeting via the Universal A2A backend.",
                    "method": "POST",
                    "path": "/a2a/actions/say_hello",
                    "input": SAY_HELLO_INPUT,
                    "output": SAY_HELLO_OUTPUT,
                }
            ],
        },
    }
    return JSONResponse(manifest, headers=_with_common_headers(rid))


@app.get("/a2a/agents", tags=["ica4aa"], summary="Agents Directory")
async def list_agents(request: Request) -> JSONResponse:
    rid = _request_id(request)
    base = _public_base_url(request)
    listing = {
        "agents": [
            {
                "id": HELLO_AGENT_ID,
                "name": HELLO_AGENT_NAME,
                "version": HELLO_AGENT_VERSION,
                "description": HELLO_AGENT_DESC,
                "tags": HELLO_AGENT_TAGS,
                "endpoints": {
                    "invoke": f"{base}/api/v1/agents/{HELLO_AGENT_ID}/invoke",
                    "health": f"{base}/healthz",
                },
                "auth": {"type": "none"},
                "input_schema": SAY_HELLO_INPUT,
                "output_schema": SAY_HELLO_OUTPUT,
                "manifestUrl": f"{base}/a2a/manifest",
                "endpointBaseUrl": base,
            }
        ]
    }
    return JSONResponse(listing, headers=_with_common_headers(rid))


@app.get("/.well-known/ica4aa/agents", tags=["ica4aa"], summary="Agents Directory (well-known)")
@app.get("/api/v1/agents", tags=["ica4aa"], summary="Agents Directory (compat)")
async def well_known_agents(request: Request) -> JSONResponse:
    rid = _request_id(request)
    base = _public_base_url(request)
    payload = {
        "version": "1.0",
        "agents": [
            {
                "id": HELLO_AGENT_ID,
                "name": HELLO_AGENT_NAME,
                "version": HELLO_AGENT_VERSION,
                "description": HELLO_AGENT_DESC,
                "tags": HELLO_AGENT_TAGS,
                "endpoints": {
                    "invoke": f"{base}/api/v1/agents/{HELLO_AGENT_ID}/invoke",
                    "health": f"{base}/healthz",
                },
                "auth": {"type": "none"},
                "input_schema": SAY_HELLO_INPUT,
                "output_schema": SAY_HELLO_OUTPUT,
            }
        ],
    }
    return JSONResponse(payload, headers=_with_common_headers(rid))


class SayHelloIn(BaseModel):
    name: Optional[str] = None


class SayHelloOut(BaseModel):
    message: str


@app.post("/a2a/actions/say_hello", response_model=SayHelloOut, tags=["ica4aa"], summary="Say Hello")
async def say_hello(payload: SayHelloIn, request: Request) -> JSONResponse:
    rid = _request_id(request)
    name = (payload.name or "World").strip() or "World"
    prompt = f"Say hello to {name}."
    try:
        reply = _invoke_via_local_a2a(_backend_base_url(request), prompt)
    except Exception:
        reply = f"Hello, {name}!"
    return JSONResponse(SayHelloOut(message=reply).model_dump(), headers=_with_common_headers(rid))


@app.post("/api/v1/agents/{agent_id}/invoke", response_model=SayHelloOut, tags=["ica4aa"], summary="Invoke Agent")
async def invoke_agent(agent_id: str, payload: SayHelloIn, request: Request) -> JSONResponse:
    rid = _request_id(request)
    name = (payload.name or "World").strip() or "World"
    prompt = f"Say hello to {name}."
    try:
        reply = _invoke_via_local_a2a(_backend_base_url(request), prompt)
    except Exception:
        reply = f"Hello, {name}!"
    return JSONResponse(SayHelloOut(message=reply).model_dump(), headers=_with_common_headers(rid))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "__main__:app", # Changed for direct execution
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=True,
    )