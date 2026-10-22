# Phase 1 implementation progress — 2026-10-23

**Status: IN PROGRESS — NOT PRODUCTION READY**

Development branch: `feat/hkp-trilingual-phase1` (Draft PR #1, not merged). Target: verified Hongkong Post two-letter destination code and English/Traditional/Simplified Chinese address classification without internet access.

## Completed foundations and local prototype modules

- Task 1: immutable record/candidate/result contracts and status invariants.
- Task 2: provenance/format/hash-checked HKP code catalogue; ISO and EC-Ship are separate schemes. **Still missing a complete manually verified current official master.**
- Task 3: two locally built GeoNames profile options, COMPACT_GLOBAL and EXTENDED_GLOBAL, indexing English, selected Chinese and Romanized Latin names.
- Task 4: offline pack hashing and immutable activation.
- Task 5: prototype English/Chinese normalization and unsupported-script checks; curated Chinese name variants (not yet full OpenCC-scale coverage).
- Task 6: bounded SQLite candidate retrieval by place names; full administrative-hierarchy validation and hard real-world cases still need further work.
- Task 7: conservative prototype classifier: source country evidence, weak-geo ambiguity and HKP output guard. Heuristic score is NOT a calibrated accuracy guarantee.
- Task 8: stream CSV/TXT, preserve Control no leading zeros and numbered blank-header columns, detect corrupt input rows.
- Task 9: read-only XLSX adapter, selected sheet and explicit handling for missing cached formula values.
- Task 10: stream detailed result / HKP summary / manual-review outputs, export manifest and count reconciliation; full production input-to-export runner is still outstanding.
- Task 11 (partial): privacy-safe CLI `preview` subcommand only. The production job runner, durable checkpoint/resume and end-to-end classification CLI remain NOT implemented.
- Tasks 12-13: Windows PySide6 GUI, independent final code review, packaging, full offline/volume/DB-size benchmarking NOT complete.

## Real uploaded file format validation (sensitive source not committed)

User-provided `AAAAA.csv`, UTF-8 BOM, 1,203,422 bytes, 9,604 logical records, twelve columns:
five `NAME_ADDRESS_LINE1` through `LINE5`, `Control no`, and six identically blank header cells. All 9,604 rows read without decoding errors. One record has a nonempty extra unnamed cell. Control numbers are unique in the supplied data. Addresses have 2/3/4/5 nonempty lines with respective counts 67 / 2,121 / 3,536 / 3,880.

The sample was used ONLY for structural/integrity preview; no country codes are claimed for the real addresses, and source addresses/control values are not stored in the repository.

## Test and release status

Local Linux/Python 3.13 test-first verification: `python -m pytest -q` — **58 passed**; `python -m compileall -q src` — completed without compilation errors. Remote GitHub source/test blobs newly added were compared against local Git hash-object and matched.

No network is required for preview; classification source/version integrity is separate and must be verified before launch. **No independent Subagent review, CI verification, Windows runtime test, official master audit, real GeoNames import, or actual delivery accuracy benchmark has happened.**

## Release blockers

1. Verify full official current HKP two-letter code master with reviewed source mapping and service context, including territories differing from ISO.
2. Build genuine GeoNames COMPACT/EXTENDED datasets and measure file sizes, matching quality, Chinese name coverage and rural-place recall.
3. Fix all high-risk matching/alias ambiguities found from labeled real samples.
4. Finish full batch runner, resume/checkpoint, QC/manual review interface, GUI, and end-to-end exports.
5. Run independently reviewed full regressions, 100k/1m/5m records tests, and packaged fully-offline Windows validation.

**Do not merge or use this branch for live mailing production yet.**
