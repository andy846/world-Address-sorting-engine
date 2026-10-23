"""Country-only mapping contract; no postal zones or recipient fixtures."""

from dataclasses import FrozenInstanceError
import hashlib
import importlib
from importlib import resources
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


SOURCE_SHA = "41b84a0938c1ebe320514b29c567ceedcf9f9868e99f84f3387bb8899cf2f373"
ROOT = Path(__file__).resolve().parents[2]


def api():
    return importlib.import_module("world_address_engine.data.country_codes")


def document():
    return json.loads(resources.files("world_address_engine.resources")
                      .joinpath("country_codes.json").read_bytes())


def write_document(tmp_path, data):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def importer():
    return runpy.run_path(str(ROOT / "tools" / "import_country_codes.py"))


def test_public_api_and_bundled_catalogue():
    assert importlib.util.find_spec("world_address_engine.data.country_codes") is not None
    module = api()
    entry = module.CountryEntry("US", "United States", "United States")
    assert entry.aliases == ()
    with pytest.raises(FrozenInstanceError):
        entry.code = "GB"
    minimal = module.CountryCatalogue({}, {}, "test", SOURCE_SHA, "0" * 64)
    assert minimal.entries == {}
    cat = module.load_country_codes()
    assert len(cat.entries) == 235
    assert cat.source_sha256 == SOURCE_SHA
    assert cat.profile == "USER_PROVIDED"
    assert cat.version
    assert "CN" in cat.entries and "CNS" not in cat.entries


def test_every_source_row_is_auditable_including_excluded_service():
    cat = api().load_country_codes()
    rows = cat.source_rows
    assert [row.seq for row in rows] == list(range(1, 237))
    assert [sum(row.page == page for row in rows) for page in range(1, 6)] == [57, 56, 57, 57, 9]
    assert rows[44].code == "CN" and rows[44].canonical_code == "CN"
    assert rows[45].code == "CNS" and rows[45].canonical_code == "CN"
    assert rows[45].exclusion_reason == "service_duplicate"
    assert sum(row.exclusion_reason is not None for row in rows) == 1
    assert {row.code for row in rows if row.exclusion_reason is None} == set(cat.entries)
    wrapped = rows[72]
    assert (wrapped.seq, wrapped.page, wrapped.code) == (73, 2, "FK")
    assert wrapped.name_en == "FALKLAND ISLANDS AND THE TERRITORY OF SOUTH GEORGIA AND SOUTH SANDWICH ISLANDS"
    assert wrapped.name_tc == "\u798f\u514b\u862d\u7fa4\u5cf6\u3001\u5357\u55ac\u6cbb\u4e9e\u5730\u5340\u53ca\u5357\u6851\u5a01\u5947\u7fa4\u5cf6"
    assert cat.entries["FK"].name_en == wrapped.name_en


def test_geonames_uses_business_codes_without_invented_territory_matches():
    cat = api().load_country_codes()
    assert {code: cat.geo_to_code[code] for code in ("CN", "US", "ES", "FR", "PT", "NZ", "FM", "SH")} == {
        "CN": "CN", "US": "US", "ES": "ES", "FR": "FR", "PT": "PT", "NZ": "NZ", "FM": "FM", "SH": "SH"}
    assert cat.geo_to_code["TL"] == "TP"
    assert cat.geo_to_code["XK"] == "XO"
    assert cat.entries["XK"].name_en == "CAROLINE ISLANDS"
    assert cat.entries["XO"].name_en == "KOSOVO"
    for code, name in {"XM": "WAKE ISLAND", "XA": "CANARY ISLANDS", "XF": "CORSICA",
                       "XD": "ASCENSION", "XB": "TRISTAN DA CUNHA", "XE": "GAZA AND KHAN YUNIS"}.items():
        assert cat.entries[code].name_en == name
    assert not ({"XA", "XB", "XD", "XE", "XF", "XG", "XH", "XI", "XJ", "XL", "XM", "XO",
                 "TP", "AN", "UM", "PS", "GS", "AC", "TA"} & cat.geo_to_code.keys())
    assert set(cat.geo_to_code.values()) <= cat.entries.keys()


@pytest.mark.parametrize(("code", "aliases"), [
    ("CN", ("China", "Mainland China", "\u4e2d\u570b", "\u4e2d\u570b\u5167\u5730")),
    ("US", ("United States", "USA")), ("GB", ("UK", "Great Britain")),
    ("TP", ("Timor-Leste", "East Timor")), ("XO", ("Kosovo",)),
    ("XA", ("Canary Islands",)), ("XF", ("Corsica",)), ("XM", ("Wake Island",)),
    ("FK", ("Falkland Islands", "South Georgia and South Sandwich Islands")),
    ("KR", ("South Korea", "Republic of Korea")), ("KP", ("North Korea",)),
    ("MO", ("Macao",)), ("MK", ("North Macedonia",)), ("WS", ("Samoa",)),
    ("LC", ("Saint Lucia", "St Lucia")), ("CC", ("Cocos Islands", "Keeling Islands")),
])
def test_full_and_short_aliases_are_preserved_without_consumer_normalization(code, aliases):
    cat = api().load_country_codes()
    entry = cat.entries[code]
    assert isinstance(entry.aliases, tuple)
    assert set(aliases) <= set(entry.aliases)
    assert {entry.name_en, entry.name_tc} <= set(entry.aliases)


