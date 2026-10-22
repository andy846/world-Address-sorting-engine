# HK Post Trilingual Offline Address Classifier — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a testable Windows Python MVP which converts CSV/XLSX/TXT address records in English, Traditional Chinese or Simplified Chinese into verified Hongkong Post two-letter postal destination codes, exact destination counts and QC outputs, wholly offline.

**Architecture:** Keep source file adapters, address matching, HKP code resolution and exports as independent modules. Build two self-contained SQLite reference-pack profiles from the same frozen GeoNames snapshot; use approved, independently versioned HKP mapping sources. The GUI/CLI call the same deterministic streaming runner.

**Tech Stack:** Python 3.12+, PySide6, SQLite/FTS5, openpyxl (read-only XLSX), pytest, stdlib CSV and ZIP, deterministic optional offline OpenCC package for Han variants, PyInstaller for Windows release verification.

**Spec:** docs/superpowers/specs/2026-10-22-hkp-offline-global-address-classifier-design.md

**Delivery boundary:** This is the FIRST end-to-end production-oriented MVP slice, not an unbounded claim to fully know every street/building in the world. OSM/OpenAddresses global street/building import, AI, live postal service eligibility and rating remain separate future plans. Code starts only after review/approval of this plan and choice of execution method.

## Global Constraints

- Accept address inputs only in English, Traditional Chinese and Simplified Chinese, including their mixtures, Latin-letter geographic spellings, numbers and postal codes.
- Preserve the full HKP destination master, geographic IDs and hierarchy independently from language alias filtering.
- Default authoritative output scheme is `HKP_DESTINATION_2`; DO NOT use ISO as a substitute. HKP `TP` and ISO `TL` remain distinguishable.
- Code mappings need approved official provenance, version, status and source/checksum. No invented entries or post hoc padding from two to three characters.
- Runtime classification, import, review and exports must function without a network connection.
- Unknown, ambiguous, conflicting or unapproved mappings must never emit an asserted destination code.
- One logical input record produces exactly one output record in input order. Duplicate addresses remain separate mail pieces.
- Unchanged original input fields; full counts reconcile across MATCHED/REVIEW_AMBIGUOUS/REVIEW_CONFLICT/REVIEW_CODE_MAPPING/UNKNOWN/INPUT_ERROR.
- GUI and CLI use the same pure-Python engine; customer data stays local and raw addresses are not logged by default.
- Do not promise database savings, accuracy or performance until benchmarked against the pinned sources and labeled datasets.
- Keep frequent commits, test-first red/green cycles and full regression after each task; no unrelated refactors or feature creep.

## File Structure and Ownership

`pyproject.toml` — dependencies, entrypoints, pytest settings.
`src/world_address_engine/models.py` — stable contracts for input records, candidates, results and job metadata.
`src/world_address_engine/hkp/catalogue.py` — approved HKP catalogue import/lookup, source validation.
`src/world_address_engine/data/geonames_builder.py` — profile-aware GeoNames importer and language alias filtering.
`src/world_address_engine/data/pack_registry.py` — immutable pack manifests, hash checks and atomic activation.
`src/world_address_engine/matching/normalize.py` — normalized EN/ZH text and variant generation.
`src/world_address_engine/matching/retrieve.py` — bounded geographic hierarchy candidate search.
`src/world_address_engine/matching/classify.py` — evidence conflicts, status, code resolving.
`src/world_address_engine/io/delimited.py` — streaming CSV and configurable TXT adapter.
`src/world_address_engine/io/xlsx.py` — read-only XLSX adapter.
`src/world_address_engine/io/reports.py` — row exports, QC files, reconciliation and run manifest.
`src/world_address_engine/jobs/runner.py` — offline streaming orchestration, stable ordering and version pins.
`src/world_address_engine/jobs/checkpoint.py` — safe resumable batch output manifest and write lifecycle.
`src/world_address_engine/cli.py` — batch CLI entry point.
`src/world_address_engine/gui/app.py` — PySide6 desktop workflow and review.
`src/world_address_engine/gui/review_store.py` — per-record audited QC decisions and CSV review log.
`tools/build_reference_pack.py` — offline build command consuming predownloaded source archives.
`tests/fixtures` — tiny pinned, synthetic/license-appropriate source rows and official-code excerpt references.
`tests/unit`, `tests/integration`, `tests/offline` — test units, end-to-end, offline/no-network checks.
`docs/data-sources.md` — approved source records and attribution.
`docs/benchmarks.md` — reproducible database build sizes, latency, memory and coverage measurements.

