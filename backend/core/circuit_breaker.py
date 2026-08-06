"""Cortocircuito para proveedores externos (OpenAI).

Evita bombardear a la API cuando esta está degradada: tras N fallos la
"puerta" se abre y se rechaza la llamada de inmediato; tras un periodo de
enfriamiento se deja pasar una llamada de prueba (half-open) para validar
la recuperación. Esto protege la cuota y el presupuesto de tokens.
"""

import time
from threading import Lock


class CircuitBreaker:
    OPEN = "open"
    HALF_OPEN = "half-open"
    CLOSED = "closed"

    def __init__(self, name: str, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._lock = Lock()
        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._last_opened_at = 0.0

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._last_opened_at >= self.cooldown_seconds:
                    self._state = self.HALF_OPEN
                    return True
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            if self._state != self.CLOSED:
                self._state = self.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._state = self.OPEN
                self._last_opened_at = time.monotonic()

    def run(self, func, *args, failure_predicate=None, **kwargs):
        if not self.allow_request():
            raise CircuitOpenError(f"circuit '{self.name}' abierto")
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            if failure_predicate is None or failure_predicate(exc):
                self.record_failure()
            raise
        self.record_success()
        return result


class CircuitOpenError(Exception):
    pass
