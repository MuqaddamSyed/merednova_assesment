"""Graceful shutdown coordination across threads."""

from __future__ import annotations

import atexit
import logging
import signal
import threading
from typing import Callable

logger = logging.getLogger("voice_coder.shutdown")


class ShutdownCoordinator:
    """Thread-safe shutdown flag and callback registry."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._shutdown_complete = False

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def request_shutdown(self) -> None:
        with self._lock:
            if self._event.is_set() or self._shutdown_complete:
                return
            self._event.set()
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb()
            except Exception as exc:
                logger.exception("Shutdown callback failed: %s", exc)
        with self._lock:
            self._shutdown_complete = True

    def register(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


def install_exit_handlers(shutdown: ShutdownCoordinator) -> None:
    """Ensure cleanup runs on Ctrl+C, terminal close, and normal exit."""

    def _signal_handler(signum: int, _frame) -> None:
        logger.info("Received signal %s — shutting down", signum)
        shutdown.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            pass

    try:
        signal.signal(signal.SIGHUP, _signal_handler)
    except (ValueError, OSError, AttributeError):
        pass

    atexit.register(shutdown.request_shutdown)
