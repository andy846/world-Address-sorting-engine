# Codex Execution Handoff — World Address Sorting Engine

> **Integration update (2026-10-23):** After the verified alpha.1 release,
> the user explicitly authorized merging the development branch through
> PR #1 into `main`. This supersedes the historical Draft/no-merge directions
> below. Production acceptance gates and existing release identities remain
> unchanged. See `docs/releases/v0.1.0-alpha.1-validation.md` for release evidence.

> **Current date:** 2026-10-23  
> **Repository:** `andy846/world-Address-sorting-engine` (PRIVATE)  
> **Work branch:** `feat/hkp-trilingual-phase1`  
> **PR:** https://github.com/andy846/world-Address-sorting-engine/pull/1 (DRAFT; DO NOT MERGE)  
> **Published preview:** https://github.com/andy846/world-Address-sorting-engine/releases/tag/v0.1.0-alpha.0  
> **Governing spec:** `docs/superpowers/specs/2026-10-22-hkp-offline-global-address-classifier-design.md`  
> **Approved 13-task plan:** `docs/superpowers/plans/2026-10-23-hkp-trilingual-mvp-implementation.md`

## Mission

Continue from **the current code and successful real-data GeoNames build**, not from zero. Deliver a safe, reproducible, fully offline Windows application that classifies large CSV/XLSX/TXT datasets containing English, Traditional Chinese and Simplified Chinese addresses into **approved, two-character Hongkong Post destination codes**, and produces exact per-destination counts and manual QC outputs. Do not label anything production-ready before the official postal catalogue, matching quality and release gates pass.

Follow the accepted Superpowers plan, but mark tasks already implemented as *prototype, requiring review and integration*, rather than reimplementing them. Use test-driven development (fail first, pass next); commit small coherent changes; run the full suite after each task. If Codex exposes subagents, use a fresh implementer and independent spec+quality reviewer per task, then a final whole-diff review. If the multi-agent interface is not available, explicitly record that review gap. Do not start unnecessary new branches, rewrite the published alpha tag, or merge to `main` without user authorization.

## Evidence-backed handoff baseline — VERIFIED ON GITHUB

- GitHub Actions global build: **success**, run **39827512415**, originating commit **929bbe6ec6e58af5c230d4f80979434371945b37**. Full source: https://github.com/andy846/world-Address-sorting-engine/actions/runs/39827512415
- Source archives in that run:
  - `allCountries.zip`: 422,156,786 bytes, SHA256 `4b8a10021d69736be2f78b75cbd6f49648f50bcd90da117cc1c4f84767725182`
  - `alternateNamesV2.zip`: 204,950,999 bytes, SHA256 `1ea8afef7da35370529cd2f7c38caac78e821ca3578f18f0207e5c31ee81fb05`
  - `cities1000.zip`: 11,077,563 bytes, SHA256 `9d3916f7a9448bb4ea45e93c06c5413d2cceb1a89e03f75c2178bbb08af12018`
