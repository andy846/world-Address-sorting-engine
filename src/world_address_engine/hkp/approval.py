"""Release-controlled approval of the Hongkong Post destination master.

The catalogue data file must never be able to assert its own production
approval. Production authority lives in a detached manifest signed with a
key that the release process keeps **outside** the repository. The manifest
binds the catalogue version, the source CSV digest, the row count and the
built database digest, and it names the official source documents that an
independent reviewer actually vetted.

A manifest signed with a `TEST_FIXTURE` key can never authorise production,
whatever it claims.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path

from world_address_engine.sqlite_util import open_db

SCOPE_PRODUCTION = "PRODUCTION"
SCOPE_TEST_FIXTURE = "TEST_FIXTURE"
SCOPES = frozenset({SCOPE_PRODUCTION, SCOPE_TEST_FIXTURE})

MANIFEST_FIELDS = (
    "approval_id", "scope", "catalogue_version", "csv_sha256", "row_count",
    "catalogue_db_sha256", "approved_destinations", "approved_sources",
)
MINIMUM_KEY_BYTES = 32
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ApprovalError(ValueError):
    """Raised when an approval manifest cannot be trusted."""


def repository_root() -> Path | None:
    """Locate the source repository so a production key can be kept outside it."""
    for parent in Path(__file__).resolve().parents:
        marker = parent / "pyproject.toml"
        if not marker.is_file():
            continue
        try:
            text = marker.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "world-address-sorting-engine" in text:
            return parent
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_payload(payload: dict) -> bytes:
    """Deterministic byte form of a manifest, excluding the signature field."""
    body = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_manifest(payload: dict, key: bytes) -> dict:
    """Return a copy of `payload` carrying an HMAC-SHA256 signature."""
    if not key:
        raise ApprovalError("approval key must not be empty")
    signed = {name: value for name, value in payload.items() if name != "signature"}
    signed["signature"] = hmac.new(key, canonical_payload(signed), hashlib.sha256).hexdigest()
    return signed


def load_key(path: Path, *, scope: str = SCOPE_PRODUCTION) -> bytes:
    """Read an approval key, refusing repository-internal production keys."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ApprovalError(f"approval key unreadable: {path.name}") from exc
    key = raw.strip()
    if len(key) < MINIMUM_KEY_BYTES:
        raise ApprovalError(
            f"approval key must be at least {MINIMUM_KEY_BYTES} bytes"
        )
    if scope == SCOPE_PRODUCTION:
        root = repository_root()
        if root is not None:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved == root or root in resolved.parents:
                raise ApprovalError(
                    "a production approval key must be stored outside the repository"
                )
    return key


@dataclass(frozen=True, slots=True)
class ApprovedSource:
    """An official document that the release process reviewed and ratified."""

    source_url: str
    source_doc_version: str
    source_section: str
    source_sha256: str

    def ratifies(self, *, source_url: str, source_doc_version: str,
                 source_checksum: str) -> bool:
        return (source_url == self.source_url
                and source_doc_version == self.source_doc_version
                and source_checksum == self.source_sha256)


@dataclass(frozen=True, slots=True)
class CatalogueApproval:
    """A verified approval for one specific catalogue database."""

    approval_id: str
    scope: str
    catalogue_version: str
    csv_sha256: str
    row_count: int
    catalogue_db_sha256: str
    approved_destinations: frozenset[str]
    approved_sources: tuple[ApprovedSource, ...]
    manifest_sha256: str

    @property
    def is_production(self) -> bool:
        return self.scope == SCOPE_PRODUCTION

    def allows(self, destination_id: str) -> bool:
        return destination_id in self.approved_destinations

    def ratifies_source(self, *, source_url: str, source_doc_version: str,
                        source_checksum: str) -> bool:
        return any(source.ratifies(source_url=source_url,
                                   source_doc_version=source_doc_version,
                                   source_checksum=source_checksum)
                   for source in self.approved_sources)


