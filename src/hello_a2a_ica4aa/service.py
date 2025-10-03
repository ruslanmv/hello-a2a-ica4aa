# src/hello_a2a_ica4aa/service.py
from __future__ import annotations

"""
Hello World A2A (ICA4AA-ready) service.

This module REUSES the production FastAPI app from `universal-a2a-agent`
and EXTENDS it with:
  - GET /a2a/manifest            (single-agent manifest; camelCase; apiVersion/kind/metadata/spec)
  - GET /a2a/agents              (directory endpoint; camelCase)
  - GET /.well-known/ica4aa/agents (well-known discovery)
  - GET /api/v1/agents           (compat discovery)
  - POST /api/v1/agents/{id}/invoke (invoke wrapper)
  - POST /a2a/actions/say_hello  (demo action)
  - GET /health                  (alias for /healthz)

Why this design?
- You keep the stable, well-tested Universal A2A HTTP surface
  (/a2a, /rpc, /openai/v1/chat/completions, /.well-known/agent-card.json, /healthz, /readyz).
- You add the ICA4AA discovery routes so Builder Studio can “Upload YAML”, “Get Agents from A2A Server”,
  or “Agent Endpoint URL” and auto-discover your agent.
- The demo action simply calls the local /a2a pipeline, so you can switch model providers
  and orchestration frameworks via environment variables (LLM_PROVIDER, AGENT_FRAMEWORK)
  without changing this code.
"""

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

# 1) Import the production FastAPI app from universal-a2a-agent.
#    We extend this app with ICA4AA-friendly endpoints.
from a2a_universal.server import app as _universal_app
from a2a_universal.client import A2AClient

# Re-export as our FastAPI app
app = _universal_app

# Enable permissive CORS for discovery/manifest endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------------------
# Models for the custom action
# --------------------------------------------------------------------------------------
class SayHelloIn(BaseModel):
    name: Optional[str] = None


class SayHelloOut(BaseModel):
    message: str


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _public_base_url(request: Request) -> str:
    """
    Compute the externally reachable base URL.

    Priority:
      1) PUBLIC_URL env var (recommended in containers/reverse proxies),
      2) request.base_url (FastAPI/ASGI-derived, respects Host/X-Forwarded-* if configured).

    Always returns without a trailing slash.
    """
    return (os.getenv("PUBLIC_URL") or str(request.base_url)).rstrip("/")


def _backend_base_url(request: Request) -> str:
    """
    Where to call the Universal A2A backend. Defaults to this same service,
    but can be pointed elsewhere if you run a separate A2A hub.

      A2A_BACKEND_BASE  -> overrides
      PUBLIC_URL        -> otherwise
      request.base_url  -> last resort

    Always returns without a trailing slash.
    """
    return (
        os.getenv("A2A_BACKEND_BASE")
        or os.getenv("PUBLIC_URL")
        or str(request.base_url)
    ).rstrip("/")


# --------------------------------------------------------------------------------------
# Convenience: health alias (many platforms probe /health)
# --------------------------------------------------------------------------------------
@app.get("/health", include_in_schema=False)
def health_alias() -> Dict[str, str]:
    # universal-a2a-agent already exposes /healthz; this is a friendly alias
    return {"status": "ok"}


# --------------------------------------------------------------------------------------
# ICA4AA: Agent Manifest (single-agent)
#   - IMPORTANT: Use camelCase and apiVersion/kind/metadata/spec structure.
#   - Matches the same shape as the agent.yaml used in “Upload Agent YAML”.
# --------------------------------------------------------------------------------------
@app.get("/a2a/manifest", tags=["ica4aa"], summary="Agent Manifest")
def get_manifest(request: Request) -> Dict[str, Any]:
    base = _public_base_url(request)
    agent_id = os.getenv("HELLO_AGENT_ID", "hello-world")
    name = os.getenv("HELLO_AGENT_NAME", "Hello World")
    version = os.getenv("HELLO_AGENT_VERSION", "1.2.0")

    # IO schemas
    say_hello_input = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Name to greet"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    say_hello_output = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    return {
        "apiVersion": "a2a/v1",
        "kind": "Agent",
        "metadata": {
            "id": agent_id,
            "name": name,
            "version": version,
            "description": "Universal A2A Hello",
        },
        "spec": {
            # New fields ICA4AA expects
            "endpoints": {
                "invoke": f"{base}/api/v1/agents/{agent_id}/invoke",
                "health": f"{base}/healthz",
            },
            "auth": {"type": "none"},
            "inputSchema": say_hello_input,   # camelCase for manifest
            "outputSchema": say_hello_output,

            # Back-compat fields retained
            "endpointBaseUrl": base,
            "openapi": "/openapi.json",
            "actions": [
                {
                    "name": "say_hello",
                    "description": "Return a friendly greeting using the Universal A2A backend.",
                    "method": "POST",
                    "path": "/a2a/actions/say_hello",
                    "input": say_hello_input,
                    "output": say_hello_output,
                }
            ],
        },
    }