## Review Focus

Five high-risk cases to be nailed down by tests below:
1. Geographic/code mismatch: Timor-Leste listed as ISO TL but HKP TP -> Task 2 and Task 7 must preserve TP.
2. City/street collision: "London Road, Mumbai, India" -> Task 7 returns IN, not GB.
3. English overseas romanization survives language filtering: "Shinjuku, Tokyo" -> Tasks 3/6 preserve Latin place names even when local names use another script.
4. 1,000,000 repeated input records -> Tasks 9/10 preserve exactly 1,000,000 physical rows/counts, without materializing in memory.
5. Interruption during output write -> Task 11 rejects unfinished exports as completed and resumes without duplicate logical rows.

---

### Task 1: Typed Contracts and Test-First Project Layout

**Files:**
- Create: `pyproject.toml`, `src/world_address_engine/__init__.py`, `src/world_address_engine/models.py`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `AddressRecord(record_no:int, source_file:str, source_sheet:str|None, record_id:str|None, fields:dict[str,str], address_text:str, country_hint:str|None, input_error:str|None=None)`; `DestinationCandidate(destination_id:str, evidence:tuple[str,...], score:float)`; `ClassificationResult(record_no:int, status:str, hkp_code:str|None, confidence:float, reason:str, destination_id:str|None)`.
- Define `STATUSES` as exactly: MATCHED, REVIEW_AMBIGUOUS, REVIEW_CONFLICT, REVIEW_CODE_MAPPING, UNKNOWN, INPUT_ERROR. Only MATCHED can have a nonempty asserted hkp_code. An adapter may yield AddressRecord(input_error=...) only if a logical record boundary is known; classification then returns INPUT_ERROR with no code. If malformed file framing makes logical-record boundaries unknowable, fail and mark the entire job incomplete instead of fabricating records.

- [ ] **Step 1: Write failing test** `test_nonmatched_result_never_contains_asserted_hkp_code` and `test_address_record_keeps_original_fields`; assert constructing a non-MATCHED result with "US" raises ValueError and input fields remain unmodified.
- [ ] **Step 2: Verify RED** Run `python -m pytest tests/unit/test_models.py -v`; expect missing model/validation.
- [ ] **Step 3: Implement minimal contracts** Dataclasses or validated immutable models with explicit types and constraints above; configure package and pytest.
- [ ] **Step 4: Verify GREEN** Re-run targeted tests then `python -m pytest`; require zero failures.
- [ ] **Step 5: Commit** `git add pyproject.toml src tests && git commit -m "feat: add address classifier data contracts"`.

### Task 2: HKP Code Catalogue Loader and Strict Resolver

**Files:**
- Create: `src/world_address_engine/hkp/catalogue.py`, `tests/fixtures/hkp_sample.csv`, `tests/fixtures/hkp_sample_manifest.json`, `docs/data-sources.md`
- Test: `tests/unit/test_hkp_catalogue.py`

**Interfaces:**
- Produces: `import_hkp_catalogue(source_csv:Path, manifest_json:Path, db_path:Path)->int` and `lookup_hkp_code(db_path:Path, destination_id:str, profile:str="HKP_DESTINATION_2")->str|None`.
- Schema: destination_id, code_scheme, code, name_en, name_zh_hant, name_zh_hans, source_url, source_doc_version, source_section, source_checksum, approval_status, profile, date_verified. Store ISO and EC-Ship 3-letter schemes in explicitly separate crosswalk rows.
- Only approval_status APPROVED and unique, non-conflicting scheme+profile+destination mapping are resolvable.

