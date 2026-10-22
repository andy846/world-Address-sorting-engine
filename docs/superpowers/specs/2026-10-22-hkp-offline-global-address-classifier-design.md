# World Address Sorting Engine — HK Post Offline Classification Design

**Status:** Draft specification for user review. No application code has been written.
**Date:** 2026-10-22
**Repository:** andy846/world-Address-sorting-engine
**Primary user goal:** Import very large numbers of international addresses and export one Hongkong Post destination code per address plus exact destination statistics.
**Runtime requirement:** Fully offline.
**Postal standard:** Hongkong Post destination codes, not ISO codes.

## 1. Accepted brief and scope

Build a production-oriented Windows Python application for overseas postal address classification. An operator selects a CSV, XLSX or TXT, maps one or more address columns, runs a batch, reviews uncertain cases, and exports original data with the HKP country/destination code and a summary by postal destination. Inputs may lack an explicit country name. Support English, traditional/simplified Chinese and transliterated international place names.

Non-negotiable conditions:

1. Import, normalization, matching, GUI, review, reporting and export run WITHOUT network access.
2. Geo datasets, postal mappings and dependencies are installed/imported in advance. A separate optional data-pack preparation/update process can use the network on a connected computer; never require network during a production run.
3. Every valid logical input record has exactly one output record in original order; no silent losses or duplicate output rows.
4. If evidence is insufficient, contradictory, or the HKP mapping is not verified, return REVIEW or UNKNOWN, not a guessed destination.
5. Freeze source versions for each job; results must be reproducible and auditable.
6. Addresses are personal data: never transmit input records, never log full addresses by default, define local retention/deletion controls.

Not part of this initial product: live geocoding, validating actual deliverability, postal-rate calculation, verifying live service eligibility/suspensions, purchasing postage, EC-Ship order submission, or guaranteeing exhaustive coverage of every street or building worldwide.

## 2. Hongkong Post code authority and output contract

HKP has more than one coding scheme:

- EC-Ship Bulk Mail API specification v1.23, Appendices D/E/F, publishes TWO-character destination codes for Bulk Air Mail, Lightweight Surface and Lightweight Air, subject to service-specific membership.
- Other HKP destination/zone charts also use TWO-character destination codes; some historic codes differ from current ISO, including Timor-Leste TP versus ISO TL.
- HKP EC-Ship individual-item REST API specification v1.25 (May 2026) documents a countryCode field (up to 3 characters), France FRA, Hong Kong local HKG, and a Common API GET /countryList/get supplying ctyCode, hkpCtyCode, nameC, nameE and nameS.
- These code lists must NEVER be silently combined, padded or treated as interchangeable. hkpCtyCode is described as a country code zone and is not automatically identical to a destination code.

**Chosen default:** The application emits the APPROVED HKP TWO-CHARACTER POSTAL DESTINATION catalogue under scheme HKP_DESTINATION_2, compiled from and checked against official Hongkong Post source snapshots.

Typical known examples from official material: US = United States, GB = United Kingdom, JP = Japan, SG = Singapore, MO = Macau, TW = Taiwan, TP = Timor-Leste. Their release status and source scope must still be revalidated when assembling the first approved catalogue.

Primary result: HKP_Destination_Code (string or empty). The general classifier MUST support all officially verifiable HKP geographic destination entries rather than be limited to the narrower set eligible for any one product. A separate HKP_Service_Profile check can validate eligibility of the classified destination for a chosen posted service, but is not evidence that the address itself is in another country.

Additional fields may include ISO_Alpha2, ECShip_Country_Code_3, HKP_Zone only when there is an explicitly approved and versioned crosswalk. Do not compute a 3-character code by string transformation. Do not replace HKP TP with ISO TL. Do not reduce separately listed HKP postal destinations (for example Macau, Guam, Puerto Rico) into a geopolitically parent state.

