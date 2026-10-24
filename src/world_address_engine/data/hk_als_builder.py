"""Audited, offline ALS GeoJSON to SQLite builder (build dependencies are lazy)."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
from datetime import date
import hashlib
from importlib.metadata import version
import json
import math
import os
from itertools import chain
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tempfile
import time
import zipfile

SOURCE_URL = "https://www.als.gov.hk/data/ALS-GeoJSON.zip"
LICENSE_URL = "https://data.gov.hk/en/terms-and-conditions"
ATTRIBUTION = "Contains address data from the Address Lookup Service, Digital Policy Office, Hong Kong SAR Government."
CONVERSION_VERSION = "opencc-python-reimplemented==0.1.7"

_DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE hk_buildings(csu_id TEXT PRIMARY KEY);
CREATE TABLE hk_addresses(address_id TEXT PRIMARY KEY,csu_id TEXT NOT NULL,
 source_member TEXT NOT NULL,source_index INTEGER NOT NULL,geo_address TEXT,
 longitude REAL,latitude REAL,region_en TEXT,region_hant TEXT,district_en TEXT,
 district_hant TEXT,number_from TEXT,number_to TEXT,number_conflict INTEGER NOT NULL,
 FOREIGN KEY(csu_id) REFERENCES hk_buildings(csu_id));
CREATE TABLE hk_aliases(address_id TEXT,kind TEXT,language TEXT,name TEXT,
 search_key TEXT,derived INTEGER,anchor TEXT,
 PRIMARY KEY(address_id,kind,language,search_key),
 FOREIGN KEY(address_id) REFERENCES hk_addresses(address_id));
CREATE TABLE hk_pack_metadata(profile TEXT,schema_version INTEGER,normalization_version INTEGER);
INSERT INTO hk_pack_metadata VALUES('HK_BILINGUAL_REGIONAL',1,1);
CREATE INDEX hk_alias_lookup ON hk_aliases(search_key,kind,address_id);
CREATE INDEX hk_alias_anchor ON hk_aliases(anchor,address_id);
CREATE INDEX hk_alias_address ON hk_aliases(address_id);
"""


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _safe_members(archive):
    seen = set()
    members = []
    for info in archive.infolist():
        name = info.orig_filename
        path = PurePosixPath(name)
        mode = info.external_attr >> 16
        if (name in seen or "\\" in name or path.is_absolute() or
                ".." in path.parts or ":" in name or "\x00" in name or
                stat.S_ISLNK(mode) or info.flag_bits & 1):
            raise ValueError("Unsafe, duplicate or encrypted ZIP member")
        seen.add(name)
        if info.is_dir():
            # A trailing slash does not exempt bytes from ZIP validation.
            if info.file_size != 0:
                raise ValueError("ZIP directory member contains a payload")
            with archive.open(info) as directory:
                if directory.read(1):
                    raise ValueError("ZIP directory member contains a payload")
        else:
            if path.suffix.lower() != ".geojson":
                raise ValueError("Unexpected non-GeoJSON ZIP member")
            members.append(info)
    if not members:
        raise ValueError("Archive contains no GeoJSON members")
    return sorted(members, key=lambda item: item.filename)


def _stream_features(stream, feature_callback):
    """Consume entire member (including CRC), retaining one feature and envelope.

    Reconstruct the small envelope with an empty features array. Features are
    separately schema-validated in full, including all nested floor/unit arrays.
    Duplicate object keys are rejected rather than silently overwritten.
    """
    import ijson
    from ijson.common import ObjectBuilder
    root = ObjectBuilder()
    current = None
    stack = []
    count = 0
    features_seen = False
    features_depth = None
    # basic_parse is essential: ijson's dotted prefixes cannot distinguish
    # a literal property 'features.item' from a real array item.
    for event, value in ijson.basic_parse(stream, use_float=True):
        if event == "map_key":
            if value in stack[-1]["keys"]:
                raise ValueError("Duplicate JSON object key")
            stack[-1]["keys"].add(value)
            stack[-1]["key"] = value
        is_value = event not in ("map_key", "end_map", "end_array")
        if is_value and len(stack) == 1 and stack[0]["kind"] == "start_map" and stack[0]["key"] == "features":
            if event != "start_array":
                raise ValueError("GeoJSON features must be an array")
            features_seen = True
            features_depth = 2
        elif is_value and features_depth is not None and len(stack) == features_depth and current is None:
            current = ObjectBuilder()
        if current is not None:
            current.event(event, value)
        else:
            root.event(event, value)
        if event in ("start_map", "start_array"):
            stack.append({"kind": event, "key": None, "keys": set()})
        elif event in ("end_map", "end_array"):
            stack.pop()
        if current is not None and len(stack) == features_depth:
            count += 1
            feature_callback(current.value, count)
            current = None
        if features_depth is not None and len(stack) < features_depth:
            # The features array itself has just closed.
            if event == "end_array":
                features_depth = None
    # ijson consumes to EOF; explicitly drain for ZIP's CRC check as well.
    while stream.read(1024 * 1024):
        pass
    if not features_seen or not isinstance(root.value, dict):
        raise ValueError("GeoJSON envelope must contain a features array")
    return root.value, count


