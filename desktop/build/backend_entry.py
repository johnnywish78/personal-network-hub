"""PyInstaller entrypoint for the packaged JPNH backend.

Kept intentionally tiny: the import graph of backend.main pulls in the whole
FastAPI application, which PyInstaller bundles into the frozen executable.
"""

from backend.main import _main

if __name__ == "__main__":
    _main()