Unknown/unmapped codes leave the code field empty; status and reason describe why. Do not put the literal value UNKNOWN or REVIEW in the country-code column. Any official-source conflict, invalid code, or missing approved mapping returns REVIEW_CODE_MAPPING, with both candidate definitions retained for QC.

### Mapping source-precedence contract

1. Verified official HKP published postal destination codes scoped to the chosen service/profile.
2. HKP Open Data destinationCode / destinationName fields (source-specific coverage, timestamps and service).
3. HKP destination and zone charts as a cross-check; old charts are not proof of current eligibility.
4. If available by authorized export, HKP EC-Ship Common API country list as an independent scheme/crosswalk.
5. ISO, GeoNames, OSM and other geographic sources identify locations but do not override HKP codes.

Every catalogue row must store source URL, document name/version, section, retrieved/reviewed dates, effective range if published, approval status and checksum. If current sources cannot be accessed or verified, their codes do not become automatically approved simply because they appear in a search result or old chart. HKP catalogue updates are versioned, reviewable, atomic, and independently tested.

## 3. Data and software architecture

Recommended baseline: Python 3.12+, PySide6 Windows GUI, SQLite indexed data store (including optional FTS5 for candidate retrieval), openpyxl read-only Excel input, streaming CSV/TXT reader, pytest, optional PyInstaller release build.

Separate modules:

- Input adapter and schema mapper: CSV, XLSX, TXT -> ordered logical address records.
- Address normalizer: Unicode, encodings, punctuation, word segmentation, language aliases, abbreviations and multi-line joining; preserve unmodified input.
- Candidate retriever: indexed exact/alias city/admin/country/place lookup; never full scan of every global place per address.
- Postal region validator: optional offline postcode patterns and country/admin/context; never infer a unique country from a generic postcode alone.
- Evidence/scoring engine: geographic hierarchy consistency, conflict handling, explainable matches, calibration.
- HKP destination resolver: mapping against the approved HKP_DESTINATION_2 version, optionally checks service-specific membership.
- Review and override engine: operator changes logged by record ID, evidence and rule version; review does not change other rows silently.
- Reporting: detailed row export, destination counts, review file, version/run manifest and hashes.
- Batch controller: bounded memory, background workers, cancellation and checkpoint/restart.
- Offline data pack manager: atomic installation, version, checksum, schema compatibility, licenses and provenance.

Suggested SQLite tables: hkp_destinations, hkp_destination_aliases, destination_crosswalks, destination_service_memberships, geo_places, geo_aliases, place_hierarchy, postal_patterns, street_evidence, building_evidence, data_pack_manifest, classification_runs, classification_evidence, review_decisions, run_checkpoints. Indexed lookup should use normalized tokens, location IDs, destination IDs and parent administrative hierarchy, rather than fuzzy-matching every record globally.

### Reference data packs

Core global pack: reviewed HKP destinations, crosswalks, GeoNames worldwide countries/admin divisions/populated places/multilingual aliases, and curated name rules. GeoNames is strong for geography but not exhaustive for buildings. Optional region packs: postal patterns, OSM street/building data, OpenAddresses where redistribution is permitted. Permit incremental regional install without rebuilding the whole world pack.

Data preparation and production runtime are separate tools. Source manifest captures provenance URL, retrieval timestamp, license, attribution, checksum, schema transform version, record count and geographic coverage. GeoNames CC BY, OSM ODbL, and individual OpenAddresses license terms must be checked before packaging/distribution. No assumption that a global commercial-ready building database is freely available.

## 4. Address inference and safety rules

Pipeline: read -> normalize -> generate destination candidates -> confirm city/admin hierarchy -> validate supporting postcode evidence -> optionally check regional street/building evidence -> detect conflict -> assign confidence/status -> resolve approved HKP code -> export.

Evidence priority:
1. Explicit unambiguous destination in a structured field or clear country token with proper word boundaries.
2. Compatible country, province/state, city and locality relationships from geospatial data; multiple independent consistent clues strengthen a hypothesis.
3. Region-specific postal code context (supporting evidence; not by itself unique worldwide).
4. Street and building evidence only when connected to locality/admin/destination records.
5. A lone ambiguous city/street name is not sufficient. Do not match a substring of a company, recipient name or road to a country name.

