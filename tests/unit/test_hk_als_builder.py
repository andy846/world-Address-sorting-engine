"""Synthetic-only streaming builder contracts; no customer inputs."""
import copy
from contextlib import closing
import hashlib
import importlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import zipfile

import pytest


def feature(number="12"):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [114.1, 22.3]},
            "properties": {"Address": {"PremisesAddress": {
                "BuildingCsuInformation": {"CsuId": "1234567890T20200101"},
                "ChiPremisesAddress": {"Region": "九龍", "ChiDistrict": "觀塘區",
                    "BuildingName": "測試大廈", "ChiStreet": {"StreetName": "測試道", "BuildingNoFrom": number}},
                "EngPremisesAddress": {"Region": "KLN", "EngDistrict": "KWUN TONG DISTRICT",
                    "BuildingName": "TEST TOWER", "EngStreet": {"StreetName": "TEST ROAD", "BuildingNoFrom": number}}
            }}}}


def schema_fixture():
    text = {"type": "string"}
    premises = {}
    for prefix, district, regions in [("Chi", "ChiDistrict", ["香港", "九龍", "新界"]),
                                       ("Eng", "EngDistrict", ["HK", "KLN", "NT"])]:
        premises[prefix + "PremisesAddress"] = {"type": "object", "required": ["Region", district],
            "properties": {"Region": {"enum": regions}, district: text, "BuildingName": text,
                prefix + "3dAddress": {"type": "array", "items": {"type": "object",
                    "properties": {"UnitNo": text}}}}}
    premises["BuildingCsuInformation"] = {"type": "object", "required": ["CsuId"],
                                        "properties": {"CsuId": {"type": "string", "minLength": 1}}}
    item = {"type": "object", "required": ["type", "geometry", "properties"], "properties": {
        "type": {"const": "Feature"}, "geometry": {"type": "object", "required": ["coordinates"],
            "properties": {"coordinates": {"type": "array", "minItems": 2, "items": {"type": "number"}}}},
        "properties": {"type": "object", "required": ["Address"], "properties": {"Address": {
            "type": "object", "required": ["PremisesAddress"], "properties": {"PremisesAddress": {
                "type": "object", "required": list(premises), "properties": premises}}}}}}}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
            "required": ["type", "features"], "properties": {"type": {"const": "FeatureCollection"},
            "features": {"type": "array", "items": item}}}


def inputs(tmp_path, records=None, *, envelope=None, member="addresses.geojson", schema=None):
    archive = tmp_path / "source.zip"
    obj = {"type": "FeatureCollection", "features": records if records is not None else [feature()]}
    obj.update(envelope or {})
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr(member, json.dumps(obj, ensure_ascii=False))
    if "\\" in member:
        # Windows ZipInfo normalizes separators on write; construct hostile bytes.
        archive.write_bytes(archive.read_bytes().replace(member.replace("\\", "/").encode(), member.encode()))
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema or schema_fixture()), encoding="utf-8")
    return archive, path


def build(tmp_path, records=None, **kwargs):
    archive, schema = inputs(tmp_path, records, **kwargs)
    module = importlib.import_module("world_address_engine.data.hk_als_builder")
    return module.build_als_pack(archive, schema, tmp_path / "pack", source_date="2026-10-23", pack_version="test")


def test_streamed_bilingual_multiaddress_and_projected_duplicate(tmp_path):
    three = copy.deepcopy(feature())
    for lang in ("Chi", "Eng"):
        three["properties"]["Address"]["PremisesAddress"][lang + "PremisesAddress"][lang + "3dAddress"] = [{"UnitNo": "NEVER INDEX UNIT"}]
    result = build(tmp_path, [feature(), three, feature("14")])
    assert result["record_count"] == 2
    assert result["building_count"] == 1
    audit = json.loads((tmp_path / "pack/audit.json").read_text())
    assert (audit["feature_count"], audit["valid_count"], audit["duplicate_count"], audit["invalid_count"]) == (3, 3, 1, 0)
    assert audit["three_d_item_count"] == 2
    with closing(sqlite3.connect(tmp_path / "pack/pack.db")) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        aliases = db.execute("SELECT language,name,derived FROM hk_aliases").fetchall()
        assert ("en", "TEST TOWER", 0) in aliases
        assert ("zh-Hant", "測試大廈", 0) in aliases
        assert ("zh-Hans", "测试大厦", 1) in aliases
        assert not any("UNIT" in row[1] for row in aliases)
        assert db.execute("SELECT number_from FROM hk_addresses ORDER BY number_from").fetchall() == [("12",), ("14",)]
    assert result["db_sha256"] == hashlib.sha256((tmp_path / "pack/pack.db").read_bytes()).hexdigest()
    assert result["conversion_version"] == "opencc-python-reimplemented==0.1.7"


