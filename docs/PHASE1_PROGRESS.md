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

No network is required for preview; classification source/version integrity is separate and must be verified before launch. **An independent Subagent review, a Windows runtime test and a real GeoNames import have now happened (see the dated sections below). CI verification, official master audit and actual delivery accuracy benchmark still have not.**

## Release blockers

1. Verify full official current HKP two-letter code master with reviewed source mapping and service context, including territories differing from ISO.
2. ~~Build genuine GeoNames COMPACT/EXTENDED datasets and measure file sizes.~~ **DONE for size and integrity** (real packs built, SHA-256 verified, measured in `docs/benchmarks.md`). **STILL OPEN:** matching quality, Chinese name coverage and rural-place recall need a labelled gold set.
3. Fix all high-risk matching/alias ambiguities found from labeled real samples.
4. Finish full batch runner, resume/checkpoint, QC/manual review interface, GUI, and end-to-end exports.
5. Run independently reviewed full regressions, 100k/1m/5m records tests, and packaged fully-offline Windows validation.

**Do not merge or use this branch for live mailing production yet.**


## 2026-10-23 — Task 11 resumable offline runner update

Implemented Python run_job/resume_job, CLI classify/resume, atomic per-batch JSONL checkpoints with SHA256 filenames, input/HKP/GeoNames version fingerprinting, and manifest-last CSV reporting. Reference-data audit gate refuses production processing unless independently approved. Synthetic test mode requires an explicit --test-only flag, and exports are marked TEST_ONLY_UNVERIFIED.

Local Python 3.13/Linux full regression: 70 passed; compileall passed. Integration checks cover 5-line CSV mapping, exact record count, source control preservation, summaries, ambiguous QC, pause/resume, modified sources/packs and tampered shard rejection, malformed CSV and mid-run file mutation. New/changed source and tests were uploaded to the GitHub development branch and their Git object SHAs checked.

User-supplied AAAAA.csv was previewed locally: 9,604 records, 12 columns, zero decoding errors, one nonempty unnamed column. No actual private addresses or control numbers have been committed. A synthetic 6-record run paused after 3 and resumed successfully with TEST_ONLY_UNVERIFIED output.

Remaining release gates: manually reviewed complete HKP destination catalogue, genuine GeoNames packs and size/accuracy measurements, stronger geopolitical/admin disambiguation, Windows GUI/QC, high-volume benchmark, proper plaintext-checkpoint retention protection, and independent security/code review.

## 2026-10-23 — Priority 0 and Priority 1 milestone (Codex)

**Status: IN PROGRESS — STILL NOT PRODUCTION READY.** An independent security
audit found three P0 defects, including a path that asserts a postal code for a
destination that was never reviewed. See `docs/SECURITY_AUDIT_2026-10-23.md`.

### Priority 0 — baseline and independent safety review

- Baseline re-established on Windows 11 / Python 3.13.2 at commit `4fff20c`:
  `python -m pytest -q` → 72 passed, 0 failed; `python -m compileall -q src
  tools` → clean. The same suite was previously only ever run on Linux.
- A Windows-only defect was found and fixed before any further work: `with
  sqlite3.connect(...)` scopes the transaction, not the connection, so the file
  handle stayed open and every reference-database install failed on Windows
  with `WinError 32`. 37 tests failed for this single reason. Fixed in
  `aa9c522`; all 72 then passed. A `windows-latest` CI job was added in
  `4fff20c`, because both existing workflows ran only on `ubuntu-latest`.
- Independent read-only subagent audit completed: 12 findings (3 × P0,
  6 × P1, 3 × P2) plus a builder defect, with executable probes. Recorded in
  `docs/SECURITY_AUDIT_2026-10-23.md` with file/line evidence and triage.

### Priority 1 — the real worldwide databases are secured and verified

Artifact `12447987288` (expiry 2026-10-29) and report artifact `12447817791`
were downloaded from run `39827512415` before expiry and preserved locally
under `builds/real-2026-10-22/` and `packs/`.

- Artifact digest verified: `56a23683a48092c4055241b56b0762ee8aa86041831fbff74b393fc94a5ffef3`.
- The archive contains **both** nested database packages, not a truncated
  single database: `compact_global.sqlite.zip` 56,535,390 bytes and
  `extended_global.sqlite.zip` 423,280,495 bytes.
- Uncompressed SQLite SHA-256 matches the published fingerprints exactly:
  `e3b8b710…faa2d2d` (COMPACT) and `fb0e4774…a2074a` (EXTENDED).
- `PRAGMA integrity_check` returns `ok` for both. Schema, place counts, alias
  counts, alias language distribution and index usage all match the build
  report. 253 distinct countries; only `A` and `P` feature classes present.
- Measured sizes: COMPACT 143,949,824 bytes (137.281 MiB), EXTENDED
  1,098,661,888 bytes (1,047.766 MiB). Lookup p95 0.264 ms / 0.317 ms warm.
  Full detail in `docs/benchmarks.md`.
- **Builder/installer format mismatch fixed.** The builder published
  `<profile>.sqlite` while `pack_registry` expected `pack.db` beside
  `manifest.json`. Added deterministic per-pack manifests, `stage_pack`,
  `install_pack` and `tools/install_reference_pack.py`; both real packs now
  install offline, verify, and stay queryable.
- New `tests/integration/test_real_geonames_packs.py`: 15 tests against the
  real databases, skipped automatically when the artefacts are absent.

### New blockers revealed by the real data

- The prototype score model saturates on real data. In `EXTENDED_GLOBAL` the
  single token `springfield` matches 68 place ids in `US`, 15 in `GB`, 12 in
  `JM`, 9 in `AU`, 7 in `CA`, 5 in `ZA` and 4 in `IE`; `berlin` saturates
  across 17 countries. Every one of those scores `0.99`, so the model can no
  longer discriminate and a lone city token can still reach `MATCHED`.
- Alias language provenance is lossy because of the `UNIQUE (place_id,
  search_key)` constraint and insert order; the report understates real
  English and Chinese coverage. Matching is unaffected.