- **COMPACT_GLOBAL**: 715,567 places; 997,281 aliases; **143,949,824 SQLite bytes (137.281 MiB)**; compressed archive **56,535,390 bytes (53.916 MiB)**; DB SHA256 `e3b8b710e7acf05e0fe3618abecc5745d13d07a7826ae1f2a41767561faa2d2d`.
- **EXTENDED_GLOBAL**: 5,776,152 places; 8,126,852 aliases; **1,098,661,888 SQLite bytes (1,047.766 MiB)**; compressed archive **423,280,495 bytes (403.672 MiB)**; DB SHA256 `fb0e4774cc360ec5fe7b22d2b8176feea031abf02a6277dc42a3877c9da2074a`.
- CI uploaded **`geonames-global-sqlite-zips`** artifact ID **12447987288** (artifact ZIP 479,816,193 bytes; expiry **2026-10-29 18:11 UTC**) and **`geonames-size-build-report`** artifact ID **12447817791** (expiry **2026-11-05 18:11 UTC**). These expiries are critical.
- Both source and built database packs are real-data, NOT synthetic examples. Build success and SQLite integrity verification are not yet evidence of correct postal classification, full territory coverage, runtime performance, or HKP code correctness.
- Preview version **v0.1.0-alpha.0** is already a GitHub **pre-release**; published via successful CI run **39829490315**, tag commit **41497d682207c945a1fb54fcb8d4d9155cbdad7f**. The release attaches the ~26KB pure-Python wheel and SHA256SUMS.txt, but **does not attach either full GeoNames database**. The release job's regression suite passed; do a fresh baseline run in the Codex environment and do not rely on historic counts.
- The project's progress docs partly predate that successful global build and still say real DB size unknown: **correct them with the verified evidence**.
- Uploaded private input reference `AAAAA.csv` previously had 9,604 records, UTF-8 BOM, 12 columns, five `NAME_ADDRESS_LINE1..5`, `Control no`, six blank headers and one nonempty extra unnamed-column value. **Never commit, copy into CI, log, or publish private addresses or control numbers.** If the sample is not mounted in Codex, use shape-equivalent synthetic fixtures; do not request it just to begin work.

## Priority 0 — Baseline and independent safety review

**Files:** `pyproject.toml`, `README.md`, `docs/PHASE1_PROGRESS.md`, `src/world_address_engine/**`, `tests/**`, `.github/workflows/**`.

- [ ] Check out the correct repository and work branch; record actual HEAD, PR, upstream worktree state and current CI; do not edit `main`.
- [ ] Read the governing spec, approved implementation plan and current source. Record exact incomplete versus existing interfaces for Tasks 1–13.
- [ ] Install with `python -m pip install -e ".[excel,test]"`; run `python -m pytest -q` and `python -m compileall -q src tools`. Record counts, Python/OS, warnings, failures and baseline commit.
- [ ] Audit security-critical flows before trusting existing prototype: unverified HKP codes, recipient name mistaken for country, geographic ambiguity, postal territories, duplicate row preservation, checkpoint tampering and CSV formula injection. Record P0/P1 findings with reproducible tests.

**Gate:** baseline reproducible, review findings logged and no known P0 bypass of the production source gate.

## Priority 1 — Secure and audit EXISTING full worldwide DB artifacts FIRST

**Files:** `tools/download_geonames.py`, `tools/build_reference_pack.py`, `src/world_address_engine/data/geonames_builder.py`, `src/world_address_engine/data/pack_registry.py`, `docs/GEONAMES_DB_BUILD.md`, `docs/data-sources.md`, new `tests/integration/test_real_geonames_packs.py`.

- [ ] Download artifact **12447987288** and report artifact **12447817791** from run **39827512415** **before expiry**. Confirm that the archive contains both nested `.sqlite.zip` packages and not a single accidentally truncated DB. If expired/unavailable, repeat pinned-source download/build; never substitute synthetic data.
- [ ] Compare uncompressed SQLite SHA256 against the two DB fingerprints above and compare JSON report counts and source archive checksums. Run `PRAGMA integrity_check`, check table/index schemas, actual counts by feature class, exact Chinese/English/Latin alias counts, and sample country/admin/place retrieval. Verify SQLite query plan uses an index.
- [ ] Fix mismatch between **published builder output** (`compact_global.sqlite` / `extended_global.sqlite` and report) and **installer expectations** (`pack.db` plus manifest fields required by `pack_registry.verify_pack`). Add deterministic per-pack manifests (`pack_id`, `profile`, `pack_version`, `schema_version`, checksums, source archive hashes, licensing, attribution and place/alias totals); add a safe install/activation test. Do not modify the existing published wheel/tag in place.
- [ ] Save checked, versioned pack artifacts in a **durable location**: prefer a separate versioned GitHub data-pack release if account limits/license constraints allow, or a user-approved object-store bucket. Do not commit ~1.1GB binary SQLite to Git history. Report the exact access URL and retention policy, not just the Actions run link.
- [ ] Re-run actual Compact/Extended size/latency/RAM benchmarks; compare alias filtering vs an unfiltered baseline only if the baseline was actually built. Do not claim a reduction percentage absent a measured baseline.

