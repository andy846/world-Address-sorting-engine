"""Literal USER_PROVIDED zones from the pinned CountryList PDF.

Runtime validation uses only standard-library JSON and the existing country
catalogue. PDF parsing belongs exclusively to the build-time importer.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
from importlib import resources
import json
from pathlib import Path
from types import MappingProxyType

from world_address_engine.data.country_codes import (
    SOURCE_FILENAME, SOURCE_SHA256, _code, _object, _text, _unique_object,
    load_country_codes,
)


# Reviewed full transcript, including the excluded CNS surface-service row.
# Compact sorted-key UTF-8 JSON; version and resource formatting are independent.
SOURCE_ROWS_SHA256 = "9c9f1b98948949886b4dee03da5fed5528654308e3fb43b531ac1e6115bd0cc3"


@dataclass(frozen=True)
class ZoneEntry:
    country_code: str
    zone_code: str
    novsn_zone_code: str


@dataclass(frozen=True)
class ZoneCatalogue:
    entries: Mapping[str, ZoneEntry]
    version: str
    source_sha256: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))


def _load_bytes(raw: bytes) -> ZoneCatalogue:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("zone catalogue must be valid UTF-8 JSON") from exc
    _object(data, {"schema_version", "version", "profile", "source", "entries", "source_rows"}, "zone catalogue")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported zone catalogue schema_version")
    if data["profile"] != "USER_PROVIDED":
        raise ValueError("zone catalogue profile must be USER_PROVIDED")
    version = _text(data["version"], "version")
    source = _object(data["source"], {"filename", "sha256", "page_count", "row_count"}, "source")
    if source["filename"] != SOURCE_FILENAME or source["sha256"] != SOURCE_SHA256:
        raise ValueError("zone catalogue source filename/SHA256 does not match the pinned PDF")
    if (type(source["page_count"]) is not int or source["page_count"] != 5
            or type(source["row_count"]) is not int or source["row_count"] != 236):
        raise ValueError("source must preserve 236 rows across 5 pages")

    countries = load_country_codes()
    if not isinstance(data["entries"], list) or len(data["entries"]) != 235:
        raise ValueError("zone catalogue requires exactly 235 active entries")
    entries = {}
    for item in data["entries"]:
        _object(item, {"country_code", "zone_code", "novsn_zone_code"}, "zone entry")
        code = _code(item["country_code"])
        if code in entries:
            raise ValueError(f"duplicate zone country code: {code}")
        entries[code] = ZoneEntry(code, _text(item["zone_code"], "zone_code"),
                                  _text(item["novsn_zone_code"], "novsn_zone_code"))
    if set(entries) != set(countries.entries):
        raise ValueError("zones must cover exactly the existing 235 business country codes")

    rows = data["source_rows"]
    if not isinstance(rows, list) or len(rows) != 236:
        raise ValueError("source_rows must preserve all 236 source rows")
    transcript = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(transcript).hexdigest() != SOURCE_ROWS_SHA256:
        raise ValueError("source_rows differ from the pinned zone source transcript")
    for row, country in zip(rows, countries.source_rows, strict=True):
        identity = asdict(country)
        _object(row, set(identity) | {"zone_code", "novsn_zone_code"}, "zone source row")
        if ({key: row[key] for key in identity} != identity
                or type(row["seq"]) is not int or type(row["page"]) is not int):
            raise ValueError("zone source row identity/order/page differs from the country catalogue")
        zone = _text(row["zone_code"], "source zone_code")
        novsn = _text(row["novsn_zone_code"], "source novsn_zone_code")
        if country.exclusion_reason is None:
            if entries[country.code] != ZoneEntry(country.code, zone, novsn):
                raise ValueError(f"zone entry differs from source transcript: {country.code}")
    return ZoneCatalogue(entries, version, source["sha256"], hashlib.sha256(raw).hexdigest())


def load_zone_mappings(path: Path | None = None) -> ZoneCatalogue:
    """Validate the complete pinned transcript and hash the resource's exact bytes.

    An explicit missing path raises OSError; invalid content raises ValueError.
    The default resource contains public source-table data only.
    """
    raw = (resources.files("world_address_engine.resources").joinpath("country_zone_mappings.json").read_bytes()
           if path is None else Path(path).read_bytes())
    return _load_bytes(raw)


def zone_values(code: str | None, catalogue: ZoneCatalogue | None = None) -> tuple[str, str]:
    """Look up a final business country code without geographic normalization."""
    if code is None or code == "":
        return "", ""
    if not isinstance(code, str):
        raise ValueError("zone lookup requires a business country code string")
    catalogue = load_zone_mappings() if catalogue is None else catalogue
    try:
        entry = catalogue.entries[code]
    except KeyError as exc:
        raise ValueError(f"unknown zone country code: {code}") from exc
    return entry.zone_code, entry.novsn_zone_code
