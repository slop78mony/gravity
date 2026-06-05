"""Tests for the storage analyzer."""

import os
import tempfile
from pathlib import Path

import pytest

from ipad_optimizer.analyzer import analyze, format_bytes, AnalysisReport
from ipad_optimizer.config import DEFAULTS


def _make_file(path: Path, size: int, content: bytes | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content if content is not None else b"x" * size
    path.write_bytes(data)


class TestFormatBytes:
    def test_bytes(self):
        assert format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert format_bytes(2048) == "2.0 KB"

    def test_megabytes(self):
        assert format_bytes(1024 * 1024 * 3) == "3.0 MB"

    def test_gigabytes(self):
        assert format_bytes(1024 ** 3 * 2) == "2.0 GB"


class TestAnalyze:
    def test_empty_directory(self, tmp_path):
        report = analyze(str(tmp_path), DEFAULTS)
        assert report.total_size == 0
        assert report.file_count == 0
        assert report.duplicates == []
        assert report.large_files == []

    def test_counts_files(self, tmp_path):
        for i in range(5):
            _make_file(tmp_path / f"file_{i}.txt", 100)
        report = analyze(str(tmp_path), DEFAULTS)
        assert report.file_count == 5
        assert report.total_size == 500

    def test_detects_large_files(self, tmp_path):
        large = tmp_path / "big.dat"
        threshold = 1024 * 1024  # 1 MB
        _make_file(large, threshold + 1)
        cfg = {**DEFAULTS, "large_file_threshold": threshold}
        report = analyze(str(tmp_path), cfg)
        assert len(report.large_files) == 1
        assert report.large_files[0][0] == large

    def test_detects_duplicates(self, tmp_path):
        content = b"duplicate content " * 1024  # >10KB
        _make_file(tmp_path / "a.bin", 0, content)
        _make_file(tmp_path / "b.bin", 0, content)
        _make_file(tmp_path / "c.bin", 0, content)
        report = analyze(str(tmp_path), DEFAULTS)
        assert len(report.duplicates) == 1
        assert len(report.duplicates[0]) == 3

    def test_no_false_duplicate_for_unique_files(self, tmp_path):
        _make_file(tmp_path / "a.bin", 0, b"aaa" * 5000)
        _make_file(tmp_path / "b.bin", 0, b"bbb" * 5000)
        report = analyze(str(tmp_path), DEFAULTS)
        assert report.duplicates == []

    def test_nonexistent_path_raises(self):
        with pytest.raises(FileNotFoundError):
            analyze("/nonexistent/path/xyz", DEFAULTS)

    def test_dir_sizes_populated(self, tmp_path):
        sub = tmp_path / "sub"
        _make_file(sub / "f.txt", 200)
        report = analyze(str(tmp_path), DEFAULTS)
        assert str(sub) in report.dir_sizes