**Gate:** both real pack DBs can be independently downloaded, SHA-verified, integrity-checked and installed offline; manifests and measured MB/MiB sizes are recorded.

## Priority 2 — Make real-data classification geographically sound

**Files:** `src/world_address_engine/matching/{normalize,retrieve,classify}.py`, `src/world_address_engine/data/geonames_builder.py`, `tests/unit/test_retrieve.py`, `tests/unit/test_classify.py`, new `tests/integration/test_real_geonames_classification.py`.

- [ ] Document country/admin1/admin2/GeoNames ID relations and implement hierarchical candidate evidence (do not count identical or coincidental text matches as independent signals). Current `retrieve_candidates` aggregates simple place-name matches; a city in a street/company name MUST NOT be sufficient evidence of destination.
- [ ] Use indexed retrieval and bound query cost on the actual 1GB pack. Add geographic disambiguation rules with explicit country terms, postal code/administrative combinations, place types, aliases, territory mappings and deterministic tie handling. Never force assignment from one unqualified city/street token.
- [ ] Trilingual test suite EN/zh-Hant/zh-Hans, common romanizations and mixed scripts. Distinguish Unicode normalization from trustworthy place identity. Unsupported-script input returns explicit review status/reason.
- [ ] Regression cases: `London Road, Mumbai, India -> India`; `Springfield` alone -> review; Hong Kong/Macau/Taiwan/Puerto Rico/Guam postal destinations separately reviewed; `Timor-Leste` HKP `TP` vs ISO `TL`; EC-Ship `FRA` vs bulk `FR`. No "China" substrings in company names as destination proof.
- [ ] Evaluate a labeled synthetic/public-safe golden set by language and geography. Report confusion matrix, precision, coverage, review rate, unknown rate and representative false positives (do not assert arbitrary accuracy success from a tiny fixture).

**Gate:** actual GeoNames packs work with the runner, no unknown/ambiguous/conflicting case is silently assigned a destination; all golden-set mistakes are analyzed and addressed or explicitly gated for review.

## Priority 3 — Complete official HK Post 2-letter postal catalogue

**Files:** `src/world_address_engine/hkp/catalogue.py`, `docs/data-sources.md`, `tests/unit/test_hkp_catalogue.py`, plus a separately versioned, auditable **data-source manifest**.

- [ ] Retrieve current Hongkong Post official bulk mail code sources, record documentation version, URL, hash, appendix and service applicability. Review any conflicting historical destination charts. **Never invent country codes or derive them unconditionally from ISO**.
- [ ] Build a complete service-qualified `HKP_DESTINATION_2` master; verify **every APPROVED row against official source evidence** (independent human sign-off if code/source differences matter). Service eligibility and zoning are distinct from country classification.
- [ ] Audit territorial handling; absence of mapping produces `REVIEW_CODE_MAPPING`, not fallback. Check `TP` vs `TL`, `FR` vs `FRA`, Macau, Guam, Taiwan and Puerto Rico.
- [ ] Ensure production flag cannot be asserted by a user-provided arbitrary CSV/SQLite field alone. Require signed or release-controlled verified manifest and explicit review record. Until that is established, keep `--test-only` and fail closed in ordinary mode.

**Gate:** independently verified complete master, explicit provenance and audit report; zero unauthorized production-classification path.

## Priority 4 — Production-sized file jobs, checkpoint privacy and exact totals

**Files:** `src/world_address_engine/io/{delimited,xlsx,reports}.py`, `src/world_address_engine/jobs/{runner,checkpoint}.py`, `src/world_address_engine/cli.py`; test files under `tests/integration/`.