@pytest.mark.parametrize("mutation", ["foreign", "missing", "3d", "coordinates"])
def test_invalid_features_are_audited_and_block_final_db(tmp_path, mutation):
    bad = feature()
    p = bad["properties"]["Address"]["PremisesAddress"]
    if mutation == "foreign":
        p["EngPremisesAddress"]["Region"] = "JP"
    elif mutation == "missing":
        del p["BuildingCsuInformation"]
    elif mutation == "3d":
        p["EngPremisesAddress"]["Eng3dAddress"] = [{"UnitNo": 123}]
    else:
        bad["geometry"]["coordinates"] = [0, 0]
    with pytest.raises(ValueError):
        build(tmp_path, [feature(), bad])
    audit = json.loads((tmp_path / "pack/audit.json").read_text())
    assert audit["invalid_count"] == 1
    assert audit["feature_count"] == 2
    if mutation == "3d":
        assert audit["three_d_item_count"] == 1
    assert not (tmp_path / "pack/pack.db").exists()
    assert not (tmp_path / "pack/manifest.json").exists()


def test_optional_blanks_and_number_conflicts(tmp_path):
    obj = feature()
    p = obj["properties"]["Address"]["PremisesAddress"]
    p["EngPremisesAddress"]["BuildingName"] = ""
    p["ChiPremisesAddress"]["ChiStreet"]["BuildingNoFrom"] = "99"
    build(tmp_path, [obj])
    with closing(sqlite3.connect(tmp_path / "pack/pack.db")) as db:
        assert db.execute("SELECT number_from,number_conflict FROM hk_addresses").fetchone() == ("12", 1)
        assert db.execute("SELECT count(*) FROM hk_aliases WHERE name=''").fetchone()[0] == 0


@pytest.mark.parametrize("envelope", [{"type": "Wrong"}, {"features": {}}, {"features": None}])
def test_bad_envelope_rejected(tmp_path, envelope):
    with pytest.raises(ValueError):
        build(tmp_path, envelope=envelope)
    assert not (tmp_path / "pack/pack.db").exists()


def test_existing_output_is_never_overwritten(tmp_path):
    (tmp_path / "pack").mkdir()
    marker = tmp_path / "pack/keep"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        build(tmp_path)
    assert marker.read_text() == "preserve"


@pytest.mark.parametrize("member", ["../escape.geojson", "/absolute.geojson", "a\\b.geojson"])
def test_unsafe_zip_members_rejected(tmp_path, member):
    with pytest.raises(ValueError):
        build(tmp_path, member=member)
    assert not (tmp_path / "escape.geojson").exists()


def test_crc_damage_refuses_pack(tmp_path):
    archive, schema = inputs(tmp_path)
    data = archive.read_bytes().replace(b'TEST TOWER', b'BEST TOWER', 1)
    archive.write_bytes(data)
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        mod.build_als_pack(archive, schema, tmp_path / "pack", source_date="2026-10-23", pack_version="test")
    assert not (tmp_path / "pack/pack.db").exists()


