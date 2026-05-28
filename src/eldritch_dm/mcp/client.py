"""
MCPClient — httpx-based client for the dm20 MCP endpoint.

Features:
- Lazy httpx.AsyncClient initialization (one shared client per MCPClient instance)
- tenacity retry: 3 attempts, exponential backoff 0.5s/1s/2s
  Retries: httpx.TimeoutException, httpx.NetworkError, 5xx status
  No retry on 4xx (surfaces as MCPToolError immediately)
- Circuit breaker integration: raises MCPCircuitOpen when OPEN
  Records success/failure on the breaker after each call
- Structured logging: tool_name, attempt_n, duration_ms bound on every call
- User-Agent: EldritchDM/0.1
"""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import httpx
import tenacity

from eldritch_dm.logging import get_logger
from eldritch_dm.mcp.errors import (
    MCPCircuitOpen,
    MCPNetworkError,
    MCPTimeoutError,
    MCPToolError,
)

if TYPE_CHECKING:
    from eldritch_dm.mcp.health import CircuitBreaker

log = get_logger(__name__)

_DEFAULT_USER_AGENT = "EldritchDM/0.1 (+https://github.com/shoemoney/EldritchDM)"


class _TransientHTTPError(Exception):
    """Internal signal for tenacity: a 5xx response that should be retried."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"HTTP {response.status_code}")


class MCPClient:
    """Async MCP client with retry, circuit breaker, and structured logging.

    Args:
        base_url: Base URL of the MCP endpoint (e.g. "http://localhost:8765").
            The client appends "/v1/mcp/execute" for tool calls.
        circuit_breaker: Optional CircuitBreaker; if OPEN, calls raise MCPCircuitOpen
            without hitting the network.
        timeout_connect: Connect timeout in seconds.
        timeout_read: Read timeout in seconds.
        timeout_write: Write timeout in seconds.
        user_agent: User-Agent header value.
        http2: Enable HTTP/2 (default True; requires httpx[http2]).
    """

    def __init__(
        self,
        base_url: str,
        *,
        circuit_breaker: CircuitBreaker | None = None,
        timeout_connect: float = 2.0,
        timeout_read: float = 30.0,
        timeout_write: float = 5.0,
        user_agent: str = _DEFAULT_USER_AGENT,
        http2: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._execute_url = f"{self._base_url}/v1/mcp/execute"
        self._circuit_breaker = circuit_breaker
        self._timeout = httpx.Timeout(
            connect=timeout_connect, read=timeout_read, write=timeout_write, pool=2.0
        )
        self._headers = {
            "User-Agent": user_agent,
            "Content-Type": "application/json",
        }
        self._http2 = http2
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._logger = log.bind(component="mcp_client")

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily initialize the shared httpx.AsyncClient."""
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        timeout=self._timeout,
                        headers=self._headers,
                        http2=self._http2,
                    )
        return self._client

    async def call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        """Call an MCP tool and return the parsed JSON response.

        Args:
            tool_name: Fully qualified tool name (e.g. "dm20__create_campaign").
            **arguments: Keyword arguments forwarded as the tool's arguments dict.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            MCPCircuitOpen: Circuit breaker is OPEN; no HTTP call made.
            MCPToolError: MCP returned a 4xx response (bad request).
            MCPTimeoutError: All retry attempts exhausted due to timeout.
            MCPNetworkError: All retry attempts exhausted due to network error.
        """
        # Check circuit breaker before any I/O
        if self._circuit_breaker is not None:
            from eldritch_dm.mcp.health import CircuitState
            if self._circuit_breaker.state == CircuitState.OPEN:
                raise MCPCircuitOpen(tool_name)

        try:
            result = await self._invoke_with_retry(tool_name, arguments)
        except (MCPTimeoutError, MCPNetworkError, MCPToolError):
            if self._circuit_breaker is not None:
                self._circuit_breaker.record_failure()
            raise
        else:
            if self._circuit_breaker is not None:
                self._circuit_breaker.record_success()
            return result

    async def _invoke_with_retry(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute the HTTP call with tenacity retry.

        Retries on: httpx.TimeoutException, httpx.NetworkError, _TransientHTTPError (5xx).
        Does NOT retry on: MCPToolError (4xx).

        Converts tenacity.RetryError to MCPTimeoutError or MCPNetworkError.
        """
        attempt_n = 0

        async def _attempt() -> dict[str, Any]:
            nonlocal attempt_n
            attempt_n += 1
            client = await self._ensure_client()
            start = time.monotonic()
            try:
                r = await client.post(
                    self._execute_url,
                    json={"tool_name": tool_name, "arguments": arguments},
                )
            except httpx.TimeoutException:
                self._logger.warning(
                    "mcp_call_timeout",
                    tool_name=tool_name,
                    attempt_n=attempt_n,
                )
                raise
            except httpx.NetworkError as exc:
                self._logger.warning(
                    "mcp_call_network_error",
                    tool_name=tool_name,
                    attempt_n=attempt_n,
                    error=str(exc),
                )
                raise

            duration_ms = int((time.monotonic() - start) * 1000)

            if r.status_code >= 500:
                self._logger.warning(
                    "mcp_call_5xx",
                    tool_name=tool_name,
                    attempt_n=attempt_n,
                    status_code=r.status_code,
                    duration_ms=duration_ms,
                )
                raise _TransientHTTPError(r)

            if 400 <= r.status_code < 500:
                try:
                    payload = r.json()
                except Exception:
                    payload = None
                self._logger.error(
                    "mcp_call_4xx",
                    tool_name=tool_name,
                    attempt_n=attempt_n,
                    status_code=r.status_code,
                    duration_ms=duration_ms,
                )
                raise MCPToolError(
                    tool_name,
                    arguments,
                    payload,
                    message=f"HTTP {r.status_code}",
                )

            # Success
            self._logger.info(
                "mcp_call_ok",
                tool_name=tool_name,
                attempt_n=attempt_n,
                duration_ms=duration_ms,
            )
            return r.json()

        # Build the tenacity retry decorator dynamically so tests can override wait
        retryer = tenacity.AsyncRetrying(
            stop=tenacity.stop_after_attempt(3),
            wait=tenacity.wait_exponential(multiplier=0.5, min=0.5, max=2.0),
            retry=tenacity.retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, _TransientHTTPError)
            ),
            reraise=False,
        )

        try:
            async for attempt in retryer:
                with attempt:
                    return await _attempt()
        except tenacity.RetryError as exc:
            last = exc.last_attempt.exception()
            if isinstance(last, httpx.TimeoutException):
                raise MCPTimeoutError(
                    f"MCP call timed out after {attempt_n} attempt(s): {tool_name!r}"
                ) from last
            raise MCPNetworkError(
                f"MCP network error after {attempt_n} attempt(s): {tool_name!r}"
            ) from last

        # Should not reach here; appease type checkers
        raise MCPNetworkError("Unexpected exit from retry loop")  # pragma: no cover

    async def aclose(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
