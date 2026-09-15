from __future__ import annotations

from .logging import error
from .config import getconf


def handle(fn: callable) -> any:
    try:
        return fn()
    except Exception as exc:
        error.from_exception(exc).print()
        if getconf("debug", False):
            raise exc
        
def safe(fn: callable) -> callable:
    return lambda *args, **kwargs: handle(lambda: fn(*args, **kwargs))

def fallback(fn: callable, fallback: any) -> any:
    try:
        return fn()
    except Exception as exc:
        error.from_exception(exc).print()
        if getconf("debug", False):
            raise exc
        return fallback