import time
import random
import threading
import functools
from typing import Callable, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def random_delay() -> None:
    min_delay = config.REQUEST_DELAY_MIN
    max_delay = config.REQUEST_DELAY_MAX
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)


def get_headers(referer: str = None, origin: str = None) -> dict:
    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    }
    
    if referer:
        headers["Referer"] = referer
    
    if origin:
        headers["Origin"] = origin
    
    return headers


class RateLimiter:
    def __init__(self, max_concurrent: int = None):
        if max_concurrent is None:
            max_concurrent = config.MAX_CONCURRENT
        self._semaphore = threading.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
    
    def acquire(self, blocking: bool = True, timeout: float = None) -> bool:
        return self._semaphore.acquire(blocking=blocking, timeout=timeout)
    
    def release(self) -> None:
        self._semaphore.release()
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def retry_on_failure(max_retries: int = 3, delay: float = 1, exceptions: tuple = None):
    if exceptions is None:
        exceptions = (Exception,)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            
            raise last_exception
        
        return wrapper
    
    return decorator
