"""Tests for frozen-safe version resolution (dev vs PyInstaller bundle)."""

from pathlib import Path

import pytest

from backend import version as version_module


def test_get_version_reads_project_version():
    expected = Path(__file__).resolve().parents[1].joinpath("VERSION").read_text().strip()
    assert version_module.get_version() == expected
    assert version_module.get_version() == version_module.get_version()


def test_get_version_from_meipass(monkeypatch):
    fake = Path(__file__).resolve().parents[1].joinpath("VERSION").parent
    monkeypatch.setattr(version_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(version_module.sys, "_MEIPASS", str(fake), raising=False)
    assert version_module.get_version() == fake.joinpath("VERSION").read_text().strip()


def test_get_version_missing_file(monkeypatch):
    monkeypatch.setattr(version_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(version_module.sys, "_MEIPASS", "/nonexistent/jpnh-bundle", raising=False)
    with pytest.raises(FileNotFoundError):
        version_module.get_version()