Scoring must handle negative evidence and competing hypotheses; counting correlated aliases multiple times must not raise confidence artificially. Calibrate release thresholds using labeled address samples, not arbitrary apparent certainty.

Status enumeration:
- MATCHED: clear evidence and approved HKP code.
- REVIEW_AMBIGUOUS: multiple credible destinations.
- REVIEW_CONFLICT: contradictory evidence (e.g. supplied country and geography differ).
- REVIEW_CODE_MAPPING: geography identified but HKP output code unapproved/missing/inconsistent.
- UNKNOWN: insufficient evidence.
- INPUT_ERROR: record input cannot be safely decoded/parsed.

Illustrative acceptance fixtures:
- 10 Bayfront Avenue, Singapore -> candidate SG; MATCHED if mapping is approved.
- Shinjuku-ku, Tokyo 160-0022 -> candidate JP using contextual matching.
- London Road, Mumbai, India -> IN, not GB.
- Main Street, Springfield -> REVIEW_AMBIGUOUS or UNKNOWN, not guessed.
- Macau -> MO; not collapsed to CN.
- Timor-Leste -> HKP TP under an approved applicable official snapshot; not automatic ISO TL.
- Guam / Puerto Rico -> distinct HKP destinations if source snapshot confirms GU / PR.
- Two contradictory explicit countries -> REVIEW_CONFLICT.
- France FR versus EC-Ship FRA; Hong Kong HK versus EC-Ship HKG -> do not confuse schemes.

These are design test cases, not evidence of working program code.

## 5. File input, outputs and precise reconciliation

CSV/TXT encoding: UTF-8 (with/without BOM), Big5, explicitly chosen encodings; decoding errors require operator-visible errors instead of silent replacement. CSV quoted embedded newlines count as ONE logical record. TXT record boundary must be configured (single line, delimiter, fixed format) before classification. XLSX read-only mode; allow worksheet selection and column mapping. Support one combined address field or multiple address lines, country, region, city and postcode. Keep original input record ID, file, row number, column values and order.

Default output format: UTF-8 BOM CSV for large jobs; XLSX only within worksheet row limits or explicitly split across sheets/files.

Detailed output appends:
- Source_File, Source_Sheet, Source_Record_No, Record_ID.
- HKP_Destination_Code, Destination_Name_EN, Destination_Name_TC.
- Classification_Status, Confidence_Level, Confidence_Score.
- Match_Method, Match_Evidence, Review_Reason.
- HKP_Catalogue_Version, Geo_Pack_Versions, Rules_Version.
- Optional verified ISO_Alpha2, ECShip_Country_Code_3 and HKP_Zone.

Additional files: Country_Summary.csv (HKP code + count), Manual_Review.csv (all non-MATCHED records), Run_Manifest.json (file hashes, totals, versions, import settings and processing outcome), optional audited Review_Corrections.csv.

**Hard reconciliation requirements**:
- Imported logical record count = MATCHED + REVIEW_AMBIGUOUS + REVIEW_CONFLICT + REVIEW_CODE_MAPPING + UNKNOWN + INPUT_ERROR.
- Sum of HKP per-destination counts = MATCHED count; all non-MATCHED records are separately counted.
- Repeated identical addresses still represent separate mail pieces; deduplication cache speeds matching but must never collapse mail piece totals.
- Explicitly configured quantity-of-items field (if any) produces separate total mail-piece count, not implicit dedup.
- Exact output row ordering and input field preservation; errors do not silently drop rows.
- CSV/Excel formula injection is handled through an explicit protected spreadsheet-view export mode. Machine-readable files maintain predictable documented quoting/escaping.

## 6. Scale, reliability, and offline delivery