- [ ] **Step 1: Write failing tests** `test_hkp_tp_is_not_iso_tl` (HKP lookup for Timor-Leste equals TP; independent ISO field TL), `test_fra_is_not_bulk_fr` (FR vs FRA), `test_conflicting_approved_rows_are_rejected`, and `test_unapproved_mapping_returns_none`. Fixture records must identify genuine published source/section; never represent an unverified sample as a complete production catalogue.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_hkp_catalogue.py -v`; expect missing loader.
- [ ] **Step 3: Implement minimal importer/lookup** Validate code length, provenance, duplicated conflicting rows, SHA256 manifest and release version; atomic build.
- [ ] **Step 4: Verify GREEN** Targeted suite and complete `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests docs && git commit -m "feat: validate versioned HK Post destination catalogue"`.

**Release gate:** Before any real-world mailing result is labeled approved, build the WHOLE verified HKP two-letter master from current accessible official documents and review every mapping. Tests with tiny excerpts are not equivalent to that requirement.

### Task 3: Trilingual GeoNames Reference-Pack Builder

**Files:**
- Create: `src/world_address_engine/data/geonames_builder.py`, `tools/build_reference_pack.py`
- Test: `tests/unit/test_geonames_builder.py`, `tests/fixtures/geonames_minimal`

**Interfaces:**
- Produces: `build_geonames_pack(source_dir:Path, target_db:Path, profile:str)->dict[str,int]`.
- Accepted `profile` values: COMPACT_GLOBAL and EXTENDED_GLOBAL.
- Inputs: frozen GeoNames countryInfo, admin1/admin2, populated-place rows, optionally cities1000, and alternateNamesV2. Source data must be supplied locally.
- Retain country/admin IDs, parent relationships; index EN aliases, ZH aliases (zh, zh-CN, zh-TW, zh-Hant, zh-Hans if present), vetted source ASCII spelling/romanization; avoid all other language aliases in the production search index. Do not delete geographical hierarchy just because no Chinese alias exists.
- COMPACT_GLOBAL uses country/admin+documented cities1000/major-place inclusion; EXTENDED_GLOBAL uses geographic P/A feature classes and a wider small-town set.

- [ ] **Step 1: Write failing tests** `test_only_en_zh_and_latin_aliases_indexed` (include en/zh-TW/zh-CN/ru/ja aliases; assert ru and ja excluded), `test_romanized_japanese_city_remains_searchable` (Tokyo/Shinjuku Latin rows kept), `test_extended_retains_small_town_missing_from_compact`, and `test_packs_keep_same_destination_ids`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_geonames_builder.py -v`.
- [ ] **Step 3: Implement minimal streaming builder** Avoid in-RAM allCountries/alternateNames materialization, add indexed relational parent keys and collect profile build counts; keep raw source attribution; no world road/building table.
- [ ] **Step 4: Verify GREEN** Targeted suite and complete `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tools tests && git commit -m "feat: build compact and extended trilingual geodata packs"`.

### Task 4: Pack Integrity and Immutable Activation

**Files:**
- Create: `src/world_address_engine/data/pack_registry.py`
- Test: `tests/unit/test_pack_registry.py`

**Interfaces:**
- Consumes: GeoNames/HKP SQLite packs from Tasks 2-3.
- Produces: `verify_pack(db_path:Path, manifest_path:Path)->bool` and `activate_pack(staging_dir:Path, active_root:Path)->Path`.
- Manifest fields: pack_id, profile, pack_version, schema_version, created_at, source_date, source_sha256, db_sha256, record_count, alias_count_by_language, attribution, license.

- [ ] **Step 1: Write failing tests** `test_tampered_db_rejected`, `test_partial_install_never_becomes_active`, `test_manifest_fingerprints_fix_run_sources`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_pack_registry.py -v`.
- [ ] **Step 3: Implement manifest validation and atomic activation** Keep installed previous pack valid on failure; source metadata must be displayed and attributable.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests && git commit -m "feat: verify and activate immutable reference packs"`.

### Task 5: English and Chinese Address Normalization

**Files:**
- Create: `src/world_address_engine/matching/normalize.py`
- Test: `tests/unit/test_normalize.py`

**Interfaces:**
- Produces: `normalize_address(value:str)->tuple[str,...]` (candidate normalized forms, original-preserving), `has_unsupported_script(value:str)->bool`.
- Han variants generated through an offline pinned deterministic converter or equivalent; never rewrite input fields, never treat a converted alias as independent corroboration. Latin casefold and token boundaries are required.

- [ ] **Step 1: Write failing tests** `test_english_case_and_whitespace_normalization`, `test_traditional_simplified_city_variants` (臺北/台北, 廣州/广州), `test_han_romanization_alias_retained`, `test_russian_script_is_not_silently_accepted` and `test_in_substring_does_not_match_india_country_code`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_normalize.py -v`.
- [ ] **Step 3: Implement normalizer and script check** Document conversion dependency/dictionary version; tokenize country abbreviations only on trusted boundaries/context.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests pyproject.toml && git commit -m "feat: normalize English and Chinese address variants"`.

### Task 6: Indexed Geographic Candidate Retrieval

