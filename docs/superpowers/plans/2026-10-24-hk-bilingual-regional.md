# ALS Hong Kong regional pack implementation ledger

Spec: docs/superpowers/specs/2026-10-24-hk-bilingual-regional-design.md.
User explicitly approved implementation, including independent pack and
unresolved-only scope. Base v0.1.0 / 13ed06a. Work branch
codex/hk-bilingual-regional, existing local checkout reused so private data and
verified packs remain in place; no mutation of the release branch/tag.

- [x] Audit official ZIP/schema/terms and establish real counts (source gate failed; see below).
- [ ] TDD registry/normalization and streaming audited pack builder; build real DB.
- [x] TDD bounded read-only matcher and country fallback; independent reviews.
- [x] Integrate CLI/jobs/checkpoints/GUI; pin optional pack hashes and versions.
- [ ] Four-language/foreign negative tests, full regression and private replay.
- [ ] Enabled/disabled million-row and recovery validation, candidate Windows EXE.
- [ ] Publish independent attributed data pack/candidate PR; retain v0.1.0 Latest.

Sources downloaded successfully: ALS ZIP 20,777,483 bytes, SHA256
4549e4f774224abdef062cb6ffaa7e75f0d8dc02187a64bc6c05434472b6f577;
schema SHA256 67deb2349be44ad8cce20650065833e12e6895d394998da8b44377135fe634f6.
Archive has 18 district GeoJSON members and one public-housing 3D member.
Runtime pack indexes projected 2D fields; floor/unit arrays are audited, not
expanded into per-household matching records. Snapshot remains ignored locally.

2026-10-24 implementation evidence:

- Registry/installer review fixes: required query columns/primary keys/values,
  explicit orphan checks, complete indexes, original snapshot identity during
  copy, standalone SQLite without WAL/journal dependencies. Five review
  reproductions failed before the fixes and passed after them; extended
  registry/builder/matcher/job/install set: 133 passed in 21.25s.
- CLI/jobs pin optional regional DB and manifest hashes and reject a regional
  database disguised by a global manifest. Latest focused registry/job/CLI/
  installer/existing country job regression: 61 passed in 19.34s with warnings
  treated as errors. Original private 9,604-row replay with the regional option
  disabled: 7,143 determined, 2,419 inferred, 42 unresolved. All three CSV report
  hashes exactly match the reviewed rules4 baseline.
- Benchmark tooling regional selection pinning: RED then GREEN; combined
  benchmark/install/version checks: 21 passed in 21.10s.
- Independent matcher review found five negative cases (foreign city/admin
  conflicts, supplied number forms, recipient/company lines, translated shared
  roles, unit/floor numbers). Fixes remain in progress.
- Full strict official audit: 183,964 features, 174,456 schema-valid,
  9,508 invalid, 1,241 projected duplicates among valid features, all 19 members
  CRC checked. Detailed audit took 566.672s. No final DB was published.
  Most failures are required subfields missing inside block/street/village/floor
  objects. Two records lack all coordinates and have no complete matching
  official projection elsewhere in the source. No inferred repairs were made.
- Required user decision pending: retain strict all-record gate, or explicitly
  permit a partial-coverage test pack that quarantines every invalid feature.
  Do not silently relax the official schema or claim full source coverage.
- Candidate code version is 0.2.0rc1. v0.1.0 and its Latest assets are untouched.

Final code milestones (local, before performance receipt):

| Commit | Scope | Verification/review |
|---|---|---|
| a816173 | Verified immutable registry and offline installer | Registry/job review defects reproduced and fixed |
| ff79a0d | Unresolved-only bounded paired-address matcher | 23 new RED cases; 281 matcher/country tests GREEN |
| 5fc0193 | CLI, pinned recovery, benchmark selection | 59 scoped tests passed in 42.91s |
| 22fc8f8 | Optional GUI controls, real partial metadata, frozen self-test | 107 passed, 1 skipped; actual Windows EXE passed |
| eb3c621 | Strict streaming ALS audit/build and atomic directory publication | Seven review findings fixed; 66 focused tests passed |
| cfd8779 | Verify every benchmark run/comparison uses the pinned regional selection | New RED reproduction then 84 tool/verifier tests passed |

Final integrated local regression: **1,487 passed, 1 skipped, 2 pre-existing
xfails in 224.25s**, both real k2 packs and slow checks enabled. Separate actual
Windows frozen self-test passed (the ordinary optional build test is the skip).
The earlier integrated failure came from the old simplified self-test global
fixture; it was corrected to the supported schema without weakening checks.

Candidate EXE 48,760,746 bytes, SHA256
b09d0e6c28fa0b25ef4b483112d68282f8149b97dcc811b4e3dd5e5adce27c18.
Wheel 194,789 bytes, SHA256
c8c229cb7719653245a8bbcd1179e98b7cd4b18dbd3142ebddcd09a8bf49b24e;
installed-wheel version, module path, country catalogue, Chinese conversion
and regional CLI/module smoke passed. Candidate remains local, unpublished.

Fresh independent integration review found one additional benchmark metadata
verification defect; fixed in cfd8779 with RED/GREEN coverage. No outstanding
reported code findings remain. Source-policy and real-pack acceptance gates
remain outstanding, not waived by code tests.

Repeated-million disabled-pack receipt:

- Runtime commit cfd8779, source fingerprint
  11afe323373d54c214976b81658e6412a26d4bc2885b1732fbc5b4867146daee.
- Complete 1,000,000 rows in 158.456s (6,310.89 rows/s), peak RSS 74,280,960
  bytes, checkpoint peak 857,393,236 bytes, completed reports 173,100,270 bytes.
- Cancelled at exactly 500,000 committed rows in 48.911s; separate process
  resumed to completion in 159.043s, peak RSS 74,444,800 bytes.
- Exhaustive per-row verification passed on both runs; all 39,600 public
  controls match labels. Three CSVs and manifests are byte-identical across
  full/recovery; the three CSVs also match the stable v0.1.0 benchmark exactly.
  Both completed plaintext checkpoints were removed. The 4,200 unresolved
  rows are the original 42 repeated 100 times, not new failures.
- This is the regional-disabled repeated workload (9,606 distinct keys), not
  a real HK-pack enabled or million-distinct validation. The latter gates
  remain blocked by the explicit source-policy decision.
- Detailed sizes, review evidence and limits:
  docs/HK_REGIONAL_VALIDATION_2026-10-24.md.
