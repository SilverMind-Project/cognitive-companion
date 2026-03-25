"""
MCP (Model Context Protocol) API router.

Exposes /mcp/tools for tool discovery and /mcp/call for tool execution.
All calls require API key authentication with mcp_readonly or higher permissions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    tool: str
    result: Any


@router.get("/tools")
async def list_tools(
    request: Request,
    auth: AuthContext = Depends(require_permission("mcp_readonly")),
):
    """List available MCP tools and their schemas."""
    registry = getattr(request.app.state, "mcp_registry", None)
    if registry is None:
        return {"tools": []}
    return {"tools": registry.list_tools()}


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(
    body: ToolCallRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("mcp_readonly")),
):
    """Execute an MCP tool by name."""
    registry = getattr(request.app.state, "mcp_registry", None)
    if registry is None:
        return ToolCallResponse(tool=body.name, result={"error": "MCP not initialized"})

    result = await registry.call_tool(body.name, body.arguments)
    logger.info("mcp_tool_called", tool=body.name, caller=auth.name)
    return ToolCallResponse(tool=body.name, result=result)