def read_manifest(path: Path) -> dict:
    """Load and structurally validate an approval manifest."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ApprovalError(f"approval manifest unreadable: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ApprovalError("approval manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ApprovalError("approval manifest must be a JSON object")
    missing = [name for name in MANIFEST_FIELDS if name not in payload]
    if missing:
        raise ApprovalError(f"approval manifest missing fields: {', '.join(missing)}")
    if not isinstance(payload.get("signature"), str) or not payload["signature"]:
        raise ApprovalError("approval manifest is not signed")
    if payload["scope"] not in SCOPES:
        raise ApprovalError(f"unknown approval scope: {payload['scope']!r}")
    if not isinstance(payload["row_count"], int) or payload["row_count"] < 1:
        raise ApprovalError("approval manifest needs a positive row_count")
    for field in ("csv_sha256", "catalogue_db_sha256"):
        if not _HEX64.fullmatch(str(payload[field])):
            raise ApprovalError(f"approval manifest has a malformed {field}")
    destinations = payload["approved_destinations"]
    if not isinstance(destinations, list) or not destinations:
        raise ApprovalError("approval manifest approves no destination")
    sources = payload["approved_sources"]
    if not isinstance(sources, list) or not sources:
        raise ApprovalError("approval manifest ratifies no source document")
    for source in sources:
        if not isinstance(source, dict):
            raise ApprovalError("malformed approved source entry")
        for field in ("source_url", "source_doc_version", "source_sha256"):
            if not str(source.get(field, "")).strip():
                raise ApprovalError(f"approved source entry lacks {field}")
        if not _HEX64.fullmatch(str(source["source_sha256"])):
            raise ApprovalError("approved source entry has a malformed source_sha256")
    return payload


def load_approval(manifest_path: Path, key_path: Path, db_path: Path) -> CatalogueApproval:
    """Verify a signed approval against the exact catalogue database.

    Every binding is checked: the signature, the database digest, the
    catalogue version, the source CSV digest, the row count and the presence
    of every approved destination. Any mismatch fails closed.
    """
    manifest_path = Path(manifest_path)
    db_path = Path(db_path)
    payload = read_manifest(manifest_path)
    key = load_key(Path(key_path), scope=payload["scope"])
    expected = hmac.new(key, canonical_payload(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(payload["signature"])):
        raise ApprovalError("approval manifest signature does not verify")
    if file_sha256(db_path) != payload["catalogue_db_sha256"]:
        raise ApprovalError("approval manifest does not match this catalogue database")
    with open_db(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(metadata)")}
        if not {"catalogue_version", "csv_sha256", "row_count"} <= columns:
            raise ApprovalError("catalogue database lacks the approval metadata columns")
        meta = conn.execute(
            "SELECT catalogue_version, csv_sha256, row_count FROM metadata"
        ).fetchone()
        stored = {row[0] for row in conn.execute(
            "SELECT DISTINCT destination_id FROM destinations "
            "WHERE code_scheme='HKP_DESTINATION_2'"
        )}
        total_rows = conn.execute("SELECT COUNT(*) FROM destinations").fetchone()[0]
    if meta[0] != payload["catalogue_version"]:
        raise ApprovalError("approval manifest names a different catalogue version")
    if meta[1] != payload["csv_sha256"]:
        raise ApprovalError("approval manifest names a different source catalogue")
    if meta[2] != payload["row_count"] or total_rows != payload["row_count"]:
        raise ApprovalError("approval manifest row count does not match the catalogue")
    approved = frozenset(str(name) for name in payload["approved_destinations"])
    missing = sorted(approved - stored)
    if missing:
        raise ApprovalError(
            "approval manifest approves destinations absent from the catalogue: "
            + ", ".join(missing)
        )
    return CatalogueApproval(
        approval_id=str(payload["approval_id"]),
        scope=str(payload["scope"]),
        catalogue_version=str(payload["catalogue_version"]),
        csv_sha256=str(payload["csv_sha256"]),
        row_count=int(payload["row_count"]),
        catalogue_db_sha256=str(payload["catalogue_db_sha256"]),
        approved_destinations=approved,
        approved_sources=tuple(
            ApprovedSource(
                source_url=str(source["source_url"]),
                source_doc_version=str(source["source_doc_version"]),
                source_section=str(source.get("source_section", "")),
                source_sha256=str(source["source_sha256"]),
            )
            for source in payload["approved_sources"]
        ),
        manifest_sha256=file_sha256(manifest_path),
    )
