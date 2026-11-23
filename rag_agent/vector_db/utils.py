import logging
import time
from contextlib import contextmanager


@contextmanager
def timed(label: str, logger: logging.Logger | None = None, level: int = logging.DEBUG):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        _logger = logger or logging.getLogger(__name__)
        _logger.log(level, "%s: %.3fs", label, elapsed)
