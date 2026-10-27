"""Literal zone mappings, complete PDF reconciliation and runtime contracts."""

from dataclasses import FrozenInstanceError, asdict
import hashlib
import importlib
from importlib import resources
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest

from world_address_engine.data.country_codes import load_country_codes


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA = "41b84a0938c1ebe320514b29c567ceedcf9f9868e99f84f3387bb8899cf2f373"


def api():
    assert importlib.util.find_spec("world_address_engine.data.zone_mappings") is not None, "zone mapping API is missing"
    return importlib.import_module("world_address_engine.data.zone_mappings")


def document():
    return json.loads(resources.files("world_address_engine.resources")
                      .joinpath("country_zone_mappings.json").read_bytes())


def write_document(tmp_path, data):
    path = tmp_path / "zones.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def importer():
    path = ROOT / "tools/import_country_zones.py"
    assert path.exists(), "build-time zone importer is missing"
    return runpy.run_path(str(path))


def source_pages():
    """Public reviewed transcript in PDF-like columns, with centered Zone header."""
    pages = []
    for page in range(1, 6):
        en_start, code_start = (33, 79) if page < 4 else (34, 80)
        header = "SEQ Country NameC".ljust(en_start) + "Country NameE"
        lines = [header.ljust(code_start) + "Country         Zone       Novsn Zone", " ".ljust(code_start) + "Code                          Code"]
        for row in document()["source_rows"]:
            if row["page"] != page:
                continue
            en = row["name_en"]
            if row["seq"] == 73:
                en = "FALKLAND ISLANDS AND THE TERRITORY OF SOUTH"
            line = f"{row['seq']:<4}{row['name_tc']}".ljust(en_start) + en
            # Zone values start LEFT of the centered Zone header.
            lines.append(line.ljust(code_start) + f"{row['code']:<13}{row['zone_code']}       {row['novsn_zone_code']}")
            if row["seq"] == 73:
                lines.append(" ".ljust(en_start) + "GEORGIA AND SOUTH SANDWICH ISLANDS")
        pages.append("\n".join(lines))
    return pages


def test_public_api_all_235_business_codes_and_frozen_records():
    module = api()
    entry = module.ZoneEntry("CN", "CN - Airmail", "F")
    with pytest.raises(FrozenInstanceError):
        entry.zone_code = "wrong"
    catalogue = module.ZoneCatalogue({"CN": entry}, "test", SOURCE_SHA, "0" * 64)
    assert module.zone_values("CN", catalogue) == ("CN - Airmail", "F")
    with pytest.raises(FrozenInstanceError):
        catalogue.version = "wrong"
    cat = module.load_zone_mappings()
    assert set(cat.entries) == set(load_country_codes().entries)
    assert len(cat.entries) == 235
    assert cat.source_sha256 == SOURCE_SHA and cat.version
    for code, value in cat.entries.items():
        assert value.country_code == code
        assert module.zone_values(code, cat) == (value.zone_code, value.novsn_zone_code)
        assert all(isinstance(text, str) and text for text in module.zone_values(code, cat))


@pytest.mark.parametrize(("code", "expected"), [
    ("CN", ("CN - Airmail", "F")), ("HK", ("LOCAL", "A")),
    ("MO", ("Macau - Surface", "M")), ("TW", ("Taiwan", "F")),
    ("TP", ("1", "C")), ("XO", ("3", "E")), ("XK", ("2", "D")),
    (None, ("", "")), ("", ("", "")),
])
def test_literal_values_and_empty_code(code, expected):
    assert api().zone_values(code) == expected


@pytest.mark.parametrize("code", ["ZZ", "CNS", "TL", "cn", " ", 0, [], {}])
def test_unknown_nonempty_codes_are_errors(code):
    with pytest.raises(ValueError):
        api().zone_values(code)


def test_missing_mapping_in_supplied_catalogue_is_an_error():
    module = api()
    cat = module.ZoneCatalogue({}, "test", SOURCE_SHA, "0" * 64)
    assert module.zone_values(None, cat) == ("", "")
    with pytest.raises(ValueError):
        module.zone_values("CN", cat)


def test_catalogue_entries_are_readonly_and_detached_from_constructor_input():
    module = api()
    original = {"CN": module.ZoneEntry("CN", "CN - Airmail", "F")}
    cat = module.ZoneCatalogue(original, "test", SOURCE_SHA, "0" * 64)
    with pytest.raises(TypeError):
        cat.entries["CN"] = module.ZoneEntry("CN", "wrong", "B")
    original.clear()
    assert module.zone_values("CN", cat) == ("CN - Airmail", "F")


def test_default_resource_is_freshly_read_and_revalidated(tmp_path, monkeypatch):
    module = api()
    data = document()
    resource = tmp_path / "country_zone_mappings.json"
    resource.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(module, "resources", SimpleNamespace(files=lambda _: tmp_path))
    first = module.load_zone_mappings()
    data["version"] += "-recheck"
    resource.write_text(json.dumps(data), encoding="utf-8")
    second = module.load_zone_mappings()
    assert second.version == data["version"]
    assert second.fingerprint != first.fingerprint
    data["entries"][44]["zone_code"] = "Airmail"
    resource.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        module.load_zone_mappings()


def test_audit_keeps_all_source_rows_and_excludes_only_cns():
    rows = document()["source_rows"]
    assert len(rows) == 236
    for row, country in zip(rows, load_country_codes().source_rows, strict=True):
        assert {key: row[key] for key in asdict(country)} == asdict(country)
    assert (rows[44]["code"], rows[44]["zone_code"], rows[44]["novsn_zone_code"]) == ("CN", "CN - Airmail", "F")
    assert (rows[45]["code"], rows[45]["zone_code"], rows[45]["novsn_zone_code"]) == ("CNS", "CN - Surface", "B")


