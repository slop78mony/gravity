"""Tests for the storage monitor."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ipad_optimizer.monitor import _get_disk_usage, _save_snapshot, show_history
from ipad_optimizer.config import HISTORY_FILE, CONFIG_DIR


class TestGetDiskUsage:
    def test_returns_three_positive_ints(self, tmp_path):
        total, used, free = _get_disk_usage(str(tmp_path))
        assert total > 0
        assert used > 0
        assert free >= 0
        # free may be less than total-used on Linux (reserved blocks for root)
        assert free <= total


class TestSaveSnapshot:
    def test_creates_history_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ipad_optimizer.monitor.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("ipad_optimizer.monitor.HISTORY_FILE", tmp_path / "history.json")
        _save_snapshot("/", 100, 50, 50)
        assert (tmp_path / "history.json").exists()

    def test_appends_entries(self, tmp_path, monkeypatch):
        hfile = tmp_path / "history.json"
        monkeypatch.setattr("ipad_optimizer.monitor.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("ipad_optimizer.monitor.HISTORY_FILE", hfile)
        _save_snapshot("/", 100, 40, 60)
        _save_snapshot("/", 100, 45, 55)
        data = json.loads(hfile.read_text())
        assert len(data) == 2
        assert data[0]["used"] == 40
        assert data[1]["used"] == 45

    def test_caps_at_1000_entries(self, tmp_path, monkeypatch):
        hfile = tmp_path / "history.json"
        monkeypatch.setattr("ipad_optimizer.monitor.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("ipad_optimizer.monitor.HISTORY_FILE", hfile)
        existing = [{"ts": "x", "path": "/", "total": 1, "used": 1, "free": 0}] * 999
        hfile.write_text(json.dumps(existing))
        _save_snapshot("/", 1, 1, 0)
        _save_snapshot("/", 1, 1, 0)
        data = json.loads(hfile.read_text())
        assert len(data) == 1000


class TestShowHistory:
    def test_empty_history(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("ipad_optimizer.monitor.HISTORY_FILE", tmp_path / "no_history.json")
        show_history()
