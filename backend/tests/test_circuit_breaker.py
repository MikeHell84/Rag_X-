import time

from core.circuit_breaker import CircuitBreaker, CircuitOpenError


def test_closed_by_default():
    breaker = CircuitBreaker("test")
    assert breaker.state == CircuitBreaker.CLOSED
    assert breaker.allow_request()


def test_opens_after_threshold():
    breaker = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=1)

    def boom():
        raise RuntimeError("boom")

    for _ in range(2):
        try:
            breaker.run(boom)
        except RuntimeError:
            pass
        assert breaker.state == CircuitBreaker.CLOSED

    try:
        breaker.run(boom)
    except RuntimeError:
        pass
    assert breaker.state == CircuitBreaker.OPEN
    assert not breaker.allow_request()


def test_half_open_probe():
    breaker = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=0.05)

    def boom():
        raise RuntimeError("boom")

    for _ in range(2):
        try:
            breaker.run(boom)
        except RuntimeError:
            pass

    assert breaker.state == CircuitBreaker.OPEN
    time.sleep(0.1)
    assert breaker.allow_request()
    assert breaker.state == CircuitBreaker.HALF_OPEN


def test_success_closes_again():
    breaker = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=0.05)

    def boom():
        raise RuntimeError("boom")

    try:
        breaker.run(boom)
    except RuntimeError:
        pass
    assert breaker.state == CircuitBreaker.OPEN

    breaker.record_success()
    assert breaker.state == CircuitBreaker.CLOSED


def test_open_blocks_and_raises():
    breaker = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60)
    try:
        breaker.run(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    except RuntimeError:
        pass
    try:
        breaker.run(lambda: "ok")
        raise AssertionError("no debió ejecutarse")
    except CircuitOpenError:
        pass
