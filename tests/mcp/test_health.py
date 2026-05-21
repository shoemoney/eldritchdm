"""
Tests for CircuitBreaker and HealthCheck.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from eldritch_dm.mcp.health import CircuitBreaker, CircuitState, HealthCheck, get_circuit_state


@pytest.fixture
def breaker():
    return CircuitBreaker(threshold=3)


# ── CircuitBreaker state machine ─────────────────────────────────────────────


def test_circuit_starts_closed(breaker):
    assert breaker.state == CircuitState.CLOSED


def test_three_failures_trip_open(breaker):
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED  # not yet
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_additional_failure_while_open_does_not_raise(breaker):
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    # Should not raise
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_success_after_open_returns_closed(breaker):
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker._failures == 0


def test_isolated_failures_dont_trip(breaker):
    """failure → success → failure → success → failure should stay CLOSED."""
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED


def test_threshold_configurable():
    b = CircuitBreaker(threshold=5)
    for _ in range(4):
        b.record_failure()
    assert b.state == CircuitState.CLOSED
    b.record_failure()
    assert b.state == CircuitState.OPEN


def test_get_circuit_state_helper(breaker):
    for _ in range(3):
        breaker.record_failure()
    assert get_circuit_state(breaker) == CircuitState.OPEN
    breaker.record_success()
    assert get_circuit_state(breaker) == CircuitState.CLOSED


# ── HealthCheck ────────────────────────────────────────────────────────────────


ENDPOINT = "http://localhost:8765/v1"
MODELS_URL = f"{ENDPOINT}/models"


@respx.mock
async def test_health_check_records_success(breaker):
    """GET /models → 200 → breaker.state == CLOSED, at least 1 success."""
    respx.get(MODELS_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "ShoeGPT"}]})
    )
    hc = HealthCheck(endpoint=ENDPOINT, interval=0.02, breaker=breaker)
    await hc.start()
    await asyncio.sleep(0.1)
    await hc.stop()

    assert breaker.state == CircuitState.CLOSED


@respx.mock
async def test_health_check_trips_on_consecutive_failures(breaker):
    """GET /models → 500 always → breaker trips OPEN after 3 failures."""
    respx.get(MODELS_URL).mock(return_value=httpx.Response(500))
    hc = HealthCheck(endpoint=ENDPOINT, interval=0.02, breaker=breaker)
    await hc.start()
    await asyncio.sleep(0.15)
    await hc.stop()

    assert breaker.state == CircuitState.OPEN


@respx.mock
async def test_health_check_recovers():
    """After tripping OPEN, one success returns CLOSED."""
    breaker = CircuitBreaker(threshold=1)
    call_count = 0

    def _side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(500)
        return httpx.Response(200, json={"data": []})

    respx.get(MODELS_URL).mock(side_effect=_side_effect)
    hc = HealthCheck(endpoint=ENDPOINT, interval=0.02, breaker=breaker)
    await hc.start()
    await asyncio.sleep(0.2)
    await hc.stop()

    # Eventually recovered to CLOSED after a successful ping
    assert breaker.state == CircuitState.CLOSED


@respx.mock
async def test_health_check_stop_clean():
    """stop() cancels the task without warnings."""
    breaker = CircuitBreaker()
    respx.get(MODELS_URL).mock(return_value=httpx.Response(200, json={}))

    hc = HealthCheck(endpoint=ENDPOINT, interval=60.0, breaker=breaker)
    await hc.start()
    # Task is running; stop it before any ping fires
    await hc.stop()
    assert hc._task is None
