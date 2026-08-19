"""Shared pytest fixtures and sys.path setup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