**Files:**
- Create: `src/world_address_engine/matching/retrieve.py`
- Test: `tests/unit/test_retrieve.py`

**Interfaces:**
- Consumes: GeoNames SQLite pack from Task 3 and normalized variants from Task 5.
- Produces: `retrieve_candidates(geo_db:Path, address_forms:tuple[str,...], country_hint:str|None, limit:int=20)->list[DestinationCandidate]`.
- Match country/admin/city through actual parent relationships. A country field on a place must not erase independently represented postal destinations like Macau/Guam/Puerto Rico when the HKP crosswalk says otherwise.

- [ ] **Step 1: Write failing tests** `test_shinjuku_tokyo_proposes_jp`, `test_mumbai_india_does_not_propose_gb_from_london_road`, `test_springfield_without_other_context_is_ambiguous`, `test_only_twenty_candidates_returned` and `test_admin_hierarchy_prevents_false_link`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_retrieve.py -v`.
- [ ] **Step 3: Implement SQL-indexed candidate lookup** Query indexed normalized names and disambiguate with parent IDs; preserve evidence and source IDs, cap number of returned destination hypotheses.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests && git commit -m "feat: retrieve geographically consistent destination candidates"`.

### Task 7: Deterministic Classifier and Conflict Policy

**Files:**
- Create: `src/world_address_engine/matching/classify.py`
- Test: `tests/unit/test_classify.py`

**Interfaces:**
- Consumes: `AddressRecord`, `retrieve_candidates`, `lookup_hkp_code`.
- Produces: `classify_record(record:AddressRecord, geo_db:Path, hkp_db:Path)->ClassificationResult`.
- Initial conservative policy: a unique explicit unambiguous destination yields MATCHED if official mapping valid and no conflicting location evidence; otherwise an independently consistent city+admin/country pair may be MATCHED; isolated ambiguous city, street or postcode MUST NOT be auto-assigned. Scores are diagnostic only until separately calibrated.

- [ ] **Step 1: Write failing tests** `test_london_road_mumbai_india_is_in`, `test_springfield_does_not_guess`, `test_conflicting_explicit_countries_review`, `test_verified_macau_is_mo_not_cn`, `test_timor_leste_is_tp_not_tl`, `test_unapproved_hkp_code_never_asserted`, `test_bad_input_record_returns_input_error`, and `test_unsupported_script_has_review_reason`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_classify.py -v`.
- [ ] **Step 3: Implement transparent rule-based evidence resolution** Explicit statuses, method/evidence reason, confidence metadata and approved-code guard; do not fit weights to desired sample answers.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests && git commit -m "feat: classify postal destinations with conservative conflict checks"`.

### Task 8: Streaming CSV/TXT Import and Schema Mapping

**Files:**
- Create: `src/world_address_engine/io/delimited.py`
- Test: `tests/unit/test_delimited.py`

**Interfaces:**
- Produces: `iter_csv_records(path:Path, encoding:str, address_columns:tuple[str,...], record_id_column:str|None=None)->Iterator[AddressRecord]` and `iter_txt_records(path:Path, encoding:str, mode:str, delimiter:str|None=None)->Iterator[AddressRecord]`.
- Explicit TXT modes: line and delimited. CSV RFC-style quoting, embedded newline as one logical record, UTF-8 BOM/Big5 selection, unreadable byte errors visible.

- [ ] **Step 1: Write failing tests** `test_multiline_csv_is_one_logical_record`, `test_big5_chinese_round_trip`, `test_utf8_bom_header`, `test_bad_bytes_report_input_error_without_drop_when_record_boundary_is_known`, `test_unrecoverable_csv_framing_marks_job_incomplete` and `test_txt_delimiter_defines_record_boundary`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_delimited.py -v`.
- [ ] **Step 3: Implement bounded-memory iterators** Preserve source row, original fields and stable logical row ID; expose recoverable record parse failures as AddressRecord(input_error=...), and fail the entire job safely if invalid framing prevents establishing trustworthy logical-record boundaries.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests && git commit -m "feat: ingest CSV and TXT addresses without losing records"`.

### Task 9: Read-Only XLSX Adapter

**Files:**
- Create: `src/world_address_engine/io/xlsx.py`
- Test: `tests/unit/test_xlsx.py`

**Interfaces:**
- Produces: `iter_xlsx_records(path:Path, sheet_name:str, address_columns:tuple[str,...], record_id_column:str|None=None)->Iterator[AddressRecord]` using openpyxl read_only=True, data_only=True with explicit cached-formula handling policy.

