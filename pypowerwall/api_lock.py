import threading
from contextlib import contextmanager


@contextmanager
def acquire_lock_with_timeout(lock_source, timeout, *, func=None):
    """
    Context manager for acquiring a lock with a timeout.
    Raises TimeoutError if the lock is not acquired in the given timeout.

    Supports three calling conventions:
      - acquire_lock_with_timeout(instance, timeout, func=wrapper)  # per-instance lock via decorator
      - acquire_lock_with_timeout(lock, timeout)  # direct lock object (cloud/fleet API)
    """
    if func is not None:
        lock = getattr(lock_source, func._lock_attr)
    elif hasattr(lock_source, 'acquire'):
        lock = lock_source
    else:
        raise TypeError(f"Cannot resolve lock from {type(lock_source)}")
    if not lock.acquire(blocking=True, timeout=timeout):
        raise TimeoutError("Unable to acquire lock within the specified timeout.")
    try:
        yield
    finally:
        lock.release()


# Backward-compatible alias
acquire_lock_with_backoff = acquire_lock_with_timeout
