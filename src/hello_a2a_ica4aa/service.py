from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import BaseModel

# 1) Import the production FastAPI app from universal-a2a-agent
#    We extend it with ICA4AA-friendly endpoints.
from a2a_universal.server import app as _universal_app
from a2a_universal.client import A2AClient

# Re-export as our app
app = _universal_app


# ----------------------------
# Models for the custom action
# ----------------------------
class SayHelloIn(BaseModel):
    name: Optional[str] = None


class SayHelloOut(BaseModel):
    message: str


# ----------------------------
# Convenience: health alias
# ----------------------------
@app.get("/health", include_in_schema=False)
async def health_alias() -> Dict[str, str]:
    # universal-a2a-agent already exposes /healthz
    return {"status": "ok"}


# ----------------------------
# ICA4AA: Agent Manifest
# ----------------------------
@app.get("/a2a/manifest")
async def get_manifest(request: Request) -> Dict[str, Any]:
    """Single-agent manifest so Builder Studio can discover from base URL."""
    base = (os.getenv("PUBLIC_URL") or str(request.base_url)).rstrip("/")

    SAY_HELLO_INPUT = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Name to greet"}},
        "required": [],
        "additionalProperties": False,
    }
    SAY_HELLO_OUTPUT = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    return {
        "api_version": "a2a/v1",
        "kind": "Agent",
        "name": os.getenv("HELLO_AGENT_NAME", "hello-world-a2a"),
        "version": os.getenv("HELLO_AGENT_VERSION", "0.1.0"),
        "description": "A minimal A2A-compatible Hello World agent built on universal-a2a-agent.",
        # Helpful links (universal-a2a-agent already exposes these)
        "health": "/healthz",
        "openapi": "/openapi.json",
        # Single demo action
        "actions": [
            {
                "name": "say_hello",
                "description": "Return a friendly greeting using the Universal A2A backend.",
                "method": "POST",
                "path": "/a2a/actions/say_hello",
                "input_schema": SAY_HELLO_INPUT,
                "output_schema": SAY_HELLO_OUTPUT,
            }
        ],
        "endpoint_base_url": base,
        "agent_card": f"{base}/.well-known/agent-card.json",
    }


# ----------------------------
# ICA4AA: Directory endpoint
# ----------------------------
@app.get("/a2a/agents")
async def list_agents(request: Request) -> Dict[str, Any]:
    """Directory endpoint for 'Get Agents from A2A Server'."""
    base = (os.getenv("PUBLIC_URL") or str(request.base_url)).rstrip("/")
    return {
        "agents": [
            {
                "name": os.getenv("HELLO_AGENT_NAME", "hello-world-a2a"),
                "version": os.getenv("HELLO_AGENT_VERSION", "0.1.0"),
                "manifest_url": f"{base}/a2a/manifest",
                "endpoint_base_url": base,
            }
        ]
    }


# ----------------------------
# ICA4AA: Action - say_hello
# ----------------------------
@app.post("/a2a/actions/say_hello", response_model=SayHelloOut)
async def say_hello(payload: SayHelloIn, request: Request) -> SayHelloOut:
    """Demo action that *uses* the Universal A2A backend for the reply."""
    name = (payload.name or "World").strip() or "World"

    # Where is the universal A2A backend? Default to this same service.
    base = (os.getenv("A2A_BACKEND_BASE") or os.getenv("PUBLIC_URL") or str(request.base_url)).rstrip("/")
    client = A2AClient(base_url=base)

    # Delegate to the universal A2A /a2a route => you get whichever provider/framework you configured
    prompt = f"Say hello to {name}."
    try:
        reply = client.send(prompt, use_jsonrpc=False)
    except Exception:
        reply = f"Hello, {name}!"

    return SayHelloOut(message=reply)