- [ ] **Step 1: Write failing tests** `test_sheet_selection_and_column_mapping`, `test_blank_rows_do_not_shift_record_ids`, `test_formula_without_cached_value_is_input_error_using_readonly_formula_check` and `test_xlsx_reader_is_iterator_not_materialized_list`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_xlsx.py -v`.
- [ ] **Step 3: Implement XLSX reader** Enforce Excel row constraints, preserve sheet/source/row metadata and original non-address columns. If data_only=True yields no cache for a required field, use a parallel read-only formula check or a clear conservative missing-required-cell error: never silently interpret a formula without a cached value as an empty address.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests && git commit -m "feat: stream address rows from selected Excel worksheet"`.

### Task 10: Detailed Export and Exact Destination Statistics

**Files:**
- Create: `src/world_address_engine/io/reports.py`
- Test: `tests/unit/test_reports.py`

**Interfaces:**
- Consumes: `Iterator[tuple[AddressRecord,ClassificationResult]]`.
- Produces: `write_reports(items:Iterator[tuple[AddressRecord,ClassificationResult]], output_dir:Path, run_metadata:dict)->dict[str,int]`.
- Required results: Classified_Addresses.csv (default Excel-safe original-value display), Country_Summary.csv, Manual_Review.csv, Run_Manifest.json; optional Classified_Addresses.machine.csv preserves exact unmodified field values with an explicit spreadsheet-import warning. Use UTF-8 BOM for Excel-facing view; escape formula-leading text for spreadsheet consumers in that view only. Record export mode in manifest. Report file hashes and versions.

- [ ] **Step 1: Write failing tests** `test_summary_counts_equal_matched_rows`, `test_review_rows_not_assigned_codes`, `test_duplicate_address_rows_count_twice`, `test_spreadsheet_formula_injection_is_neutralized_in_excel_view`, `test_machine_mode_keeps_exact_original_string` and `test_original_columns_and_order_preserved`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/unit/test_reports.py -v`.
- [ ] **Step 3: Implement streaming writer and reconciliation** Require sum(status totals)==input count, sum(destination totals)==MATCHED; refuse complete manifest if not equal.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests && git commit -m "feat: export reconciled HK Post destination statistics"`.

### Task 11: Job Runner, CLI and Crash-Safe Output State

**Files:**
- Create: `src/world_address_engine/jobs/runner.py`, `src/world_address_engine/jobs/checkpoint.py`, `src/world_address_engine/cli.py`
- Test: `tests/integration/test_job_runner.py`

**Interfaces:**
- Consumes: iterators (Tasks 8/9), classifier (Task 7), reporter (Task 10), pinned packs (Task 4).
- Produces: `run_job(input_path:Path, output_dir:Path, geo_db:Path, hkp_db:Path, input_options:dict, batch_size:int=10000)->dict[str,int]`; `resume_job(run_dir:Path)->dict[str,int]`; CLI `world-address-engine classify --input FILE --geo-db FILE --hkp-db FILE --output DIR --address-column NAME` (configurable optional parameters).
- Use durable committed-batch shards and a run state marker; on resume, verify input hash/version/selected input options, continue only after last committed logical record. Never claim completed while output is partial.

- [ ] **Step 1: Write failing tests** `test_csv_end_to_end_counts`, `test_repeated_million_rows_preserves_count` (slow-marked integration test), `test_interrupted_batch_resume_without_duplicates`, `test_mismatched_pack_rejects_resume` and `test_missing_approved_master_refuses_production_label`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/integration/test_job_runner.py -v -m "not slow"`.
- [ ] **Step 3: Implement bounded streaming runner and durable shard checkpoints** Prefer single worker initially for deterministic behavior; avoid speculative multiprocessing until benchmarks justify it. CLI reuses runner without GUI imports.
- [ ] **Step 4: Verify GREEN** Targeted fast suite, `python -m pytest` then explicit slow integration command on CI-capable hardware.
- [ ] **Step 5: Commit** `git add src tests pyproject.toml && git commit -m "feat: run resumable offline classification jobs"`.

### Task 12: PySide6 Desktop GUI, Quality Review and Export

**Files:**
- Create: `src/world_address_engine/gui/app.py`, `src/world_address_engine/gui/review_store.py`
- Test: `tests/integration/test_gui_workflow.py`

**Interfaces:**
- Consumes: `run_job`, `resume_job`, installed pack manifests, country candidates/results; GUI keeps only bounded preview data in RAM.
- GUI surfaces: Import file/encoding/sheet/column mapping, select Compact/Extended pack, job controls and progress, destination counts, non-MATCHED review cases, approved-code manual override with reason, export and source version display.
- Review decisions must be traceable per input record with operator, time and reason; never silently modify unrelated same-address rows.

- [ ] **Step 1: Write failing tests** `test_gui_import_map_classify_export` (offscreen Qt), `test_gui_shows_unsupported_language_review`, `test_review_override_changes_one_record_only`, `test_review_decision_is_audited` and `test_gui_does_not_block_main_thread_on_large_job`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/integration/test_gui_workflow.py -v`.
- [ ] **Step 3: Implement thin GUI around runner and review store** Worker signals update UI; no direct SQL/HTTP in widgets; export audited corrections and regenerate reconciliation.
- [ ] **Step 4: Verify GREEN** Targeted suite then `python -m pytest`.
- [ ] **Step 5: Commit** `git add src tests && git commit -m "feat: add offline address classification desktop UI"`.

