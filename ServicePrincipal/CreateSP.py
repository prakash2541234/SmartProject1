"""Compatibility wrapper for Azure Functions indexing.

The canonical function app lives in function_app.py. This module re-exports
its app object so the worker does not index two separate apps with the same
routes.
"""

from function_app import app  # noqa: F401
