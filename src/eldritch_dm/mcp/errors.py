"""
Structured exception hierarchy for MCP client errors.

All MCP-related exceptions inherit from MCPError so callers can catch
them with a single `except MCPError` or discriminate by subtype.
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


class MCPError(Exception):
    """Base class for all MCP client errors."""


class MCPTimeoutError(MCPError):
    """Raised when all retry attempts exhausted due to timeout."""


class MCPNetworkError(MCPError):
    """Raised when all retry attempts exhausted due to network error."""


class MCPToolError(MCPError):
    """Raised on a 4xx HTTP response from the MCP endpoint.

    No retry is attempted — 4xx indicates a bad request, not a transient fault.

    Attributes:
        tool_name: The MCP tool that was called.
        arguments: The arguments dict passed to the tool.
        response_payload: Parsed JSON body from the error response, or None.
    """

    def __init__(
        self,
        tool_name: str,
        arguments: dict,
        response_payload: dict | None,
        message: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.response_payload = response_payload
        self._message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        msg = self._message or "MCP tool error"
        return f"{msg}: tool={self.tool_name!r} response={self.response_payload!r}"


class MCPCircuitOpen(MCPError):
    """Raised immediately when the circuit breaker is OPEN.

    No HTTP call is attempted — the circuit breaker is protecting the
    downstream service from further load while it recovers.

    Attributes:
        tool_name: The tool call that was blocked.
    """

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(
            f"MCP circuit breaker is OPEN — refused to call {tool_name!r}"
        )
