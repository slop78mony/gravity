"""Tests for the file cleaner."""

from pathlib import Path

import pytest

from ipad_optimizer.analyzer import analyze
from ipad_optimizer.cleaner import clean_duplicates, clean_temp, find_temp_files
from ipad_optimizer.config import DEFAULTS


def _make_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


LARGE_CONTENT = b"z" * 1024 * 15  # 15 KB — above min_duplicate_size


class TestCleanDuplicates:
    def test_removes_extra_copies(self, tmp_path):
        _make_file(tmp_path / "a" / "orig.bin", LARGE_CONTENT)
        _make_file(tmp_path / "b" / "copy.bin", LARGE_CONTENT)
        report = analyze(str(tmp_path), DEFAULTS)
        removed, freed = clean_duplicates(report, dry_run=False)
        assert removed == 1
        assert freed == len(LARGE_CONTENT)
        remaining = list(tmp_path.rglob("*.bin"))
        assert len(remaining) == 1

    def test_dry_run_does_not_delete(self, tmp_path):
        _make_file(tmp_path / "a.bin", LARGE_CONTENT)
        _make_file(tmp_path / "b.bin", LARGE_CONTENT)
        report = analyze(str(tmp_path), DEFAULTS)
        clean_duplicates(report, dry_run=True)
        assert len(list(tmp_path.rglob("*.bin"))) == 2

    def test_no_duplicates_returns_zero(self, tmp_path):
        _make_file(tmp_path / "only.bin", LARGE_CONTENT)
        report = analyze(str(tmp_path), DEFAULTS)
        removed, freed = clean_duplicates(report, dry_run=False)
        assert removed == 0
        assert freed == 0


class TestFindTempFiles:
    def test_finds_matching_patterns(self, tmp_path):
        (tmp_path / "a.tmp").write_bytes(b"x")
        (tmp_path / "b.cache").write_bytes(b"x")
        (tmp_path / "important.txt").write_bytes(b"x")
        found = find_temp_files(tmp_path, ["*.tmp", "*.cache"])
        names = {p.name for p in found}
        assert "a.tmp" in names
        assert "b.cache" in names
        assert "important.txt" not in names

    def test_no_matches_returns_empty(self, tmp_path):
        (tmp_path / "data.csv").write_bytes(b"x")
        found = find_temp_files(tmp_path, ["*.tmp"])
        assert found == []


class TestCleanTemp:
    def test_removes_temp_files(self, tmp_path):
        (tmp_path / "session.tmp").write_bytes(b"x" * 100)
        removed, freed = clean_temp(tmp_path, ["*.tmp"], dry_run=False)
        assert removed == 1
        assert freed == 100
        assert not (tmp_path / "session.tmp").exists()

    def test_dry_run_preserves_files(self, tmp_path):
        (tmp_path / "session.tmp").write_bytes(b"y" * 100)
        clean_temp(tmp_path, ["*.tmp"], dry_run=True)
        assert (tmp_path / "session.tmp").exists()
