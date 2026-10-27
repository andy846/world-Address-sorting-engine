# v0.3 workflow, quick lookup and zone mapping

Approved by user: implement the proposed plan, with defaults selected in the
planning questions. Work branch feat/v0.3-workflow-zones, candidate 0.3.0rc1.
Preserve v0.2.0 tag/Latest, canonical D:\WASE\WorldAddressEngine.exe and its
CURRENT_RELEASE.json; no main merge or formal promotion before new manual acceptance.

## Required behavior

1. Auto-discover installed global Extended (Compact fallback) and HK packs,
   default HK enabled, explicit manual override/off allowed. Prefer saved manual
   paths and executable-adjacent packs; source project/CWD fallback. Verify off
   UI thread, display version/partial coverage and missing/bad pack status.
   No network download. Independent readonly classifier/SQLite connections per
   worker; do not weaken registry content-hash/receipt/integrity guards.
2. GUI fresh batches create sibling <stem>_output_YYYYMMDD_HHMMSS, atomic mkdir
   plus _01 suffix on collision. Optional output setting is a parent directory.
   Actual last run path is separate; repeat/input changes never reuse occupied
   output. Resume retains original folder/pins; CLI explicit --output remains
   an exact directory. Preserve all prior outputs and original inputs.
3. Native top-level Batch analysis / Single address lookup pages, batch default.
   Multi-line input, button/Ctrl+Enter query, Enter newline, clear/copy code,
   country/name/status/Zone/NOVSN display. Independent persistent worker allows
   querying during batch; reuse verified model, no per-query full DB reload.
   Editing invalidates stale result/copy; request generations drop late results.
   No address history/files/logging. Closing/cancelling safe for both workers.
   Keep System/Light/Dark, keyboard focus and large-font layout accessible.
4. Literal mapping from original pinned CountryList_20250708.pdf. Source has
   236 rows including excluded CNS; active mapping exactly same 235 business
   Country Codes. CN -> CN - Airmail/F; HK -> LOCAL/A;
   MO -> Macau - Surface/M; TW -> Taiwan/F. No delivery-method inference or
   new air/surface setting. Preserve string values, do not truncate centered
   PDF columns or assume numerical Zone. Map final country code (TP/XO/XK
   namespace), never raw GeoNames ISO. Existing country catalogue/matcher unchanged.

## Integration contracts (locked before delegation)

- Data module world_address_engine.data.zone_mappings exports frozen ZoneEntry
  (country_code,zone_code,novsn_zone_code), ZoneCatalogue (entries,version,
  source_sha256,fingerprint), load_zone_mappings(path=None),
  zone_values(code,catalogue=None)->(str,str). None/empty code -> ('','');
  unknown nonempty code -> ValueError. Default resource country_zone_mappings.json.
  Metadata: {'version':zones.version,'source_sha256':zones.source_sha256,
             'sha256':zones.fingerprint}. PDF parsing is build-time only.
- New detail output schema 2: original columns + Country_Code,Zone_Code,
  NOVSN_Zone_Code (exact generated tail). Summary: Country_Code,Country_Name_TC,
  Country_Name_EN,Zone_Code,NOVSN_Zone_Code,Count,Percentage. Diagnostics unchanged.
  Manifest top-level report_schema_version=2 and generated_columns=list above;
  run_metadata.zone_mapping holds exact mapping metadata. Unknown leaves all 3
  generated cells blank; known missing mapping errors, not guessed.
- Checkpoint STATE_VERSION='2026-10-26.country-state.3' pins zone metadata. Old
  state.2 requires v0.2.0; do not relabel or mutate old checkpoints.
- Case rows add zone_code,novsn_zone_code, legacy schema1 report fields blank.
  Case CSV export becomes Source_Record_No,Address,Status,Country_Code,Zone_Code,
  NOVSN_Zone_Code,Reason,Candidates. New/legacy readers use explicit manifest
  schema and generated positions, not last-cell guesses; original duplicate
  headers/fields/order remain preserved. Legacy completed reports read-only.
- Single lookup uses same CountryClassifier and zone_values, not a batch job.
  Existing CountryInference/CountryCatalogue and country rules7 stay unchanged.

## Ownership / ordered milestones

- [x] A: independent data worker owns zone_mappings.py, resource JSON,
  tools/import_country_zones.py and new tests/unit/test_zone_mappings.py only.
- [x] B: main implementer owns country_reports.py, country_analysis.py,
  country_cases.py and corresponding non-GUI report/job/cases tests.
- [x] C: GUI worker owns country_app.py, country_layout.py,country_results.py,
  new GUI helper modules, GUI integration tests; default/missing pack, automatic
  sibling output and concurrent single lookup. No edits to data/jobs/io/tools.
- [x] D: benchmark worker owns benchmark_country_repeat.py,
  country_benchmark_verify.py and their two unit-test modules only; authenticate
  schema2/zone metadata/new fields, preserve legacy verification where explicit.
- [x] Main integrates candidate version/CI/packaging assertions, per-task reviews,
  full local/remote regression, actual candidate EXE and offline smoke.
- [x] Real private 9,604-row replay: identical original cells/country/status/reason;
  42 unresolved retained; correct zones. Frozen 336 public cases stay passing.
