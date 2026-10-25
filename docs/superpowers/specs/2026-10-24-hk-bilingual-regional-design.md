# ALS Hong Kong bilingual regional pack — approved design

Approved user choices: ALS first, independent installable pack, unresolved-only
fallback. Start from v0.1.0; preserve its tag/assets/Latest designation.

## Interfaces and responsibilities

Builder API in data/hk_als_builder.py:
`build_als_pack(archive, schema, output_dir, *, source_date, pack_version, on_progress=None)`.
Produces pack.db, manifest.json, audit.json, ATTRIBUTION.txt. Refuses existing
nonempty output. Full source/schema SHA256, ZIP CRC, envelope/schema validation,
audit counts and provenance are mandatory. Build-only ijson/jsonschema imports
must be lazy, not required by an installed EXE. Alias normalization lives in
data/hk_regional.py as `normalize_hk_key(text)` (NFKC/casefold, punctuation and
space folding; preserve Han/digits) and `alias_anchor(key)` (deterministic longest
Latin content word, excluding generic building/street terms; first Han trigram
or full two-Han key). No runtime API calls.

Registry API in data/hk_regional.py:
`verify_hk_pack(db_path, *, full=True) -> dict` validates profile/schema,
manifest/db hashes, counts/indexes/integrity and returns manifest.
`install_hk_pack(staging_dir, active_root) -> Path` atomically installs a new
version, refuses overwrites and returns pack.db; source snapshot/build files stay
outside installation. `hk_pack_metadata(db_path) -> dict` returns path/profile/
version/schema plus DB/manifest SHA256 for checkpoint pinning.

Matcher API in matching/hk_regional.py:
`HKRegionalMatcher(db_path)` read-only/query-only, `match(text) -> HKRegionalMatch|None`,
with immutable result `address_ids: tuple[str,...]`, `evidence: tuple[str,...]`.
Context manager/close must release SQLite handles. At most 64 accepted candidate
address IDs. Overbroad anchors are skipped; bounded indexed retrieval never scans
all aliases. Final normalized whole-alias containment must be boundary-aware,
not Latin substrings. All supporting roles must occur in address context, not
company or recipient lines. Matching requires building/estate+street, or
street+house-number+district on the SAME address ID. Supplied street number
contradictions reject a candidate; no guessing from building/street alone.

CountryClassifier(geo_db,catalogue=None,*,hk_regional_db=None) and
analyze_job(...,*,hk_regional_db=None). Only NO_GEOGRAPHIC_MATCH and
MULTIPLE_PLAUSIBLE_COUNTRIES may upgrade to HK/INFERRED with reason
HK_REGIONAL_ADDRESS_MATCH; all existing assigned results and all explicit,
administrative and independent-city conflicts remain unchanged. Country
evidence is `HK_ALS:<address_id>`; CSV column contracts stay unchanged.

## SQLite schema contract (regional schema 1, normalization 1)

`hk_buildings(csu_id TEXT PRIMARY KEY)` represents building entities, not unique
addresses. `hk_addresses(address_id TEXT PRIMARY KEY,csu_id TEXT NOT NULL,
source_member TEXT NOT NULL,source_index INTEGER NOT NULL,geo_address TEXT,
longitude REAL,latitude REAL,region_en TEXT,region_hant TEXT,district_en TEXT,
district_hant TEXT,number_from TEXT,number_to TEXT,number_conflict INTEGER NOT NULL)`.
Foreign key csu_id -> hk_buildings. Number range uses EN when available, otherwise
Hant; nonempty contradictory EN/Hant numbers set number_conflict=1. Full raw
source is preserved outside the pack, referenced by archive SHA/member/index.

`hk_aliases(address_id TEXT,kind TEXT,language TEXT,name TEXT,search_key TEXT,
derived INTEGER,anchor TEXT,PRIMARY KEY(address_id,kind,language,search_key))`.
Kinds building/estate/street/village/district; languages en/zh-Hant/zh-Hans.
FK address_id -> hk_addresses. Index hk_alias_lookup(search_key,kind,address_id),
hk_alias_anchor(anchor,address_id), hk_alias_address(address_id).
`hk_pack_metadata(profile TEXT,schema_version INTEGER,normalization_version INTEGER)`.

Address IDs are SHA256 of canonical CsuId + bilingual 2D premises objects,
excluding 3D arrays; exact projected duplicates coalesce and are counted. Do not
merge names/CsuIds/coordinates heuristically. Derived Simplified aliases use
pinned OpenCC and are not independent geographic evidence. All aliases retain
their original official name/language through address identity and provenance.

Manifest profile HK_BILINGUAL_REGIONAL, schema_version=1,
normalization_version=1, pack_id='hk-bilingual-als', pack_version supplied,
source_date, source_url, source_sha256, schema_sha256, db_sha256,
record_count (unique addresses), building_count, alias_count,
alias_count_by_language, conversion_version, attribution, license URL/text.
Standard installed path packs/hk-bilingual-als-<version>/pack.db.

## Jobs, GUI, compatibility

Checkpoint schema becomes 2026-10-24.country-state.2, country rules
2026-10-24.country.5. Config/run_metadata `hk_regional` is null when disabled,
otherwise metadata with path/profile/version/schema_version/db_sha256/
manifest_sha256. Preflight validates before writing state; resume never
autodiscovers or silently changes the pinned regional selection. Source changes
before final export fail closed. Old checkpoints remain untouched for v0.1.0.

CLI --hk-regional-db; GUI optional enable/select field and version display;
installed packs may be discovered but only applied when enabled. Default no
pack preserves v0.1.0 inference outputs. Wrong regional/global profile gives
clear input errors. v0.2.0rc1 candidate, not Latest; data pack is independent,
free and source-attributed. No RVD/road/iG1000 ingestion in this phase.

## Gates

Source audit/reconciliation, four-language positives and overseas/company/
number-mismatch negatives, same-CsuId multi-address regressions, all previously
assigned private baseline rows unchanged, precise new-HK review, real-pack
performance, million-row enabled/disabled and fresh-process resume identity.
Use TDD, independent review and full regression/bundle validation. No private
customer input/row outputs in Git or CI. No claims of exhaustive HK coverage,
global accuracy or deliverability.