def _check_stream_schema(spec):
    """Reject unsupported root constraints and all unhashed reference sources.

    Only features.items and its local definitions are evaluated against actual
    features; array min/max are counted separately. All other root assertions
    must be independent of array contents, or they cannot be honestly checked
    against the reconstructed envelope.
    """
    allowed = {"$schema", "$id", "$comment", "title", "description", "type", "required",
               "properties", "additionalProperties", "$defs", "definitions",
               "minProperties", "maxProperties"}
    if not isinstance(spec, dict) or set(spec) - allowed or spec.get("type") != "object":
        raise ValueError("Unsupported root/cross-feature schema constraints")
    if not isinstance(spec.get("additionalProperties", True), bool):
        raise ValueError("Unsupported root additionalProperties schema")
    def visit(node, root=False):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and (not isinstance(value, str) or not value.startswith(("#/$defs/", "#/definitions/"))):
                    raise ValueError("Unsupported external or cross-feature schema reference")
                if key in ("$dynamicRef", "$recursiveRef") or key == "$id" and not root:
                    raise ValueError("Unsupported schema reference scope")
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(spec, root=True)


def _number_key(value, normalize):
    """Compare numeric spellings without changing the official stored text."""
    key = normalize(value)
    match = re.fullmatch(r"([0-9]+)([a-z]?)", key)
    if match:
        return int(match[1]), match[2]
    match = re.fullmatch(r"([零〇一二兩两三四五六七八九十百千]+)([a-z]?)", key)
    if not match or len(match[1]) > 16:
        return key
    digits = dict(zip("零〇一二兩两三四五六七八九", (0, 0, 1, 2, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
    total = number = 0
    previous_unit = 10000
    for char in match[1]:
        if char in digits:
            number = number * 10 + digits[char]
        else:
            unit = {"十": 10, "百": 100, "千": 1000}[char]
            if unit >= previous_unit:
                return key
            total += (number or 1) * unit
            number, previous_unit = 0, unit
    return total + number, match[2]


def _projection(feature):
    premises = feature["properties"]["Address"]["PremisesAddress"]
    csu = premises["BuildingCsuInformation"]["CsuId"]
    zh = {k: v for k, v in premises["ChiPremisesAddress"].items() if k != "Chi3dAddress"}
    en = {k: v for k, v in premises["EngPremisesAddress"].items() if k != "Eng3dAddress"}
    identity = json.dumps([csu, zh, en], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest(), csu, zh, en, premises


def _insert(db, feature, member, index, convert, normalize, anchor):
    address_id, csu, zh, en, premises = _projection(feature)
    db.execute("INSERT OR IGNORE INTO hk_buildings VALUES(?)", (csu,))
    def numbers(value, prefix):
        # Number ranges belong to the street; village is the documented fallback.
        location = value.get(prefix + "Street") or value.get(prefix + "Village") or {}
        return tuple(location.get(key, "").strip() for key in ("BuildingNoFrom", "BuildingNoTo"))
    en_numbers, zh_numbers = numbers(en, "Eng"), numbers(zh, "Chi")
    selected = tuple(number or None for number in (en_numbers if any(en_numbers) else zh_numbers))
    conflict = int(any(e and z and _number_key(e, normalize) != _number_key(z, normalize) for e, z in zip(en_numbers, zh_numbers)))
    coordinates = feature["geometry"]["coordinates"]
    cursor = db.execute("INSERT OR IGNORE INTO hk_addresses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        address_id, csu, member, index, premises.get("GeoAddress"), *coordinates[:2],
        en.get("Region"), zh.get("Region"), en.get("EngDistrict"), zh.get("ChiDistrict"),
        *selected, conflict))
    if not cursor.rowcount:
        return False
    for value, prefix, language in ((en, "Eng", "en"), (zh, "Chi", "zh-Hant")):
        names = [("building", value.get("BuildingName")),
                 ("district", value.get(prefix + "District"))]
        for kind, obj, field in (("street", "Street", "StreetName"),
                                  ("estate", "Estate", "EstateName"),
                                  ("village", "Village", "VillageName")):
            names.append((kind, (value.get(prefix + obj) or {}).get(field)))
        for kind, name in names:
            if not name or not name.strip():
                continue
            variants = [(language, name, 0)]
            if language == "zh-Hant":
                variants.append(("zh-Hans", convert(name), 1))
            for lang, alias, derived in variants:
                key = normalize(alias)
                if key:
                    db.execute("INSERT OR IGNORE INTO hk_aliases VALUES(?,?,?,?,?,?,?)", (
                        address_id, kind, lang, alias, key, derived, anchor(key)))
    return True


def build_als_pack(archive, schema, output_dir, *, source_date, pack_version, on_progress=None):
    """Build a strictly validated pack; failures leave only aggregate audit.json.

    Returns the published manifest. Progress receives count-only dictionaries.
    A failed directory is never reused automatically: choose a fresh destination.
    """
    import jsonschema
    import ijson
    from opencc import OpenCC
    from world_address_engine.data.hk_regional import normalize_hk_key, alias_anchor

    archive, schema, output = Path(archive).resolve(), Path(schema).resolve(), Path(output_dir).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError("Existing nonempty output directory; choose a new destination")
    if output in (archive, schema) or output in archive.parents or output in schema.parents:
        raise ValueError("Output must not contain the source files")
    date.fromisoformat(source_date)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", pack_version):
        raise ValueError("Unsafe pack version")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{output.name}.building-", dir=output.parent))
    work_identity = work.stat()
    staging = work / "pack.db.building"
    audit = {"status": "building", "feature_count": 0, "valid_count": 0, "invalid_count": 0,
             "duplicate_count": 0, "three_d_item_count": 0, "members": [], "errors": [],
             "district_counts": {}, "blank_optional_counts": {}, "bilingual_pair_count": 0}
    started = time.monotonic()
    def notify(stage):
        if on_progress:
            on_progress({"stage": stage, "feature_count": audit["feature_count"],
                         "invalid_count": audit["invalid_count"], "member_count": len(audit["members"])})
    try:
        if version("opencc-python-reimplemented") != "0.1.7":
            raise ValueError("Builder requires pinned OpenCC 0.1.7")
        source_hash, schema_hash = _sha(archive), _sha(schema)
        audit.update(source_sha256=source_hash, schema_sha256=schema_hash,
                     source_bytes=archive.stat().st_size, schema_bytes=schema.stat().st_size)
        spec = json.loads(schema.read_text(encoding="utf-8-sig"))
        _check_stream_schema(spec)
        validator_type = jsonschema.validators.validator_for(spec)
        try:
            validator_type.check_schema(spec)
            array_spec = spec["properties"]["features"]
            item_spec = array_spec["items"]
        except (jsonschema.SchemaError, KeyError, TypeError) as exc:
            raise ValueError("Invalid or unsupported ALS schema") from exc
        # Fail closed for array-wide constraints that cannot be checked per item.
        if set(array_spec) - {"type", "items", "minItems", "maxItems", "title", "description"}:
            raise ValueError("Unsupported cross-feature schema constraints")
        envelope_spec = deepcopy(spec)
        envelope_spec["properties"]["features"] = {"type": "array"}
        root_validator = validator_type(spec)
        envelope_validator = root_validator.evolve(schema=envelope_spec)
        feature_validator = root_validator.evolve(schema=item_spec)
        convert = OpenCC("t2s").convert
        districts, blanks = Counter(), Counter()
        schema_errors, missing_required = Counter(), Counter()
        with archive.open("rb") as source_stream, closing(sqlite3.connect(staging)) as db:
            # Hash the very handle ZIP will consume, not just its pathname.
            if hashlib.file_digest(source_stream, "sha256").hexdigest() != source_hash:
                raise ValueError("Source changed before read")
            source_stream.seek(0)
            db.executescript(_DDL)
            with zipfile.ZipFile(source_stream) as z:
                members = _safe_members(z)
                for info in members:
                    member_audit = {"member": info.filename, "uncompressed_bytes": info.file_size,
                                    "crc32": f"{info.CRC:08x}", "feature_count": 0, "invalid_count": 0}
                    def accept(obj, index):
                        audit["feature_count"] += 1
                        member_audit["feature_count"] += 1
                        # Audit raw 3D array sizes even on schema-invalid features.
                        raw_premises = obj
                        for part in ("properties", "Address", "PremisesAddress"):
                            raw_premises = raw_premises.get(part, {}) if isinstance(raw_premises, dict) else {}
                        for prefix in ("Chi", "Eng"):
                            value = raw_premises.get(prefix + "PremisesAddress", {}) if isinstance(raw_premises, dict) else {}
                            units = value.get(prefix + "3dAddress") if isinstance(value, dict) else None
                            if isinstance(units, list):
                                audit["three_d_item_count"] += len(units)
                        error_iterator = feature_validator.iter_errors(obj)
                        error = next(error_iterator, None)
                        if error is not None:
                            reason = "feature_schema"
                            seen_missing = set()
                            for item in chain((error,), error_iterator):
                                path = "/".join("[]" if isinstance(part, int) else part for part in item.absolute_path)
                                schema_errors[(path, item.validator)] += 1
                                if item.validator == "required" and isinstance(item.instance, dict):
                                    for key in item.validator_value:
                                        if key not in item.instance:
                                            identity = (tuple(item.absolute_path), key)
                                            if identity not in seen_missing:
                                                missing_required[(path, key)] += 1
                                                seen_missing.add(identity)
                        else:
                            try:
                                _, csu, zh, en, p = _projection(obj)
                                lon, lat = obj["geometry"]["coordinates"][:2]
                                if (not csu.strip() or not all(math.isfinite(v) for v in (lon, lat)) or
                                        not (113.7 <= lon <= 114.6 and 22.1 <= lat <= 22.6) or
                                        en["Region"] not in ("HK", "KLN", "NT") or
                                        zh["Region"] not in ("香港", "九龍", "新界")):
                                    raise ValueError("Invalid HK geography")
                                reason = None
                            except (KeyError, TypeError, ValueError):
                                reason = "invalid_hk_address"
                        if reason:
                            audit["invalid_count"] += 1
                            member_audit["invalid_count"] += 1
                            if len(audit["errors"]) < 20:
                                audit["errors"].append({"member": info.filename, "source_index": index, "reason": reason})
                            return
                        audit["valid_count"] += 1
                        districts[en["EngDistrict"]] += 1
                        audit["bilingual_pair_count"] += 1
                        for value, prefix in ((zh, "Chi"), (en, "Eng")):
                            for key in ("BuildingName", prefix + "Street", prefix + "Estate", prefix + "Village"):
                                if not value.get(key):
                                    blanks[prefix + "." + key] += 1
                        if not _insert(db, obj, info.filename, index, convert, normalize_hk_key, alias_anchor):
                            audit["duplicate_count"] += 1
                        if index % 1000 == 0:
                            notify("validating")
                    with z.open(info) as member:
                        try:
                            envelope, count = _stream_features(member, accept)
                        except ijson.JSONError as exc:
                            raise ValueError("Malformed GeoJSON member") from exc
                    if (count < array_spec.get("minItems", 0) or
                            count > array_spec.get("maxItems", float("inf"))):
                        raise ValueError("Feature count violates schema")
                    if next(envelope_validator.iter_errors(envelope), None) is not None:
                        raise ValueError("Invalid GeoJSON envelope")
                    member_audit["crc_verified"] = True
                    audit["members"].append(member_audit)
                    audit["district_counts"], audit["blank_optional_counts"] = dict(districts), dict(blanks)
                    audit["schema_error_counts"] = [{"path": key[0], "validator": key[1], "count": value}
                                                    for key, value in sorted(schema_errors.items())]
                    audit["schema_required_missing_counts"] = [{"path": key[0], "field": key[1], "count": value}
                                                               for key, value in sorted(missing_required.items())]
                    db.commit()
                    notify("member_complete")
            source_stream.seek(0)
            if (hashlib.file_digest(source_stream, "sha256").hexdigest() != source_hash or
                    _sha(archive) != source_hash or _sha(schema) != schema_hash):
                raise ValueError("Source or schema changed during build")
            if audit["invalid_count"]:
                raise ValueError("Invalid features block final database; see audit.json")
            record_count = db.execute("SELECT COUNT(*) FROM hk_addresses").fetchone()[0]
            if record_count == 0:
                raise ValueError("No valid addresses")
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("SQLite integrity check failed")
            manifest = {"profile": "HK_BILINGUAL_REGIONAL", "schema_version": 1, "normalization_version": 1,
                        "pack_id": "hk-bilingual-als", "pack_version": pack_version,
                        "source_date": source_date, "source_url": SOURCE_URL,
                        "source_sha256": source_hash, "schema_sha256": schema_hash,
                        "record_count": record_count,
                        "building_count": db.execute("SELECT COUNT(*) FROM hk_buildings").fetchone()[0],
                        "alias_count": db.execute("SELECT COUNT(*) FROM hk_aliases").fetchone()[0],
                        "alias_count_by_language": dict(db.execute("SELECT language,COUNT(*) FROM hk_aliases GROUP BY language")),
                        "conversion_version": CONVERSION_VERSION, "attribution": ATTRIBUTION,
                        "license": {"url": LICENSE_URL, "text": "Reuse subject to DATA.GOV.HK terms; retain source attribution and original terms. Not relicensed under the software license."}}
            db.commit()
        manifest["db_sha256"] = _sha(staging)
        def check_sources():
            if _sha(archive) != source_hash or _sha(schema) != schema_hash:
                raise ValueError("Source or schema changed during publication")
        check_sources()
        audit.update(status="publishing", record_count=record_count,
                     elapsed_seconds=round(time.monotonic() - started, 3))
        _json_write(work / "audit.json", audit)
        (work / "ATTRIBUTION.txt").write_text(ATTRIBUTION + "\n" + SOURCE_URL + "\n" + LICENSE_URL + "\n" + manifest["license"]["text"] + "\n", encoding="utf-8")
        staging.rename(work / "pack.db")
        _json_write(work / "manifest.json", manifest)
        check_sources()
        audit["status"] = "complete"
        _json_write(work / "audit.json", audit)
        notify("publishing")
        check_sources()
        # All four files and all checks complete before the output is visible.
        # A sibling directory rename is the commit point on the same filesystem.
        # The last source check pins a validated snapshot; the caller must retain
        # that original archive, not assume the source pathname is immutable.
        if output.exists():
            if not output.is_dir() or any(output.iterdir()):
                raise FileExistsError("Output appeared during build; refusing overwrite")
            output.rmdir()
        work.rename(output)
        return manifest
    except BaseException as exc:
        # Identity, rather than a flag set after rename, covers interruption in
        # the tiny gap immediately after the atomic directory commit syscall.
        if not work.exists() and output.exists() and os.path.samestat(output.stat(), work_identity):
            output.rename(work)
        for name in ("pack.db.building", "pack.db.building-journal", "pack.db", "manifest.json", "ATTRIBUTION.txt"):
            (work / name).unlink(missing_ok=True)
        # Never expose invalid source values in audit or CLI error output.
        audit.update(status="failed", failure_type=type(exc).__name__,
                     elapsed_seconds=round(time.monotonic() - started, 3))
        _json_write(work / "audit.json", audit)
        if output.exists() and output.is_dir() and not any(output.iterdir()):
            output.rmdir()
        if not output.exists():
            work.rename(output)
        # If a competing writer owns output, keep this failed audit in its
        # uniquely named sibling; never overwrite the other writer's pack.
        raise
