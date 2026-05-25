"""
EldritchDM MCP subpackage — public API surface.

Exports the error hierarchy, MCPClient, health check, circuit breaker,
and the typed tool wrappers.

DO NOT import from eldritch_dm.persistence or eldritch_dm.safety — boundary discipline.
"""

from __future__ import annotations

from eldritch_dm.mcp import tools
from eldritch_dm.mcp.cache import CACHEABLE_TOOLS, MCPCache, MCPCacheMetrics
from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.errors import (
    MCPCircuitOpen,
    MCPError,
    MCPNetworkError,
    MCPTimeoutError,
    MCPToolError,
)
from eldritch_dm.mcp.health import CircuitBreaker, CircuitState, HealthCheck, get_circuit_state

__all__ = [
    # Client
    "MCPClient",
    # Cache (Phase 16)
    "MCPCache",
    "MCPCacheMetrics",
    "CACHEABLE_TOOLS",
    # Errors
    "MCPError",
    "MCPTimeoutError",
    "MCPNetworkError",
    "MCPToolError",
    "MCPCircuitOpen",
    # Health
    "HealthCheck",
    "CircuitBreaker",
    "CircuitState",
    "get_circuit_state",
    # Tools namespace
    "tools",
]
