#!/usr/bin/env python3
"""
devt/error_wrapper.py

Error Handling Wrapper

Provides a decorator to catch and handle exceptions in Typer commands.
"""

import functools
import logging
import typer
from typing import Any, Callable, TypeVar

from devt import __version__

T = TypeVar("T", bound=Callable[..., Any])
logger = logging.getLogger(__name__)

def handle_errors(func: T) -> T:
    """Decorator for catching and handling exceptions in Typer commands."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as err:
            if __version__ == "dev":
                raise err  # Show full traceback in dev mode
            logger.exception("An error occurred in %s:", func.__name__)
            raise typer.Exit(code=1)  # Exit cleanly in production mode
    return wrapper  