Process input in bounded chunks; pre-index global data; cache normalized matches keyed by data/rule version; parallelize only if output order and counting remain deterministic. Production checkpointing records input identity, run versions, shard hashes, counts and last committed logical record; never mark an incomplete run as complete. Restart after cancellation or crash must not repeat committed rows or distort totals. Configure safe temp storage, disk-space checks, cleanup and customer-data retention.

Benchmark 100,000, 1,000,000 and 5,000,000 logical records with representative international address distribution and privacy-safe synthetic/permissioned samples. Report memory peak, rows/sec, MATCHED precision, ambiguous/unknown rates by destination and language, checksum reconciliation, cancellation/resume and Windows offline packaged startup. Performance/accuracy promises require actual measurements.

GUI sections: Import (mapping and encoding preview), Data Packs (versions and licenses), Classification Jobs (start/pause/cancel/resume and diagnostics), QC Review (candidates and evidence), Results (destination totals and exports). GUI and optional CLI must use the identical core pipeline.

## 7. Acceptance criteria, tests and development phases

A test-first implementation must cover:
1. HKP TP vs ISO TL and FR vs FRA / HK vs HKG scheme separation.
2. Postal territory independence: Macau, Guam, Puerto Rico, Taiwan as published in HKP source.
3. Country explicit/implicit inference, alias boundaries, international city duplicates, postcode collisions and contradictory fields.
4. UTF-8/Big5/multilingual inputs, invalid bytes, multiline CSV, TXT boundaries, XLSX sheets, blank/error records.
5. Input-output order, repeated addresses, millions of rows, checksum/count conservation, formula safety.
6. Invalid/expired source packs, approved version pinning, source conflicts and service membership distinctions.
7. Cancel/resume/crash at batch boundaries and atomic output writes.
8. System network blocked: import, classify, review, export all work offline.
9. Labeled multilingual gold-set evaluation, precision and review coverage, regression tests.
10. Clean Windows offline packaged build with all required data assets.

Delivery stages after approval:
- Phase 1A: Build/review official HKP_DESTINATION_2 master from accessible authoritative source snapshots; versioned code profiles, source manifest and test fixtures. If source access blocks validation, report exact missing entries rather than fabricating them.
- Phase 1B: GeoNames import/index, aliases, normalization, candidate scoring and classification statuses.
- Phase 1C: CSV/XLSX/TXT input, reconciled output, summary, basic PySide6 GUI, QC review and offline automated tests.
- Phase 2: optional licensed regional postcode/street/building packs and expanded languages.
- Phase 3: large-job performance, reliable checkpoint/resume, Windows packaged release with full regression.
- Phase 4: separate verified postal-service destination/zone profiles, production audit and operator rules.

**Approval gate:** This file is the architectural specification. User review/approval is required before invoking Superpowers writing-plans or implementing product code. Next step after approval: implementation plan with exact tasks, tests, interfaces and order.

## 8. Official source references checked 2026-10-22

- HKP EC-Ship Bulk Mail API Specification v1.23 (Appendices D/E/F): https://ec-ship.hongkongpost.hk/API-portal/Bulk_API_Specification.pdf
- HKP EC-Ship REST API Specification v1.25, last updated May 2026 (countryCode; countryList/get): https://ec-ship.hongkongpost.hk/API-portal/EC-Ship_API_Specification_Restful.pdf
- HKP destination and zone chart (historical codes and territory examples): https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf
- HKP Open Data postage destinationCode schema: https://www.hongkongpost.hk/opendata/DataDictionary/en/DataDictionary_PostageRate.pdf
- HKP ordinary air service/eligibility (not code identification): https://www.hongkongpost.hk/tc/sending_mail/other_destinations/air/ordinary/index.html
- GeoNames: https://download.geonames.org/export/dump/
- OSM license: https://www.openstreetmap.org/copyright
- OpenAddresses: https://openaddresses.io/

**Evidence limitation:** Relevant official documents/indexed text were reviewed, but some direct official PDFs/JSON assets could not be fetched for row-level master import. Compiling and verifying the actual full HKP code master is explicitly a first implementation prerequisite and has NOT yet been completed.