- [ ] Preserve all input columns (including unnamed fields), `Control no` leading zeros, original ordering and duplicates; every valid logical row yields exactly one output, even if UNKNOWN or INPUT_ERROR. Malformed unrecoverable framing must fail the job without a COMPLETE manifest.
- [ ] Optimize resume so 1M–5M input rows are not repeatedly rescanned unnecessarily. Verify resume source and pack hashes, shard contents and row boundaries, and prevent race conditions/source modification during classification.
- [ ] Handle offline PII safely: encrypted-at-rest support or restrictive file permissions plus configured retention, safe cleanup, no address logging, no accidental CI artifact upload. Treat local JSONL `.job-state` shards as sensitive.
- [ ] Ensure source/candidate/review/manifests reconcile exactly: total rows = all statuses; MATCHED = summed per-HKP destination totals; output original values preserved in raw safe export; Excel-view outputs neutralize CSV formula injection.
- [ ] Benchmark genuine reference packs with **100k, 1M and 5M** synthetic rows, bounded memory and realistic disk; report wall-clock throughput, peak RSS, compressed checkpoint sizes, failure recovery timings, SQLite latency and accuracy/coverage. Do not invent numerical performance commitments.

**Gate:** reproducible exact reconciliation, resumable interruption/restart, explicit privacy controls and real benchmark measurements.

## Priority 5 — Windows GUI, manual QC and distribution

**Files:** `src/world_address_engine/gui/{app,review_store}.py`, Windows-oriented packaging scripts/workflows, tests `tests/integration/test_gui_workflow.py` and offline packaging tests.

- [ ] Create PySide6 GUI: file selection, encoding/worksheet/column mapping, install/select Compact vs Extended, progress, cancellation/resume, matched counts and review cases. Keep main thread responsive.
- [ ] Operator review: one record at a time, approved destination choices only; log operator, timestamp, original/current result, reason, pack/catalogue versions. Recompute reports after QC without shifting or duplicating unrelated rows.
- [ ] Package Windows .exe with intended data-pack approach (avoid bundling unreviewed multi-GB databases blindly); test on a clean offline Windows machine, including fresh install, 9,604-row shape-compatible fixture, and recovery.
- [ ] Complete independent spec/security review and CI. Tag a **new** semver pre-release (for example `v0.1.0-alpha.1`, after verification); never overwrite `v0.1.0-alpha.0` assets/tags.
- [ ] Publish a production-ready release ONLY after HKP master approval, QC precision results, privacy controls and packaged Windows offline acceptance. Otherwise explicitly label developer preview.

**Gate:** a tested, operator-usable offline GUI with traceable QC and documented Windows release evidence; no silent promotion to production.

## Reporting contract to user (Cantonese summary)

After each independent stage, return: changed files/commits, RED→GREEN test commands and actual counts, Code Review findings, verified DB sizes (bytes + MiB), exact artifact/release URLs, uncovered accuracy/privacy risks, blockers, and next task. Keep all private recipient content out of reports. Do not claim a stage completed because CI config exists; verify the actual job/asset.

## Codex execution prompt (copy into Codex)

> Continue `andy846/world-Address-sorting-engine` on `feat/hkp-trilingual-phase1` following `docs/CODEX_HANDOFF_2026-10-23.md`, the existing approved spec and 13-task implementation plan. First secure existing successful REAL GeoNames build artifacts from GitHub Actions run `39827512415` before they expire, verify both SQLite hashes/integrity/aliases, and resolve pack-builder/install-format incompatibility. Then work through geographic matching audit, official HKP two-letter master, large-batch privacy/reliability, PySide6 Windows UI and release gates. Use test-first commits and independent per-task reviews if subagents are available. Preserve the existing Draft PR and do not merge to main, overwrite the alpha tag, publish sensitive records, or claim production readiness without the evidence gates. Report actual metrics and status at each milestone. 
