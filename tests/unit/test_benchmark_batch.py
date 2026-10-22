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
    build_fixture_master,
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


def test_a_measurement_that_matched_nothing_is_refused(tmp_path):
    """A throughput number for a run that asserted nothing is not a measurement."""
    master = build_fixture_master(tmp_path / "master")
    gazetteer = geo(tmp_path)
    # Portugal is not issued by the fixture master, so no row can be matched.
    places = [place for place in PLACES if place[5] == "PT"]
    with pytest.raises(SystemExit):
        measure(30, master, gazetteer, tmp_path / "work", 10, "test", places)


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
                   "", "01", "", "", "", "8000000", "", "", "UTC", "2024-01-01"])])
    places = [place for place in PLACES if place[5] in ("JP", "IN")]
    assert street_evidence_violations(gazetteer, places) == []
    monkeypatch.setattr("benchmark_batch.STREET_EN", ("Nanjing Road",))
    assert street_evidence_violations(gazetteer, places)
