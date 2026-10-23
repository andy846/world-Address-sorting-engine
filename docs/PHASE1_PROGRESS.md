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

## Milestone 2 — geographic classification accuracy (2026-10-23)

Commits `525e0e2` (evidence-mass model) and `63d2c32` (alias provenance).

### What changed

The place-count score (`0.35 + 0.26 * rows`) is gone. Evidence is now a
weighted mass per destination in which **each search term contributes at
most one weight**, however many gazetteer rows the term matches. A country
entity weighs 0.60, an `ADM1` 0.26, an `ADM2` 0.16, deeper administration
0.08, and a populated place `0.26 * min(1, log10(pop+1)/6)`. Places with no
population carry no evidence.

A destination is assertable only when `support >= 0.15` **and** it either
has two independent search terms or is a country entity. Company names are
withdrawn from the evidence before any decision is taken. A structured
country field is trusted unless the address text contradicts it.

### Audit findings closed

P0-2, P0-3, P1-5, P1-6, P1-7 and builder defect A1. The before/after probe
table is in `docs/SECURITY_AUDIT_2026-10-23.md`.

### Verified against the real packs

`tests/integration/test_real_geonames_classification.py` runs 67 cases
against **both** published databases and is skipped when they are absent.
Measured outcomes against `EXTENDED_GLOBAL`:

| Address | Result |
|---|---|
| `London Road, Mumbai, India` | `MATCHED IN` |
| `10 Bayfront Avenue, Singapore` | `MATCHED SG` |
| `Shinjuku-ku, Tokyo 160-0022` | `MATCHED JP` |
| `Macau` / `Macao` | `MATCHED MO` |
| `Timor-Leste` | `MATCHED TP` |
| `Springfield, Illinois` | `MATCHED US` |
| `Berlin, Germany` / `Paris, France` | `MATCHED DE` / `MATCHED FR` |
| `Hong Kong` / `香港` | `MATCHED HK` |
| `Guam` / `Puerto Rico` | `MATCHED GU` / `MATCHED PR` |
| `中国北京市朝阳区` / `上海浦东新区` | `MATCHED CN` |
| `St. Louis, Missouri, United States` | `MATCHED US` |
| `Main Street, Springfield` | `REVIEW_AMBIGUOUS`, no code |
| `Tokyo` | `UNKNOWN`, no code |
| `Tokyo` with `Country="US"` | `REVIEW_CONFLICT`, no code |
| `CHINA CONSTRUCTION LTD` | `UNKNOWN`, no code |
| `Jane Doe / CHINA CONSTRUCTION LTD / ...` | `REVIEW_AMBIGUOUS`, no code |
| `北京市 / 中国银行` | `UNKNOWN`, no code |

### Measurements

- Suite: **187 passed** (91 unit + 96 integration, of which 67
  exercise the two real published packs), 0 failures.
- Throughput: 4.07 ms mean per record against `COMPACT_GLOBAL`, 4.33 ms
  against `EXTENDED_GLOBAL` (~240 records/sec, one core, warm cache). See
  `docs/benchmarks.md`; this excludes the reader, exporter and checkpoint,
  and Priority 4 must still add caching and a reused connection.
- Database sizes are unchanged: COMPACT 143,949,824 bytes, EXTENDED
  1,098,661,888 bytes.

### Remaining blockers

- The verified **Hongkong Post** two-character master is still missing
  (Priority 3). Every result above uses `tests/hkp_master_fixture.py`, which
  is explicitly a synthetic fixture and not an official catalogue.
- The P0-1 catalogue self-approval bypass was subsequently replaced with
  a separate signed approval manifest bound to the exact database, source
  evidence and approved destinations. See `docs/data-sources.md`. The full
  official source review and production catalogue remain outstanding.
- Throughput is a single-record cost with no caching (Priority 4).
- Completed 100k / 1M / 5M measurements remain outstanding. A subsequent
  2,000-row smoke measurement and a 129-row labelled synthetic golden set
  are recorded in `docs/benchmarks.md`; neither establishes production
  accuracy or full-size batch performance.

## 2026-10-23 - durable pack release verification

The Priority 1 download, preservation and offline installation gate now has
published release evidence in `docs/PACK_RELEASES_2026-10-23.md`. Both the
original CI k1 databases and current k2 rebuild have separate versioned
prereleases with manifests, hashes and attribution. Each generation passed
39 real-pack tests including full SQLite integrity; all 16 uploaded asset
digests matched. A fresh GitHub download of both k2 profiles was installed
and queried with socket connections denied.

Commits `e8a0549` and `adafeed` were pushed to the development branch. They
bind report/manifest format provenance and make benchmark RSS attributable
to a fresh process. Follow-up `36f991b` fixes an incomplete Han test fixture
(16 passed/1 failed before, 17 passed after). A combined Windows regression
run before the next classifier changes passed 386 tests, with 4 skipped.

Independent pack review approved publication; its two nonblocking metadata
notes were corrected. Independent Windows review found a real QtCore import
failure in the 65,976,817-byte onefile executable plus exclusion/report and
timeout-cleanup gaps. Packaging fixes and nested-name classification fixes
are in progress. No alpha.1 executable or production readiness is claimed.

