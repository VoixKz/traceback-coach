"""traceback-coach — a visual error-literacy coach for Jupyter notebooks."""
from __future__ import annotations

__version__ = "0.5.1"

__all__ = ["__version__", "load_ipython_extension", "unload_ipython_extension"]


def load_ipython_extension(ipython):  # pragma: no cover - wired in Task 8
    from .magics import register

    register(ipython)


def unload_ipython_extension(ipython):  # pragma: no cover - wired in Task 8
    from .magics import unregister

    unregister(ipython)
