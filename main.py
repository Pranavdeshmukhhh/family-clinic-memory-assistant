"""
Backward-compatibility shim.

Both of these commands work:
    uvicorn main:app          # legacy (this file)
    uvicorn app.main:app      # canonical (new package)
"""
from app.main import app  # noqa: F401
