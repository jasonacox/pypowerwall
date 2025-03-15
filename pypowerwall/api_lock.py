import logging
import random
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import DefaultDict

log = logging.getLogger(__name__)

def acquire_with_exponential_backoff(
    lock: threading.Lock,
    timeout: float,
    initial_delay: float = 0.1,
    factor: int = 2,
    max_delay: int = 2,
    jitter: float = 0.1
) -> bool:
    """
    Attempts to acquire a lock using exponential backoff with jitter.

    This function repeatedly attempts to acquire the given lock without blocking.
    If the lock is not immediately available, it waits for a delay period that increases
    exponentially with each attempt, plus a random jitter to reduce contention. The process
    continues until the lock is acquired or the total elapsed time exceeds the specified timeout.

    Args:
        lock (threading.Lock): The lock instance to acquire.
        timeout (float): The total time (in seconds) to keep trying to acquire the lock.
        initial_delay (float, optional): The initial delay (in seconds) before retrying after a failed attempt. Defaults to 0.1.
        factor (int, optional): The multiplier for the delay after each failed attempt. Defaults to 2.
        max_delay (int, optional): The maximum delay (in seconds) between retries. Defaults to 2.
        jitter (float, optional): The maximum additional random delay (in seconds) added to each sleep interval. Defaults to 0.1.

    Returns:
        bool: True if the lock was acquired within the timeout period, otherwise False.
    """
    start_time = time.perf_counter()
    delay = initial_delay

    # Continue trying until the elapsed time exceeds the timeout
    elapsed = time.perf_counter() - start_time
    while elapsed < timeout:
        if lock.acquire(blocking=False):
            return True
        remaining_time = timeout - elapsed
        # Ensure we don't sleep past the timeout and add a bit of random jitter
        sleep_time = min(delay, remaining_time) + random.uniform(0, jitter)
        time.sleep(sleep_time)
        delay = min(delay * factor, max_delay)
        log.info(f"Timeout for {lock}")
        elapsed = time.perf_counter() - start_time

    return False


@contextmanager
def acquire_lock_with_backoff(func, timeout, **backoff_kwargs):
    """
    Context manager for acquiring a lock using exponential backoff with jitter.
    Raises TimeoutError if the lock is not acquired in the given timeout.
    """
    lock: threading.Lock = func.api_lock
    if not acquire_with_exponential_backoff(lock, timeout, **backoff_kwargs):
        raise TimeoutError("Unable to acquire lock within the specified timeout.")
    try:
        yield
    finally:
        lock.release()
