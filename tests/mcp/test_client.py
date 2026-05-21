"""
Tests for MCPClient.

Uses respx to mock httpx calls — zero real network traffic.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from eldritch_dm.mcp.client import MCPClient
from eldritch_dm.mcp.errors import (
    MCPCircuitOpen,
    MCPNetworkError,
    MCPTimeoutError,
    MCPToolError,
)
from eldritch_dm.mcp.health import CircuitBreaker, CircuitState

BASE_URL = "http://localhost:8765"
MCP_URL = f"{BASE_URL}/v1/mcp/execute"


@pytest.fixture
def client():
    """MCPClient instance with no circuit breaker, pointing at test BASE_URL."""
    return MCPClient(base_url=BASE_URL, http2=False)


@pytest.fixture
def breaker():
    return CircuitBreaker(threshold=3)


# ── Happy path ────────────────────────────────────────────────────────────────


@respx.mock
async def test_happy_path(client):
    """200 response returns parsed JSON body; one HTTP call made."""
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(200, json={"result": {"ok": True}})
    )
    result = await client.call("dm20__create_campaign", name="test")
    assert result == {"result": {"ok": True}}
    assert route.called
    assert len(route.calls) == 1
    await client.aclose()


@respx.mock
async def test_post_body_shape(client):
    """The request body must be {tool_name, arguments}."""
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await client.call("x", k="v")
    assert route.calls.last.request.content is not None
    import json
    body = json.loads(route.calls.last.request.content)
    assert body == {"tool_name": "x", "arguments": {"k": "v"}}
    await client.aclose()


@respx.mock
async def test_user_agent_header_set():
    """User-Agent header contains 'EldritchDM/0.1'."""
    c = MCPClient(base_url=BASE_URL, http2=False)
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={}))
    await c.call("x")
    ua = route.calls.last.request.headers.get("user-agent", "")
    assert "EldritchDM/0.1" in ua
    await c.aclose()


# ── Retry behaviour ───────────────────────────────────────────────────────────


@respx.mock
async def test_retry_on_timeout():
    """Times out on first two attempts, succeeds on third."""
    c = MCPClient(base_url=BASE_URL, http2=False)
    call_count = 0

    def _side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"ok": True})

    respx.post(MCP_URL).mock(side_effect=_side_effect)

    # Patch tenacity wait to avoid real sleeps
    from unittest.mock import patch  # noqa: PLC0415

    import tenacity  # noqa: PLC0415

    # Use monkeypatching on the wait within the retryer instead
    with patch(
        "eldritch_dm.mcp.client.tenacity.wait_exponential",
        return_value=tenacity.wait_none(),
    ):
        result = await c.call("x")

    assert result == {"ok": True}
    assert call_count == 3
    await c.aclose()


@respx.mock
async def test_retry_on_5xx():
    """503 on first two attempts, 200 on third."""
    from unittest.mock import patch

    import tenacity

    c = MCPClient(base_url=BASE_URL, http2=False)
    call_count = 0

    def _side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"ok": True})

    respx.post(MCP_URL).mock(side_effect=_side_effect)

    with patch(
        "eldritch_dm.mcp.client.tenacity.wait_exponential",
        return_value=tenacity.wait_none(),
    ):
        result = await c.call("x")

    assert result == {"ok": True}
    assert call_count == 3
    await c.aclose()


@respx.mock
async def test_no_retry_on_4xx():
    """400 response raises MCPToolError immediately; exactly 1 HTTP call."""
    c = MCPClient(base_url=BASE_URL, http2=False)
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(400, json={"error": "bad tool args"})
    )

    with pytest.raises(MCPToolError) as exc_info:
        await c.call("dm20__bad_tool", k="v")

    err = exc_info.value
    assert err.tool_name == "dm20__bad_tool"
    assert err.response_payload == {"error": "bad tool args"}
    assert len(route.calls) == 1
    await c.aclose()


@respx.mock
async def test_timeout_exhaustion_raises_mcp_timeout():
    """All attempts time out → MCPTimeoutError with __cause__ being TimeoutException."""
    from unittest.mock import patch

    import tenacity

    c = MCPClient(base_url=BASE_URL, http2=False)

    def _always_timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    respx.post(MCP_URL).mock(side_effect=_always_timeout)

    with patch(
        "eldritch_dm.mcp.client.tenacity.wait_exponential",
        return_value=tenacity.wait_none(),
    ):
        with pytest.raises(MCPTimeoutError) as exc_info:
            await c.call("x")

    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)
    await c.aclose()


@respx.mock
async def test_network_exhaustion_raises_mcp_network():
    """All attempts raise NetworkError → MCPNetworkError."""
    from unittest.mock import patch

    import tenacity

    c = MCPClient(base_url=BASE_URL, http2=False)

    def _always_network_error(request):
        raise httpx.NetworkError("connection refused", request=request)

    respx.post(MCP_URL).mock(side_effect=_always_network_error)

    with patch(
        "eldritch_dm.mcp.client.tenacity.wait_exponential",
        return_value=tenacity.wait_none(),
    ):
        with pytest.raises(MCPNetworkError):
            await c.call("x")

    await c.aclose()


# ── Circuit breaker ───────────────────────────────────────────────────────────


@respx.mock
async def test_circuit_open_blocks_call(breaker):
    """When breaker is OPEN, MCPCircuitOpen raised without any HTTP call."""
    # Trip the breaker
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    c = MCPClient(base_url=BASE_URL, circuit_breaker=breaker, http2=False)
    route = respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(MCPCircuitOpen) as exc_info:
        await c.call("x")

    assert exc_info.value.tool_name == "x"
    assert not route.called
    await c.aclose()


@respx.mock
async def test_circuit_success_recorded(breaker):
    """Successful call records success on the circuit breaker."""
    c = MCPClient(base_url=BASE_URL, circuit_breaker=breaker, http2=False)
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    await c.call("x")

    assert breaker.state == CircuitState.CLOSED
    assert breaker._failures == 0
    await c.aclose()


@respx.mock
async def test_circuit_failure_recorded(breaker):
    """Terminal failure (timeout exhaustion) records failure on the circuit breaker."""
    from unittest.mock import patch

    import tenacity

    c = MCPClient(base_url=BASE_URL, circuit_breaker=breaker, http2=False)

    def _always_timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    respx.post(MCP_URL).mock(side_effect=_always_timeout)

    with patch(
        "eldritch_dm.mcp.client.tenacity.wait_exponential",
        return_value=tenacity.wait_none(),
    ):
        with pytest.raises(MCPTimeoutError):
            await c.call("x")

    # One terminal failure should be recorded
    assert breaker._failures >= 1
    await c.aclose()


# ── Lifecycle ─────────────────────────────────────────────────────────────────


@respx.mock
async def test_aclose_closes_httpx_client():
    """aclose() closes the underlying httpx client."""
    c = MCPClient(base_url=BASE_URL, http2=False)
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={}))
    await c.call("x")  # ensure client is initialized

    await c.aclose()
    assert c._client is None