# --------------------------------------------------------------------------------------
# ICA4AA: Directory endpoint (multi-agent list — here we return just this one)
#   - IMPORTANT: Use camelCase keys like manifestUrl and endpointBaseUrl.
# --------------------------------------------------------------------------------------
@app.get("/a2a/agents", tags=["ica4aa"], summary="Agents Directory")
def list_agents(request: Request) -> Dict[str, Any]:
    base = _public_base_url(request)
    agent_id = os.getenv("HELLO_AGENT_ID", "hello-world")
    name = os.getenv("HELLO_AGENT_NAME", "Hello World")
    version = os.getenv("HELLO_AGENT_VERSION", "1.2.0")

    say_hello_input = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Name to greet"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    say_hello_output = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    return {
        "agents": [
            {
                "id": agent_id,
                "name": name,
                "version": version,
                # New recommended fields
                "description": "Universal A2A Hello",
                "tags": ["demo", "tutorial"],
                "endpoints": {
                    "invoke": f"{base}/api/v1/agents/{agent_id}/invoke",
                    "health": f"{base}/healthz",
                },
                "auth": {"type": "none"},
                "input_schema": say_hello_input,   # snake_case for directory
                "output_schema": say_hello_output,
                # Back-compat hints
                "manifestUrl": f"{base}/a2a/manifest",
                "endpointBaseUrl": base,
            }
        ]
    }


# --------------------------------------------------------------------------------------
# ICA4AA: Action - say_hello
#   - Delegates to the Universal A2A backend (/a2a) so you get whichever
#     provider/framework you configured via env (LLM_PROVIDER, AGENT_FRAMEWORK, …).
#   - Runs the blocking HTTP call in a thread to avoid blocking the event loop.
# --------------------------------------------------------------------------------------
@app.post("/a2a/actions/say_hello", response_model=SayHelloOut, tags=["ica4aa"], summary="Say Hello")
async def say_hello(payload: SayHelloIn, request: Request) -> SayHelloOut:
    name = (payload.name or "World").strip() or "World"
    prompt = f"Say hello to {name}."

    backend_base = _backend_base_url(request)
    client = A2AClient(base_url=backend_base)

    try:
        # A2AClient.send is synchronous; run in thread to keep async server responsive
        reply = await run_in_threadpool(client.send, prompt, False)
    except (httpx.HTTPError, Exception):
        # Offline / error fallback still returns a friendly message
        reply = f"Hello, {name}!"

    return SayHelloOut(message=reply)


# --------------------------------------------------------------------------------------
# ICA4AA: Well-known discovery endpoints
# --------------------------------------------------------------------------------------
@app.get("/.well-known/ica4aa/agents", tags=["ica4aa"], summary="Agents Directory (well-known)")
@app.get("/api/v1/agents", tags=["ica4aa"], summary="Agents Directory (compat)")
def well_known_agents(request: Request) -> Dict[str, Any]:
    base = _public_base_url(request)
    agent_id = os.getenv("HELLO_AGENT_ID", "hello-world")
    name = os.getenv("HELLO_AGENT_NAME", "Hello World")
    version = os.getenv("HELLO_AGENT_VERSION", "1.2.0")

    say_hello_input = {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Name to greet"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    say_hello_output = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    return {
        "version": "1.0",
        "agents": [
            {
                "id": agent_id,
                "name": name,
                "version": version,
                "description": "Universal A2A Hello",
                "tags": ["demo", "tutorial"],
                "endpoints": {
                    "invoke": f"{base}/api/v1/agents/{agent_id}/invoke",
                    "health": f"{base}/healthz",
                },
                "auth": {"type": "none"},
                "input_schema": say_hello_input,
                "output_schema": say_hello_output,
            }
        ],
    }


# --------------------------------------------------------------------------------------
# ICA4AA: Invoke wrapper for simple agents
# --------------------------------------------------------------------------------------
@app.post(
    "/api/v1/agents/{agent_id}/invoke",
    response_model=SayHelloOut,
    tags=["ica4aa"],
    summary="Invoke Agent",
)
async def invoke_agent(agent_id: str, payload: SayHelloIn, request: Request) -> SayHelloOut:
    # Reuse the same logic as say_hello
    name = (payload.name or "World").strip() or "World"
    prompt = f"Say hello to {name}."
    backend_base = _backend_base_url(request)
    client = A2AClient(base_url=backend_base)
    try:
        reply = await run_in_threadpool(client.send, prompt, False)
    except Exception:
        reply = f"Hello, {name}!"
    return SayHelloOut(message=reply)