def test_fingerprint_hashes_exact_bytes_and_explicit_path_is_supported(tmp_path):
    data = document()
    path = write_document(tmp_path, data)
    first = api().load_country_codes(path)
    assert first.fingerprint == hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(path.read_bytes() + b"\n")
    second = api().load_country_codes(path)
    assert second.entries == first.entries
    assert second.fingerprint != first.fingerprint
    bundled = resources.files("world_address_engine.resources").joinpath("country_codes.json").read_bytes()
    assert api().load_country_codes().fingerprint == hashlib.sha256(bundled).hexdigest()


@pytest.mark.parametrize("case", [
    "root", "schema", "profile", "version", "hash", "page_count", "row_count", "entries_type",
    "missing_field", "duplicate_code", "invalid_code", "cns", "empty_name", "alias_string",
    "alias_number", "duplicate_alias", "missing_entry", "row_gap", "row_duplicate", "row_page",
    "row_name", "row_code", "row_exclusion", "row_canonical", "geo_type", "geo_unknown",
    "geo_lowercase", "geo_parent", "geo_kosovo", "geo_timor", "geo_invented", "unknown_field",
])
def test_malformed_catalogues_are_rejected(tmp_path, case):
    data = document()
    if case == "root":
        data = []
    elif case == "schema":
        data["schema_version"] = True
    elif case == "profile":
        data["profile"] = "APPROVED"
    elif case == "version":
        data["version"] = ""
    elif case == "hash":
        data["source"]["sha256"] = "not-a-sha256"
    elif case in ("page_count", "row_count"):
        data["source"][case] = 1
    elif case == "entries_type":
        data["entries"] = {}
    elif case == "missing_field":
        del data["entries"][0]["name_tc"]
    elif case == "duplicate_code":
        data["entries"][1]["code"] = data["entries"][0]["code"]
    elif case in ("invalid_code", "cns"):
        data["entries"][0]["code"] = "a1" if case == "invalid_code" else "CNS"
    elif case == "empty_name":
        data["entries"][0]["name_en"] = " "
    elif case == "alias_string":
        data["entries"][0]["aliases"] = "Afghanistan"
    elif case == "alias_number":
        data["entries"][0]["aliases"] = [12]
    elif case == "duplicate_alias":
        data["entries"][0]["aliases"] *= 2
    elif case == "missing_entry":
        data["entries"].pop()
    elif case == "row_gap":
        data["source_rows"].pop(72)
    elif case == "row_duplicate":
        data["source_rows"][1]["seq"] = 1
    elif case == "row_page":
        data["source_rows"][72]["page"] = 1
    elif case == "row_name":
        data["source_rows"][72]["name_en"] = "FALKLAND ISLANDS"
    elif case == "row_code":
        data["source_rows"][45]["code"] = "CN"
    elif case == "row_exclusion":
        data["source_rows"][45]["exclusion_reason"] = None
    elif case == "row_canonical":
        data["source_rows"][45]["canonical_code"] = "US"
    elif case == "geo_type":
        data["geo_to_code"] = []
    elif case == "geo_unknown":
        data["geo_to_code"]["US"] = "ZZ"
    elif case == "geo_lowercase":
        data["geo_to_code"]["us"] = "US"
    elif case == "geo_parent":
        data["geo_to_code"]["ES"] = "XA"
    elif case == "geo_kosovo":
        data["geo_to_code"]["XK"] = "XK"
    elif case == "geo_timor":
        data["geo_to_code"]["TL"] = "TL"
    elif case == "geo_invented":
        data["geo_to_code"]["UM"] = "XM"
    elif case == "unknown_field":
        data["entries"][0]["zone"] = "ignored"
    with pytest.raises(ValueError):
        api().load_country_codes(write_document(tmp_path, data))


