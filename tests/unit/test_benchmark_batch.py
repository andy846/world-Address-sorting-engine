"""The benchmark has to measure the path a real mailing run takes.

The catalogue file is data, not authority: without the signed approval
that governs it, no destination code may be asserted, and every record
would come out as a review. A measurement that only produces reviews
describes work a production run never does.

The measurement also has to be *attributable*. The peak resident memory of
a process is its high water mark, so a run that shares a process with an
earlier one cannot be told apart from it. Every measurement therefore runs
in a process of its own.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_batch import (  # noqa: E402
    PLACES,
    _cleanup_measurement_inputs,
    build_fixture_master,
    git_provenance,
    measure,
    measure_resume,
    peak_rss_bytes,
    street_evidence_violations,
)
from tests.unit.test_retrieve import geo  # noqa: E402


def test_the_benchmark_measures_the_matching_path(tmp_path):
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    result = measure(30, master, gazetteer, tmp_path / "work", 10, "test", places)
    assert result["status_counts"].get("MATCHED", 0) > 0
    assert result["status_counts"].get("REVIEW_CODE_MAPPING", 0) == 0


def test_the_benchmark_reports_the_pack_and_the_catalogue_it_measured(tmp_path):
    """A measurement may never be read without the data it was taken against."""
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    result = measure(30, master, gazetteer, tmp_path / "work", 10, "test", places)
    assert result["pack_bytes"] == gazetteer.stat().st_size
    assert result["catalogue_bytes"] == master.db_path.stat().st_size
    assert result["records_per_second"] > 0


def test_every_measurement_runs_in_a_process_of_its_own(tmp_path):
    """The peak memory of a run belongs to that run and to no other."""
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    first = measure(30, master, gazetteer, tmp_path / "work", 10, "test", places)
    second = measure(30, master, gazetteer, tmp_path / "work", 10, "test", places)
    assert first["pid"] != os.getpid()
    assert second["pid"] != os.getpid()
    assert first["pid"] != second["pid"]
    assert first["peak_rss_bytes"] > 0
    assert second["peak_rss_bytes"] > 0


def test_measurement_uses_its_requested_work_directory(tmp_path):
    master = build_fixture_master(tmp_path / "master")
    work = tmp_path / "private-benchmark-work"
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    result = measure(30, master, gazetteer, work, 10, "test", places)
    root = work / result["measurement_dir"]
    assert root.parent == work.resolve()
    assert (root / result["output_dir"] / "Run_Manifest.json").is_file()


def test_resume_measurement_uses_its_requested_work_directory(tmp_path):
    master = build_fixture_master(tmp_path / "master")
    work = tmp_path / "private-benchmark-work"
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    result = measure_resume(30, master, gazetteer, work, 10, 1, places)
    root = work / result["measurement_dir"]
    assert root.parent == work.resolve()
    assert (root / result["output_dir"] / "Run_Manifest.json").is_file()


@pytest.mark.parametrize("kind", ["measure", "resume"])
def test_measurement_never_deletes_preexisting_work_artifacts(tmp_path, kind):
    master = build_fixture_master(tmp_path / "master")
    work = tmp_path / "existing-private-work"
    work.mkdir()
    sentinel = work / "run-30"
    sentinel.mkdir()
    protected = sentinel / "operator-file.txt"
    protected.write_text("keep me", encoding="utf-8")
    places_file = work / "places.json"
    places_file.write_text("operator data", encoding="utf-8")
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    if kind == "measure":
        measure(30, master, gazetteer, work, 10, "test", places)
    else:
        measure_resume(30, master, gazetteer, work, 10, 1, places)
    assert protected.read_text(encoding="utf-8") == "keep me"
    assert places_file.read_text(encoding="utf-8") == "operator data"


def test_relative_pack_path_is_resolved_before_the_child_changes_directory(
        tmp_path, monkeypatch):
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    work = tmp_path / "private-benchmark-work"
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    monkeypatch.chdir(tmp_path)
    result = measure(30, master, Path(gazetteer.name), work, 10, "test", places)
    assert result["pack_sha256"]
    assert result["rules_version"]


def test_a_measurement_that_matched_nothing_is_refused(tmp_path):
    """A throughput number for a run that asserted nothing is not a measurement."""
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    # Portugal is not issued by the fixture master, so no row can be matched.
    places = [place for place in PLACES if place[5] == "PT"]
    with pytest.raises(SystemExit):
        measure(30, master, gazetteer, tmp_path / "work", 10, "test", places)


def test_a_resume_measurement_that_matched_nothing_is_refused(tmp_path):
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] == "PT"]
    with pytest.raises(SystemExit, match="matched no record"):
        measure_resume(30, master, gazetteer, tmp_path / "work", 10, 1, places)


def test_the_resume_measurement_reports_memory_and_the_data_it_measured(tmp_path):
    """A restart cost without its memory and its data is not a measurement."""
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    result = measure_resume(30, master, gazetteer, tmp_path / "work", 10, 1, places)
    assert result["peak_rss_bytes"] > 0
    assert result["pack_bytes"] == gazetteer.stat().st_size
    assert result["catalogue_bytes"] == master.db_path.stat().st_size
    assert result["pid"] != os.getpid()


def test_the_peak_memory_of_a_process_is_never_reported_as_zero(tmp_path):
    """A number the tool could not measure must not be a number at all."""
    assert peak_rss_bytes() > 0


def test_the_street_names_carry_no_place_evidence(tmp_path, monkeypatch):
    """A street name is a place name the reader would look up."""
    gazetteer = geo(tmp_path, extra_rows=[
        "\t".join(["99", "Nanjing", "Nanjing", "", "0", "0", "P", "PPL", "CN",
                   "", "01", "", "", "", "8000000", "", "", "UTC", "2024-01-01"])],
        extra_aliases=[
            "101\t1\tzh-Hant\t東京\n",
            "102\t4\tzh-Hant\t孟買\n",
            "103\t7\tzh\t印度\n",
            "104\t8\tzh\t日本\n",
        ])
    # This tiny gazetteer contains Tokyo and Mumbai, not all Japanese and
    # Indian cities from the global benchmark pool. Its Han names must be
    # explicit aliases rather than depend on an optional converter.
    places = [place for place in PLACES if place[0] in ("Tokyo", "Mumbai")]
    assert street_evidence_violations(gazetteer, places) == []
    monkeypatch.setattr("benchmark_batch.STREET_EN", ("Nanjing Road",))
    violations = street_evidence_violations(gazetteer, places)
    assert violations
    assert all(item["problem"] == "the street name adds a country"
               and item["countries"] == ["CN"] for item in violations)


def test_input_cleanup_is_limited_to_owned_measurement_directories(tmp_path):
    work = tmp_path / "benchmark-work"
    work.mkdir()
    caller_input = work / "input-30.csv"
    caller_input.write_text("caller-owned", encoding="utf-8")
    owned = work / "measure-30-owned"
    owned.mkdir()
    owned_input = owned / "input-30.csv"
    owned_input.write_text("generated", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_input = outside / "input-30.csv"
    outside_input.write_text("outside", encoding="utf-8")

    _cleanup_measurement_inputs(work, [
        {"measurement_dir": owned.name, "rows": 30},
        {"measurement_dir": "..", "rows": 30},
    ])

    assert not owned_input.exists()
    assert caller_input.read_text(encoding="utf-8") == "caller-owned"
    assert outside_input.read_text(encoding="utf-8") == "outside"


def test_git_provenance_records_commit_dirty_state_and_status_hash():
    provenance = git_provenance(ROOT)
    assert len(provenance["git_commit"]) == 40
    assert isinstance(provenance["git_dirty"], bool)
    assert len(provenance["git_status_sha256"]) == 64


def test_git_provenance_fails_closed_when_git_is_unavailable(monkeypatch):
    class Failed:
        returncode = 1
        stdout = ""
        stderr = "not a git repository"

    monkeypatch.setattr("benchmark_batch.subprocess.run", lambda *args, **kwargs: Failed())
    with pytest.raises(SystemExit, match="git provenance"):
        git_provenance(ROOT)
