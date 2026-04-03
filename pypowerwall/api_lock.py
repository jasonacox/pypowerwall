import logging
import threading
from contextlib import contextmanager

log = logging.getLogger(__name__)

def acquire_with_timeout(
    lock: threading.Lock,
    timeout: float,
) -> bool:
    """
    Attempts to acquire a lock with a timeout.

    Uses blocking acquisition so the thread is woken immediately when the
    lock becomes available, avoiding the missed-release windows that occur
    with poll-and-sleep approaches.

    Args:
        lock (threading.Lock): The lock instance to acquire.
        timeout (float): The maximum time (in seconds) to wait for the lock.

    Returns:
        bool: True if the lock was acquired within the timeout period, otherwise False.
    """
    return lock.acquire(blocking=True, timeout=timeout)


@contextmanager
def acquire_lock_with_backoff(func_or_instance, timeout, *, func=None, **backoff_kwargs):
    """
    Context manager for acquiring a lock with a timeout.
    Raises TimeoutError if the lock is not acquired in the given timeout.

    Supports three calling conventions:
      - acquire_lock_with_backoff(instance, timeout, func=wrapper)  # per-instance lock via decorator
      - acquire_lock_with_backoff(lock, timeout)  # direct lock object (cloud/fleet API)
      - acquire_lock_with_backoff(func, timeout)  # legacy: lock on function object
    """
    if func is not None:
        # Per-instance lock: look up lock attribute on the instance
        instance = func_or_instance
        lock_attr = func._lock_attr
        lock = getattr(instance, lock_attr)
    elif hasattr(func_or_instance, 'acquire'):
        # Direct lock object
        lock = func_or_instance
    else:
        # Legacy: lock stored on the function object
        lock = func_or_instance.api_lock
    if not acquire_with_timeout(lock, timeout):
        raise TimeoutError("Unable to acquire lock within the specified timeout.")
    try:
        yield
    finally:
        lock.release()