@pytest.mark.parametrize("raw", [b"not json", b"\xff", b'{"schema_version":1,"schema_version":1}'])
def test_invalid_json_and_duplicate_object_keys_are_rejected(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        api().load_country_codes(path)


@pytest.mark.parametrize("case", ["renamed", "recoded", "missing_china"])
def test_audit_transcript_cannot_be_rewritten_along_with_canonical_entries(tmp_path, case):
    data = document()
    if case == "renamed":
        data["entries"][0]["name_en"] = "Invented Country"
        data["entries"][0]["aliases"].append("Invented Country")
        data["source_rows"][0]["name_en"] = "Invented Country"
    else:
        index = 0 if case == "recoded" else 44
        old_code = data["entries"][index]["code"]
        data["entries"][index]["code"] = "ZZ"
        data["source_rows"][index]["code"] = "ZZ"
        data["source_rows"][index]["canonical_code"] = "ZZ"
        del data["geo_to_code"][old_code]
        data["geo_to_code"]["ZZ"] = "ZZ"
    with pytest.raises(ValueError):
        api().load_country_codes(write_document(tmp_path, data))


def test_runtime_loads_in_isolated_python_without_pdf_dependencies():
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
        "from world_address_engine.data.country_codes import load_country_codes; "
        "assert len(load_country_codes().entries) == 235; "
        "assert 'pypdf' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_importer_parses_wrapped_names_with_page_specific_columns():
    def page(en_start, code_start, seq, tc, en, code, continuation=None):
        header = "SEQ Country NameC".ljust(en_start) + "Country NameE"
        header = header.ljust(code_start) + "Country   Zone   Novsn Zone"
        row = f"{seq:<4}{tc}".ljust(en_start) + en
        row = row.ljust(code_start) + code + "   arbitrary ignored values"
        lines = [header, row]
        if continuation:
            lines.append(("    " + continuation[0]).ljust(en_start) + continuation[1])
        return "\n".join(lines)
    rows = importer()["parse_pages"]([
        page(33, 79, 73, "\u798f\u514b\u862d\u7fa4\u5cf6\u3001\u5357\u55ac\u6cbb\u4e9e\u5730\u5340",
             "FALKLAND ISLANDS AND THE TERRITORY OF SOUTH", "FK",
             ("\u53ca\u5357\u6851\u5a01\u5947\u7fa4\u5cf6", "GEORGIA AND SOUTH SANDWICH ISLANDS")),
        page(34, 80, 74, "\u6cd5\u7f85\u7fa4\u5cf6", "FAROE ISLANDS", "FO"),
    ])
    assert rows[0]["name_en"] == "FALKLAND ISLANDS AND THE TERRITORY OF SOUTH GEORGIA AND SOUTH SANDWICH ISLANDS"
    assert rows[0]["name_tc"] == "\u798f\u514b\u862d\u7fa4\u5cf6\u3001\u5357\u55ac\u6cbb\u4e9e\u5730\u5340\u53ca\u5357\u6851\u5a01\u5947\u7fa4\u5cf6"
    assert (rows[0]["seq"], rows[0]["page"], rows[0]["code"]) == (73, 1, "FK")
    assert (rows[1]["seq"], rows[1]["page"], rows[1]["code"]) == (74, 2, "FO")
    assert all("zone" not in key.lower() for row in rows for key in row)


def test_importer_refuses_wrong_pdf_hash_without_writing(tmp_path):
    pdf = tmp_path / "wrong.pdf"
    pdf.write_bytes(b"not the source")
    output = tmp_path / "country_codes.json"
    output.write_bytes(b"existing")
    with pytest.raises(ValueError, match="SHA256"):
        importer()["import_country_codes"](pdf, output)
    assert output.read_bytes() == b"existing"


def test_importer_rejects_missing_table_headers():
    with pytest.raises(ValueError, match="header"):
        importer()["parse_pages"](["unrecognized table"])


def test_importer_rebuilds_complete_catalogue_and_rejects_missing_rows():
    data = document()
    pages = []
    for page_number in range(1, 6):
        en_start, code_start = (33, 79) if page_number < 4 else (34, 80)
        header = "SEQ Country NameC".ljust(en_start) + "Country NameE"
        lines = [header.ljust(code_start) + "Country   Zone   Novsn Zone"]
        for row in data["source_rows"]:
            if row["page"] == page_number:
                line = f"{row['seq']:<4}{row['name_tc']}".ljust(en_start) + row["name_en"]
                # A single long row must wrap within the actual source columns.
                if row["seq"] == 73:
                    line = f"{row['seq']:<4}{row['name_tc']}".ljust(en_start) + "FALKLAND ISLANDS AND THE TERRITORY OF SOUTH"
                    lines.append(line.ljust(code_start) + row["code"])
                    lines.append(" ".ljust(en_start) + "GEORGIA AND SOUTH SANDWICH ISLANDS")
                else:
                    lines.append(line.ljust(code_start) + row["code"])
        pages.append("\n".join(lines))
    build = importer()["build_catalogue"]
    assert build(pages) == data
    pages[4] = "\n".join(pages[4].splitlines()[:-1])
    with pytest.raises(ValueError):
        build(pages)