- [x] Fresh million workload + cancel500k/fresh-process resume; exhaustive source,
  code/zone/diagnostic/count and CSV/manifest equivalence. No runtime edits/commits
  or other heavy work during measurements. Only 9,606 distinct keys, report honestly.
- [x] Warm quick lookup >=48 distinct public addresses, idle and batch concurrent,
  P95 <=1s target; initial validation separately timed/progress visible.
- [x] Candidate GitHub Draft PR and local out/v0.3.0rc1 artifact for manual test;
  do not overwrite current formal executable or published artifacts.

## Evidence / ledger

TDD failing tests before code, focused verification and frequent coherent commits.
Independent per-task and final reviews. Record actual outputs, reviews, timings,
DB/artifact sizes and remaining blockers here. Private inputs/replays/oracles
remain only in ignored exports/.tmp; public-only source and aggregate receipts
may enter Git. Existing v0.2.0 snapshot is the legacy compatibility baseline.

Task A completed: 67 zone tests / 130 combined zone-country tests passed.
Independent reviewer re-extracted all 236 audit rows and 235 active mappings
from the pinned PDF, confirmed byte-identical re-import, immutable entries,
fresh-byte fingerprints and rejection of all 472 coordinated value mutations.
No important data-task findings. Existing country catalogue/resource unchanged.

Core progress: seven report/case tests and three checkpoint tests failed first;
new output schema/pins/state3/legacy readers implemented. Initial integrated
group: 69 passed plus six old column assertions awaiting new contract. After
updating those assertions with explicit IN/JP/blank zone values, 75 passed in
18.05s. Independent core review is in progress.

Execution resumed after an automatic-approval service usage-limit interruption;
the final test-assertion patch had not executed, was verified absent and then
applied normally after service recovery. No alternative approval bypass used.

Task B reviewed: independent reviewer ran 132 targeted tests and all-235-code
probes; no important findings. Verified schema/downgrade rejection, mapping
changes before export/finalization, report read races, unchanged diagnostics,
legacy blank zones and state2 rejection without mutation. Main rerun including
candidate metadata: 55 passed in 16.13s (overlapping focused group).

Review round 2: Task D independent synthetic review found no important issues
(126 passed, two live-revision runner checks pending freeze; 48 rehashed zone
corruptions rejected). GUI review reproduced an allocation-boundary reference
replacement and retained quick-query cache keys; a smaller preflight-schema
gap was also identified. Packaging review reproduced a ready/settled race in
the smoke producer. First full suite was stopped at 54% without failures to
apply these corrections; that interrupted run is not a completed acceptance.
New backend identity regression: five RED failures, then 42 focused passed.

Review corrections completed: backend 4fae30e (51 main focused tests; separate
43-test independent recheck). GUI preflight pins consumed Geo/HK/manifest and
quarantine bytes through job creation, validates schema/profile before output,
and clears query cache even on exceptions: 14 RED, then 29 focused GREEN;
main caller/GUI recheck 139 passed in 35.69s. Independent final 29-test rerun
used the project Python3.13 interpreter unclamped; the earlier reviewer CSV
overflow was specific to an unsupported Python3.11 interpreter.
Packaging ready/settled race: three deterministic RED tests, then 197 passed,
one optional actual-build skip; independent three-test race rerun passed.
Actual 0.3.0rc1 EXE build and frozen offline workflow self-test passed:
48,801,605 bytes, all prior and new strict gates true, no DB bundled.
Fresh private schema2 replay preserved all 9,604 originals/codes/diagnostics
and verified every zone pair; public 336/336 smoke bank passed unchanged.

Final acceptance receipts (candidate, not formal promotion): full local 1,984
passed / 1 skipped / 2 existing xfails; actual local EXE and fresh installed
wheel passed. GitHub validation 40336180259 passed Linux (1,698/122/2) and
Windows (1,668/319), including explicit real EXE smoke. Windows regression
40336180004 passed 1,669/318 including real packaging. Optional-Qt test-only
guard 43e09bb fixed the initial Linux collection failure; runtime unchanged.
Independent final cross-contract review was clear.

Measured frozen clean commit 43e09bb: repeated million 235.411s, 79,233,024-byte
peak RSS; cancel at 500k 98.462s, fresh-process resume 238.661s. Both outputs
exhaustively verified and all three CSVs plus manifests identical. Checkpoints
removed on completion. Workload has only 9,606 distinct keys. Real GUI idle
48-query P95 25.36ms, different 48 queries concurrent with 96k public batch
P95 122.14ms; initial model/reference preparation 46.401s separately.
DB sizes unchanged: Compact142,577,664 / Extended1,087,344,640 /
HK747,376,640 bytes. Full receipts/artifact hashes/review corrections and
remaining acceptance scopes are in docs/releases/v0.3.0rc1.md and its JSON.
Draft PR #4 is attached. v0.2.0 Latest/root EXE preserved; next step is manual
candidate acceptance. No global accuracy, million-distinct or production claim.

Final receipt completed on 28 October: CI attestation explicitly names 43e09bb;
remaining commit is documentation only. Aggregate/privacy review found no data
leak. Existing EXE self-test, runtime fingerprint and formal EXE hash rechecked;
light/dark and batch captures readable after loading Windows fonts in the
offscreen harness. Application source and validated behavior remain unchanged.
