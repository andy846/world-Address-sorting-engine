"""The build tool must produce a usable pack manifest and report.

A real pack build used to crash after the database was written, because the
alias language counts were taken out of the metrics before the manifest was
built from them. The synthetic sources below exercise the whole tool.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from build_reference_pack import build, manifest_from_report  # noqa: E402
from tests.unit.test_geonames_builder import make_sources  # noqa: E402


def _prepare_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    make_sources(source)
    (source / "source_manifest.json").write_text(
        json.dumps({"source_date": "2026-10-23"}), encoding="utf-8")
    return source


def test_the_build_writes_a_manifest_and_a_report(tmp_path):
    source = _prepare_source(tmp_path)
    output = tmp_path / "pack"
    report = build(source, output, ["COMPACT_GLOBAL"], compress=True)
    manifest_path = output / "compact_global.manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["profile"] == "COMPACT_GLOBAL"
    assert manifest["pack_version"] == "2026-10-23-k2"
    assert manifest["alias_count_by_language"]
    assert manifest["alias_count"] > 0
    assert manifest["db_bytes"] == (output / "compact_global.sqlite").stat().st_size
    assert manifest["license"] == "CC BY 4.0"
    detail = report["profiles"]["COMPACT_GLOBAL"]
    assert detail["alias_language_counts"]
    assert detail["compressed_bytes"] > 0
    assert (output / "build_report.json").is_file()


def test_the_build_refuses_to_overwrite_a_finished_pack(tmp_path):
    source = _prepare_source(tmp_path)
    output = tmp_path / "pack"
    build(source, output, ["COMPACT_GLOBAL"], compress=False)
    with pytest.raises(FileExistsError):
        build(source, output, ["COMPACT_GLOBAL"], compress=False)


def test_the_build_refuses_a_source_without_a_pinned_date(tmp_path):
    source = _prepare_source(tmp_path)
    (source / "source_manifest.json").unlink()
    with pytest.raises(ValueError):
        build(source, tmp_path / "pack", ["COMPACT_GLOBAL"], compress=False)


def test_the_manifest_can_be_rebuilt_from_the_report(tmp_path):
    """The report and the manifest are two views of one measurement.

    The installer derives the manifest from `build_report.json`, so the two
    must agree byte for byte. When they can drift apart, a pack installs
    under a checksum that was never measured.
    """
    source = _prepare_source(tmp_path)
    output = tmp_path / "pack"
    report = build(source, output, ["COMPACT_GLOBAL"], compress=True)
    written = json.loads(
        (output / "compact_global.manifest.json").read_text(encoding="utf-8"))
    assert manifest_from_report(report, "COMPACT_GLOBAL") == written


def test_a_rebuilt_pack_is_published_under_its_own_version(tmp_path):
    """A pack built today must not be published as the old published one."""
    source = _prepare_source(tmp_path)
    output = tmp_path / "pack"
    report = build(source, output, ["COMPACT_GLOBAL"], compress=False)
    manifest = manifest_from_report(report, "COMPACT_GLOBAL")
    assert manifest["pack_version"] != report["source_date"]