def test_source_change_during_progress_blocks_publication(tmp_path):
    archive, schema = inputs(tmp_path)
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    def mutate(event):
        if event["stage"] == "member_complete":
            schema.write_text(schema.read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        mod.build_als_pack(archive, schema, tmp_path / "pack", source_date="2026-10-23", pack_version="test", on_progress=mutate)
    assert not (tmp_path / "pack/pack.db").exists()


def test_bad_schema_refuses_pack(tmp_path):
    with pytest.raises(ValueError):
        build(tmp_path, schema={"type": 22})
    assert not (tmp_path / "pack/pack.db").exists()


def test_schema_local_references_validate_raw_features(tmp_path):
    spec = schema_fixture()
    spec["$defs"] = {"feature": spec["properties"]["features"]["items"]}
    spec["properties"]["features"]["items"] = {"$ref": "#/$defs/feature"}
    assert build(tmp_path, schema=spec)["record_count"] == 1


def test_number_range_never_combines_languages(tmp_path):
    obj = feature()
    p = obj["properties"]["Address"]["PremisesAddress"]
    p["ChiPremisesAddress"]["ChiStreet"]["BuildingNoTo"] = "18"
    build(tmp_path, [obj])
    with closing(sqlite3.connect(tmp_path / "pack/pack.db")) as db:
        assert db.execute("SELECT number_from,number_to,number_conflict FROM hk_addresses").fetchone() == ("12", None, 0)


def test_failure_audit_identifies_schema_paths_without_values(tmp_path):
    obj = feature()
    obj["properties"]["Address"]["PremisesAddress"]["BuildingCsuInformation"]["CsuId"] = 123
    with pytest.raises(ValueError):
        build(tmp_path, [obj])
    audit = json.loads((tmp_path / "pack/audit.json").read_text())
    assert audit["schema_error_counts"] == [{"path": "properties/Address/PremisesAddress/BuildingCsuInformation/CsuId", "validator": "type", "count": 1}]


def test_repeated_builds_have_deterministic_database_and_ids(tmp_path):
    first = build(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    assert first["db_sha256"] == build(other)["db_sha256"]


def test_all_members_and_trailing_json_are_consumed(tmp_path):
    archive, schema = inputs(tmp_path)
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr("last.geojson", json.dumps({"type": "FeatureCollection", "features": [feature("18")]}) + "BROKEN")
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    with pytest.raises(ValueError):
        mod.build_als_pack(archive, schema, tmp_path / "pack", source_date="2026-10-23", pack_version="test")
    assert not (tmp_path / "pack/pack.db").exists()


def test_builder_import_does_not_load_build_dependencies():
    src = Path(__file__).resolve().parents[2] / "src"
    result = subprocess.run([sys.executable, "-I", "-c",
        f"import sys; sys.path.insert(0, {str(src)!r}); import world_address_engine.data.hk_als_builder; "
        "assert 'ijson' not in sys.modules; assert 'jsonschema' not in sys.modules"], capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_cli_builds_verified_pack_and_refuses_rerun(tmp_path):
    archive, schema = inputs(tmp_path)
    tool = Path(__file__).resolve().parents[2] / "tools/build_hk_als_pack.py"
    command = [sys.executable, str(tool), str(archive), str(schema), str(tmp_path / "pack"),
               "--source-date", "2026-10-23", "--pack-version", "test"]
    completed = subprocess.run(command, capture_output=True)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    from world_address_engine.data.hk_regional import verify_hk_pack
    assert verify_hk_pack(tmp_path / "pack/pack.db")["record_count"] == 1
    checksum = hashlib.sha256((tmp_path / "pack/pack.db").read_bytes()).hexdigest()
    assert subprocess.run(command, capture_output=True).returncode == 1
    assert hashlib.sha256((tmp_path / "pack/pack.db").read_bytes()).hexdigest() == checksum


def test_missing_required_counts_are_per_feature_not_error_multiples(tmp_path):
    obj = feature()
    obj["properties"]["Address"]["PremisesAddress"]["ChiPremisesAddress"] = {}
    with pytest.raises(ValueError):
        build(tmp_path, [obj])
    audit = json.loads((tmp_path / "pack/audit.json").read_text())
    assert {(entry["field"], entry["count"]) for entry in audit["schema_required_missing_counts"]} == {("Region", 1), ("ChiDistrict", 1)}


def test_publication_failure_removes_unpublished_final_database(tmp_path, monkeypatch):
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    write = mod._json_write
    def fail_manifest(path, value):
        if path.name == "manifest.json":
            raise OSError("Simulated publication failure")
        write(path, value)
    monkeypatch.setattr(mod, "_json_write", fail_manifest)
    with pytest.raises(OSError):
        build(tmp_path)
    assert not (tmp_path / "pack/pack.db").exists()
    assert json.loads((tmp_path / "pack/audit.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("extra,empty", [("features.hidden", False), ("features.item", True)])
def test_dotted_root_keys_cannot_spoof_stream_structure(tmp_path, extra, empty):
    spec = schema_fixture()
    spec["additionalProperties"] = False
    spec["properties"]["features"]["minItems"] = 1
    with pytest.raises(ValueError):
        build(tmp_path, [] if empty else [feature()], schema=spec, envelope={extra: feature()})
    assert not (tmp_path / "pack/pack.db").exists()


@pytest.mark.parametrize("constraint", ["not", "allOf", "if", "dependentSchemas"])
def test_root_cross_feature_constraints_fail_closed(tmp_path, constraint):
    spec = schema_fixture()
    condition = {"properties": {"features": {"minItems": 1}}, "required": ["features"]}
    spec[constraint] = [condition] if constraint == "allOf" else ({"type": condition} if constraint == "dependentSchemas" else condition)
    with pytest.raises(ValueError, match="Unsupported"):
        build(tmp_path, schema=spec)


def test_external_schema_reference_never_resolves_unhashed_bytes(tmp_path):
    external = tmp_path / "external.json"
    external.write_text(json.dumps(schema_fixture()["properties"]["features"]["items"]))
    spec = schema_fixture()
    spec["properties"]["features"]["items"] = {"$ref": external.as_uri()}
    with pytest.raises(ValueError, match="reference"):
        build(tmp_path, schema=spec)
    assert not (tmp_path / "pack/pack.db").exists()


def test_directory_payload_crc_cannot_be_ignored(tmp_path):
    archive, schema = inputs(tmp_path)
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr("extra/", "DIRECTORY-PAYLOAD")
    archive.write_bytes(archive.read_bytes().replace(b"DIRECTORY-PAYLOAD", b"CORRUPTED-PAYLOAD"))
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        mod.build_als_pack(archive, schema, tmp_path / "pack", source_date="2026-10-23", pack_version="test")
    assert not (tmp_path / "pack/pack.db").exists()


def test_empty_directory_crc_is_still_verified(tmp_path):
    archive, schema = inputs(tmp_path)
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr("empty/", b"")
    data = bytearray(archive.read_bytes())
    offset = data.index(b"PK\x01\x02")
    while data[offset + 46:offset + 52] != b"empty/":
        offset = data.index(b"PK\x01\x02", offset + 4)
    data[offset + 16:offset + 20] = b"BAD!"
    archive.write_bytes(data)
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    with pytest.raises(zipfile.BadZipFile):
        mod.build_als_pack(archive, schema, tmp_path / "pack", source_date="2026-10-23", pack_version="test")
    assert not (tmp_path / "pack/pack.db").exists()


@pytest.mark.parametrize("publication_point", ["manifest", "rename", "directory"])
def test_interrupted_publication_cleans_final_pack_and_marks_audit_failed(tmp_path, monkeypatch, publication_point):
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    if publication_point == "manifest":
        write = mod._json_write
        def interrupt(path, value):
            if path.name == "manifest.json":
                raise KeyboardInterrupt("Synthetic interruption")
            write(path, value)
        monkeypatch.setattr(mod, "_json_write", interrupt)
    else:
        rename = Path.rename
        interrupted = False
        def interrupt(path, target):
            nonlocal interrupted
            result = rename(path, target)
            is_point = path.name == "pack.db.building" if publication_point == "rename" else Path(target) == tmp_path / "pack"
            if is_point and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("Synthetic interruption after rename")
            return result
        monkeypatch.setattr(Path, "rename", interrupt)
    with pytest.raises(KeyboardInterrupt):
        build(tmp_path)
    assert not (tmp_path / "pack/pack.db").exists()
    assert not (tmp_path / "pack/manifest.json").exists()
    assert json.loads((tmp_path / "pack/audit.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("changed", ["source.zip", "schema.json"])
def test_late_source_change_during_publication_refuses_pack(tmp_path, monkeypatch, changed):
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    write = mod._json_write
    def mutate(path, value):
        write(path, value)
        if path.name == "manifest.json":
            source = tmp_path / changed
            source.write_bytes(source.read_bytes() + b" ")
    monkeypatch.setattr(mod, "_json_write", mutate)
    with pytest.raises(ValueError, match="changed"):
        build(tmp_path)
    assert not (tmp_path / "pack/pack.db").exists()


@pytest.mark.parametrize("point", ["database_hash", "complete_audit"])
def test_final_checks_cover_entire_publication_window(tmp_path, monkeypatch, point):
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    source = tmp_path / "source.zip"
    if point == "database_hash":
        sha = mod._sha
        def mutate(path):
            result = sha(path)
            if Path(path).name == "pack.db.building":
                source.write_bytes(source.read_bytes() + b" ")
            return result
        monkeypatch.setattr(mod, "_sha", mutate)
    else:
        write = mod._json_write
        def mutate(path, value):
            write(path, value)
            if path.name == "audit.json" and value["status"] == "complete":
                source.write_bytes(source.read_bytes() + b" ")
        monkeypatch.setattr(mod, "_json_write", mutate)
    with pytest.raises(ValueError, match="changed"):
        build(tmp_path)
    assert not (tmp_path / "pack/pack.db").exists()
    assert json.loads((tmp_path / "pack/audit.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("chinese,english,want", [("十二", "12", 0), ("二十一", "21", 0), ("一二", "12", 0), ("十三", "12", 1)])
def test_equivalent_chinese_house_numbers_are_not_conflicts(tmp_path, chinese, english, want):
    obj = feature(english)
    obj["properties"]["Address"]["PremisesAddress"]["ChiPremisesAddress"]["ChiStreet"]["BuildingNoFrom"] = chinese
    build(tmp_path, [obj])
    with closing(sqlite3.connect(tmp_path / "pack/pack.db")) as db:
        assert db.execute("SELECT number_conflict FROM hk_addresses").fetchone()[0] == want


def test_installer_cannot_accept_output_before_atomic_directory_commit(tmp_path, monkeypatch):
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    from world_address_engine.data.hk_regional import verify_hk_pack
    write = mod._json_write
    observations = []
    def observe(path, value):
        write(path, value)
        if path.name == "manifest.json" or path.name == "audit.json" and value["status"] == "complete":
            try:
                verify_hk_pack(tmp_path / "pack/pack.db")
            except ValueError:
                observations.append(False)
            else:
                observations.append(True)
    monkeypatch.setattr(mod, "_json_write", observe)
    result = build(tmp_path)
    assert observations and not any(observations)
    assert verify_hk_pack(tmp_path / "pack/pack.db") == result


def test_prepublish_callback_observes_no_final_pack_and_can_abort(tmp_path):
    archive, schema = inputs(tmp_path)
    mod = importlib.import_module("world_address_engine.data.hk_als_builder")
    from world_address_engine.data.hk_regional import verify_hk_pack
    seen = []
    def observe(event):
        if event["stage"] == "publishing":
            with pytest.raises(ValueError):
                verify_hk_pack(tmp_path / "pack/pack.db")
            seen.append(True)
            raise KeyboardInterrupt("Abort before atomic commit")
    with pytest.raises(KeyboardInterrupt):
        mod.build_als_pack(archive, schema, tmp_path / "pack", source_date="2026-10-23", pack_version="test", on_progress=observe)
    assert seen == [True]
    assert sorted(path.name for path in (tmp_path / "pack").iterdir()) == ["audit.json"]
    assert json.loads((tmp_path / "pack/audit.json").read_text())["status"] == "failed"


def test_existing_empty_output_can_be_atomically_replaced(tmp_path):
    (tmp_path / "pack").mkdir()
    assert build(tmp_path)["record_count"] == 1
    assert sorted(path.name for path in (tmp_path / "pack").iterdir()) == ["ATTRIBUTION.txt", "audit.json", "manifest.json", "pack.db"]