### Task 13: Offline Release Validation and Empirical Database Size Comparison

**Files:**
- Create: `tests/offline/test_no_network.py`, `tests/integration/test_pack_sizes.py`, `docs/benchmarks.md`
- Test: above files and end-to-end CLI/GUI smoke commands; packaged Windows app check.

**Interfaces:**
- Consumes: all earlier tasks. Comparison profiles: unfiltered aliases baseline (benchmark-only), COMPACT_GLOBAL, EXTENDED_GLOBAL; same frozen GeoNames snapshot for all.
- Metrics: source row count, indexed place count, English alias count, Chinese alias counts by variant, count of discarded language aliases, raw source bytes, packed reference DB bytes, VACUUMed installed DB bytes, disk footprint incl FTS indexes, sample lookups/sec, 100k/1m/5m job throughput, peak RAM, gold-label precision/coverage and review rate for EN/ZH-Hant/ZH-Hans. Measure distinct rural/small-town cases.

- [ ] **Step 1: Write failing tests** `test_all_processing_functions_succeed_with_network_blocked` (socket access raises if called), `test_source_manifest_honors_profile_and_chinese_aliases`, `test_reference_pack_build_is_reproducible` and `test_incomplete_run_never_exports_completed_manifest`.
- [ ] **Step 2: Verify RED** `python -m pytest tests/offline tests/integration/test_pack_sizes.py -v`.
- [ ] **Step 3: Implement reproducible benchmarks + Windows release process** Generate documented measurements rather than estimated percentage savings. Run PyInstaller and a clean offline Windows startup/export smoke test; include required data packs, proper license attribution and crash-safe temp cleanup.
- [ ] **Step 4: Verify GREEN** Run `python -m pytest` with zero failures; run `python -m pytest -m slow` separately; verify Windows packaged executable on a clean offline machine, including export and integrity manifests. Report any unverified test/hardware limitation without a completion claim.
- [ ] **Step 5: Commit** `git add tests docs && git commit -m "test: verify offline deployment and multilingual pack sizes"`.

## Verification and Scope Self-Review

Coverage map: HKP standard (Tasks 2/7), offline/approved packs (Tasks 3/4/13), trilingual matching (Tasks 3/5/6/7), input formats (Tasks 8/9), per-line outputs/stats/QC (Tasks 10/12), large-scale resilience (Tasks 10/11/13), GUI (Task 12), licenses/provenance (Tasks 2/3/4/13), full Windows release (Task 13). Street/building packs, live postal rates and expanded service profiles are explicitly future-project plans, not hidden MVP acceptance claims.

The most dangerous operational gap remains FULL, up-to-date HKP two-character catalogue verification. **Do not ship/claim complete global HKP coverage until every master entry has a sourced approval state and the coverage audit passes.** Measured database-size savings and classification accuracy remain unknown until Task 13.

After every task run the complete test suite; when a failing test is added, first observe a justified RED failure, then GREEN, then commit. End with full-regression results and source/provenance manifest.

## Execution Handoff (not yet approved for coding)

Review this plan and choose:
- **Subagent-driven (recommended):** independent implementation and review per task; stronger controls around postal codes, reconciliation and licensed datasets.
- **Native:** one implementer completes tasks in order, then independent final review; lower overhead but less intermediate review.

Implementation only after user acceptance of this specific plan and execution method. No product code was authored by writing this document.