def test_exact_byte_fingerprint_and_explicit_path(tmp_path):
    path = write_document(tmp_path, document())
    cat = api().load_zone_mappings(path)
    assert cat.fingerprint == hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(path.read_bytes() + b"\n")
    other = api().load_zone_mappings(path)
    assert cat.entries == other.entries and cat.fingerprint != other.fingerprint
    raw = resources.files("world_address_engine.resources").joinpath("country_zone_mappings.json").read_bytes()
    assert api().load_zone_mappings().fingerprint == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("case", [
    "root", "schema", "profile", "version", "source_hash", "filename", "page_count", "row_count",
    "extra", "entries_type", "missing_entry", "duplicate", "code", "cns", "entry_field",
    "empty_zone", "numeric_zone", "blank_novsn", "trim", "truncated", "row_missing", "row_duplicate",
    "row_page", "row_code", "row_name", "row_exclusion", "row_canonical", "rewrite_both", "rewrite_cns",
])
def test_malformed_and_rewritten_transcripts_rejected(tmp_path, case):
    data = document()
    if case == "root":
        data = []
    elif case == "schema":
        data["schema_version"] = True
    elif case == "profile":
        data["profile"] = "APPROVED"
    elif case == "version":
        data["version"] = ""
    elif case in {"source_hash", "filename", "page_count", "row_count"}:
        key = "sha256" if case == "source_hash" else case
        data["source"][key] = "wrong" if key in {"sha256", "filename"} else True
    elif case == "extra":
        data["unreviewed"] = True
    elif case == "entries_type":
        data["entries"] = {}
    elif case == "missing_entry":
        data["entries"].pop()
    elif case == "duplicate":
        data["entries"][1] = data["entries"][0]
    elif case in {"code", "cns"}:
        data["entries"][0]["country_code"] = "a1" if case == "code" else "CNS"
    elif case == "entry_field":
        del data["entries"][0]["novsn_zone_code"]
    elif case in {"empty_zone", "numeric_zone", "blank_novsn", "trim", "truncated"}:
        key = "novsn_zone_code" if case == "blank_novsn" else "zone_code"
        data["entries"][44][key] = {"empty_zone": "", "numeric_zone": 1, "blank_novsn": " ", "trim": " 1", "truncated": "Airmail"}[case]
    elif case == "row_missing":
        data["source_rows"].pop()
    elif case == "row_duplicate":
        data["source_rows"][1] = data["source_rows"][0]
    elif case.startswith("row_"):
        key = {"row_page": "page", "row_code": "code", "row_name": "name_en", "row_exclusion": "exclusion_reason", "row_canonical": "canonical_code"}[case]
        data["source_rows"][45][key] = "wrong"
    elif case == "rewrite_both":
        data["entries"][44]["zone_code"] = "Airmail"
        data["source_rows"][44]["zone_code"] = "Airmail"
    elif case == "rewrite_cns":
        data["source_rows"][45]["zone_code"] = "Surface"
    with pytest.raises(ValueError):
        api().load_zone_mappings(write_document(tmp_path, data))


@pytest.mark.parametrize("raw", [b"not json", b"\xff", b'{"schema_version":1,"schema_version":1}'])
def test_invalid_utf8_json_and_duplicate_keys(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        api().load_zone_mappings(path)


def test_runtime_and_importer_load_without_pdf_dependency():
    code = (f"import sys, runpy; sys.path.insert(0, {str(ROOT / 'src')!r}); "
            "from world_address_engine.data.zone_mappings import load_zone_mappings; "
            "assert len(load_zone_mappings().entries) == 235; "
            f"runpy.run_path({str(ROOT / 'tools/import_country_zones.py')!r}); "
            "assert 'pypdf' not in sys.modules")
    result = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_importer_rebuilds_all_rows_without_centered_header_truncation():
    assert importer()["build_catalogue"](source_pages()) == document()


@pytest.mark.parametrize("case", ["header", "missing", "order", "page", "code", "name", "tail", "truncated", "novsn"])
def test_importer_rejects_incomplete_or_changed_source(case):
    pages = source_pages()
    if case == "header":
        pages[0] = "no table"
    elif case == "missing":
        pages[-1] = "\n".join(pages[-1].splitlines()[:-1])
    elif case == "order":
        lines = pages[0].splitlines()
        lines[2], lines[3] = lines[3], lines[2]
        pages[0] = "\n".join(lines)
    elif case == "page":
        pages[0], pages[1] = pages[1], pages[0]
    elif case == "code":
        pages[0] = pages[0].replace("CNS          ", "CN           ")
    elif case == "name":
        pages[0] = pages[0].replace("AFGHANISTAN", "MADEUPLAND ")
    elif case == "tail":
        pages[0] = pages[0].replace("CN - Airmail       F", "CN - Airmail")
    elif case == "truncated":
        pages[0] = pages[0].replace("CN - Airmail", "Airmail")
    elif case == "novsn":
        pages[0] = pages[0].replace("CN - Airmail       F", "CN - Airmail       B")
    with pytest.raises(ValueError):
        importer()["build_catalogue"](pages)


def test_importer_wrong_pdf_hash_never_writes_output(tmp_path):
    pdf = tmp_path / "wrong.pdf"
    pdf.write_bytes(b"not the pinned source")
    output = tmp_path / "zones.json"
    output.write_bytes(b"preserve existing")
    with pytest.raises(ValueError, match="SHA256"):
        importer()["import_country_zones"](pdf, output)
    assert output.read_bytes() == b"preserve existing"