## 2026-10-23 - Windows packaging and GUI verification follow-up

Committed and pushed `fbaea39` (release completed GUI callbacks) and
`1d042bb` (archive inspection, report-file self-test, packaging dependency
and Windows CI fixes). Independent reviewers accepted both scoped changes.
The callback weakref test was observed failing before the fix and passing
afterward. Two subsequent complete local suites passed (455/4 skipped,
then 457/4 skipped after rule-version checkpoint tests were added); the
previous native access violation did not recur in those runs.

The QtCore bundle failure was traced to Poppler's incompatible ICU DLL on
the inherited PATH. Isolating the builder's Python/Windows DLL search paths
produced a working onefile executable. A rules.4 development snapshot was
48,469,344 bytes (46.224 MiB) and passed the frozen GUI/event, synthetic
9,604-row CSV and one-row XLSX preview, and production approval-refusal
checks. This is startup/preview validation, not a full production mailing
acceptance test or a newly published alpha.1 executable.

GitHub Windows run
[39888768810](https://github.com/andy846/world-Address-sorting-engine/actions/runs/39888768810)
at `1d042bb` succeeded: 284 passed, 122 skipped in 104.36 seconds, including
the enabled real onefile build/self-test. Real database tests skip on that
runner because the packs are not checked into Git. Syntax and console
entry-point checks also succeeded.

Matching changes remain uncommitted pending review fixes. A reviewer found
that longer country entity names could hide independent conflicts, Unicode
punctuation could leave Northern Ireland incorrectly assigned to Ireland,
and repeated-name inputs caused excessive occurrence-processing work. These
are being corrected with regression tests before any matching release.
Rule-version pinning and benchmark child-work-directory isolation are also
under local validation. Full 100k/1M/5M measurements, approved Hongkong Post
master, onedir runtime and clean offline operator acceptance remain open.

## 2026-10-23 - alpha.1 release validation

The preserved k2 data packs remain unchanged: Compact 142,577,664 bytes
(135.973 MiB), Extended 1,087,344,640 bytes (1,036.973 MiB). Their separate
release and offline download/install evidence are in `docs/PACK_RELEASES_2026-10-23.md`.

Since `1d042bb`, commits `d86d571`, `c2fc5fb` and `82325a0` harden checkpoint
verification, cleanup, benchmark ownership and provenance. `4a67073`,
`92c8eb1` and `ec5301c` fix nested names, brand collisions and conflicting
Han geography. `076cc2b` pins exact status, reason and empty-code outcomes.
Independent classifier re-review found no P0/P1/P2 findings in that scope;
its full suite passed 684 tests, with 1 skipped and 2 expected failures.

The clean `ec5301c` benchmark completed 2,000 and 100,000 synthetic rows at
107.2 and 109.7 records/sec, with 47.8 and 56.8 MiB peak RSS. The 100k run
took 911.675 seconds, reconciled all rows, and used 62,057,316 checkpoint
bytes. A second run with changing Git provenance was rejected and excluded.
Full methodology and sizes are in `docs/benchmarks.md`; 1M/5M are unmeasured.

`b32a0bb` attests the running bundle version. A local Windows onefile build
of version `0.1.0a1` is 48,488,511 bytes and passed packaged frozen/version,
GUI event, CSV/XLSX preview and production-approval refusal checks.

Release review found concrete workflow defects: draft lookup through the
published-tag endpoint, upload verification against an unanchored checksum
file, short branch-name checks, and incomplete failure cleanup. Follow-up
tests were observed RED (5 failures/5 passes), then GREEN (12 release tests,
including metadata). The workflow now creates and records a draft ID before
upload, checks full branch refs, compares downloaded checksum files with the
pre-upload copy, and returns failed/cancelled publications to draft by ID.
Alpha.0's commit, asset names, sizes and known digests are checked before
publication. Final local regression with both real k2 packs and slow checks:
**694 passed, 1 skipped, 2 xfailed in 115.52 seconds**. Syntax compilation,
all 22 Linux Bash workflow blocks, all 5 embedded Python blocks, and
`git diff --check` passed. Actual GitHub build/publication evidence must be
recorded after the run finishes.

Ruling: the branch push marker is deliberate publication intent from an
already authorized repository writer, not an independent approval boundary.
Repository-wide immutability and required reviewers are not prerequisites
specified for this TEST ONLY preview; no such platform protection is claimed.
Existing release versions are refused rather than overwritten. If the API
is unavailable during cleanup, manual draft recovery may still be needed.

Ruling: maliciously renamed or nested databases are not comprehensively
detected by header/extension scans. The build additionally inspects the
PyInstaller archive and runtime tree, and only the verified wheel, EXE and
checksum file are uploaded. This is not a content scanner for arbitrary
customer data and relies on the reviewed source/build inputs.

Production remains NO-GO: the official Hongkong Post master is unverified;
the k2 Simplified Chinese Hong Kong SAR alias is missing (two expected-failure
regressions); 1M/5M benchmarks, onedir runtime and clean offline operator
acceptance are outstanding. Alpha.1 is a TEST ONLY prerelease.

