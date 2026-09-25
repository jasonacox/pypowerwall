import logging
import threading
from contextlib import contextmanager

log = logging.getLogger(__name__)

# pylint: disable=unused-argument
def acquire_with_exponential_backoff(
    lock: threading.Lock,
    timeout: float,
    initial_delay: float = 0.1,
    factor: int = 2,
    max_delay: int = 2,
    jitter: float = 0.1
) -> bool:
    """
    Attempts to acquire a lock, waiting up to timeout seconds.

    This now uses the native (C-level) blocking acquire with a timeout, which
    wakes up as soon as the lock is released. The previous implementation
    polled with exponentially increasing sleeps, which could add up to ~2s of
    idle latency after the lock was already free.

    The backoff parameters (initial_delay, factor, max_delay, jitter) are kept
    for signature compatibility but are no longer used - the kernel-level wait
    has no polling delay to tune.

    Args:
        lock (threading.Lock): The lock instance to acquire.
        timeout (float): The maximum time (in seconds) to wait for the lock.

    Returns:
        bool: True if the lock was acquired within the timeout period, otherwise False.
    """
    if timeout is None or timeout <= 0:
        # Preserve prior behavior: a non-positive timeout never acquires
        return False
    acquired = lock.acquire(timeout=timeout)
    if not acquired:
        log.debug(f"Unable to acquire {lock} within {timeout}s")
    return acquired


@contextmanager
def acquire_lock_with_backoff(lock_holder, timeout, **backoff_kwargs):
    """
    Context manager for acquiring a lock with a bounded wait.
    Raises TimeoutError if the lock is not acquired in the given timeout.

    ``lock_holder`` is either the lock itself (anything with ``acquire`` /
    ``release`` - the per-instance TEDAPI locks) or an object carrying the
    lock as an ``api_lock`` attribute (legacy holder convention). ``None``,
    or a holder without a lock, yields a no-op context.
    """
    if lock_holder is None:
        # no-op context
        yield
        return
    if hasattr(lock_holder, "acquire") and hasattr(lock_holder, "release"):
        lock = lock_holder
    elif hasattr(lock_holder, "api_lock"):
        lock = lock_holder.api_lock
    else:
        # no-op context
        yield
        return
    if not acquire_with_exponential_backoff(lock, timeout, **backoff_kwargs):
        raise TimeoutError("Unable to acquire lock within the specified timeout.")
    try:
        yield
    finally:
        lock.release()
