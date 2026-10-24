# ALS Hong Kong regional pack implementation ledger

Spec: docs/superpowers/specs/2026-10-24-hk-bilingual-regional-design.md.
User explicitly approved implementation, including independent pack and
unresolved-only scope. Base v0.1.0 / 13ed06a. Work branch
codex/hk-bilingual-regional, existing local checkout reused so private data and
verified packs remain in place; no mutation of the release branch/tag.

- [x] Audit official ZIP/schema/terms and establish real counts (source gate failed; see below).
- [ ] TDD registry/normalization and streaming audited pack builder; build real DB.
- [ ] TDD bounded read-only matcher and country fallback; independent reviews.
- [ ] Integrate CLI/jobs/checkpoints/GUI; pin optional pack hashes and versions.
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
