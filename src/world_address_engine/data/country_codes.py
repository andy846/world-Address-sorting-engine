"""Country-only USER_PROVIDED mappings, not an approved production HKP master.

Names and aliases retain their spelling and case; consumers normalize search
keys. Geographic country codes and source business codes are separate namespaces.
The runtime reads JSON with the standard library and never imports a PDF reader.
"""

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
from pathlib import Path
import re


SOURCE_SHA256 = "41b84a0938c1ebe320514b29c567ceedcf9f9868e99f84f3387bb8899cf2f373"
SOURCE_FILENAME = "1-CountryList_20250708.pdf"
SOURCE_PAGE_ENDS = (57, 113, 170, 227, 236)
# Digest of the complete, reviewed country-only transcript, serialized with
# sorted keys and compact UTF-8 JSON. Aliases/version can change independently.
SOURCE_ROWS_SHA256 = "78939bf134bf962c348b125a92efdea63992c62a9a54fc16b3081fad681e6b7e"


@dataclass(frozen=True)
class CountryEntry:
    code: str
    name_en: str
    name_tc: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CountrySourceRow:
    """One original Country Code row, including the excluded CNS service row."""

    seq: int
    page: int
    code: str
    name_en: str
    name_tc: str
    canonical_code: str
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class CountryCatalogue:
    entries: dict[str, CountryEntry]
    geo_to_code: dict[str, str]
    version: str
    source_sha256: str
    fingerprint: str
    profile: str = "USER_PROVIDED"
    source_rows: tuple[CountrySourceRow, ...] = ()


def _object(value, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"invalid {label} schema; expected fields {sorted(fields)}")
    return value


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonempty, trimmed string")
    return value


def _code(value) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Z]{2}", value) is None:
        raise ValueError("country code must be two uppercase letters; CNS is prohibited")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _geo_mapping(codes) -> dict[str, str]:
    # X* business territories have no inferred geographic country identity.
    # In particular source XK is Caroline Islands; GeoNames XK means Kosovo.
    mapping = {code: code for code in codes
               if not code.startswith("X") and code not in {"AN", "TP"}}
    mapping.update({"TL": "TP", "XK": "XO"})
    return mapping


def _load_bytes(raw: bytes) -> CountryCatalogue:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("country catalogue must be valid UTF-8 JSON") from exc
    _object(data, {"schema_version", "version", "profile", "source", "entries",
                   "source_rows", "geo_to_code"}, "country catalogue")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported country catalogue schema_version")
    if data["profile"] != "USER_PROVIDED":
        raise ValueError("country catalogue profile must be USER_PROVIDED")
    version = _text(data["version"], "version")
    source = _object(data["source"], {"filename", "sha256", "page_count", "row_count"}, "source")
    if source["filename"] != SOURCE_FILENAME or source["sha256"] != SOURCE_SHA256:
        raise ValueError("country catalogue source filename/SHA256 does not match the pinned PDF")
    if (type(source["page_count"]) is not int or source["page_count"] != 5
            or type(source["row_count"]) is not int or source["row_count"] != 236):
        raise ValueError("source must preserve 236 rows across 5 pages")

    if not isinstance(data["entries"], list) or len(data["entries"]) != 235:
        raise ValueError("country catalogue requires exactly 235 canonical entries")
    entries = {}
    for item in data["entries"]:
        _object(item, {"code", "name_en", "name_tc", "aliases"}, "entry")
        code = _code(item["code"])
        if code in entries:
            raise ValueError(f"duplicate country code: {code}")
        name_en = _text(item["name_en"], "name_en")
        name_tc = _text(item["name_tc"], "name_tc")
        aliases = item["aliases"]
        if not isinstance(aliases, list):
            raise ValueError("aliases must be a list of strings")
        for alias in aliases:
            _text(alias, "alias")
        if len(aliases) != len(set(aliases)) or not {name_en, name_tc} <= set(aliases):
            raise ValueError("aliases must be unique and include both full source names")
        entries[code] = CountryEntry(code, name_en, name_tc, tuple(aliases))

    rows = data["source_rows"]
    if not isinstance(rows, list) or len(rows) != 236:
        raise ValueError("source_rows must preserve all 236 source rows")
    transcript = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(transcript).hexdigest() != SOURCE_ROWS_SHA256:
        raise ValueError("source_rows differ from the pinned country-only source transcript")
    source_rows = []
    seen = set()
    for seq, row in enumerate(rows, 1):
        _object(row, {"seq", "page", "code", "name_en", "name_tc", "canonical_code",
                      "exclusion_reason"}, "source row")
        page = next(i for i, end in enumerate(SOURCE_PAGE_ENDS, 1) if seq <= end)
        if (type(row["seq"]) is not int or row["seq"] != seq
                or type(row["page"]) is not int or row["page"] != page):
            raise ValueError("source rows must retain sequential source numbers and original pages")
        code = row["code"]
        if seq == 46:
            if (code != "CNS" or row["canonical_code"] != "CN"
                    or row["exclusion_reason"] != "service_duplicate"
                    or row["name_en"] != entries["CN"].name_en
                    or row["name_tc"] != "\u4e2d\u570b\u5167\u5730 \u5e73\u90f5"):
                raise ValueError("source row 46 must audit CNS as the excluded CN service duplicate")
        else:
            _code(code)
            if code in seen or code not in entries:
                raise ValueError("duplicate or unknown source country code")
            seen.add(code)
            entry = entries[code]
            if (row["canonical_code"] != code or row["exclusion_reason"] is not None
                    or row["name_en"] != entry.name_en or row["name_tc"] != entry.name_tc):
                raise ValueError("source row names and canonical code must agree with the entry")
        source_rows.append(CountrySourceRow(**row))
    if seen != set(entries) or rows[44]["code"] != "CN":
        raise ValueError("canonical entries must correspond to all source rows except CNS")

    geo_to_code = data["geo_to_code"]
    if not isinstance(geo_to_code, dict):
        raise ValueError("geo_to_code must be an object")
    for geo, code in geo_to_code.items():
        _code(geo)
        _code(code)
    if geo_to_code != _geo_mapping(entries):
        raise ValueError("invalid GeoNames mapping: only same-code countries, TL->TP and XK->XO are allowed")
    return CountryCatalogue(entries, dict(geo_to_code), version, source["sha256"],
                            hashlib.sha256(raw).hexdigest(), data["profile"], tuple(source_rows))


def load_country_codes(path: Path | None = None) -> CountryCatalogue:
    """Validate the pinned country-only JSON and fingerprint its exact bytes.

    Source provenance is an audit record, not a production approval. A missing
    explicit path raises OSError; malformed or inconsistent data raises ValueError.
    """
    raw = (resources.files("world_address_engine.resources").joinpath("country_codes.json").read_bytes()
           if path is None else Path(path).read_bytes())
    return _load_bytes(raw)
