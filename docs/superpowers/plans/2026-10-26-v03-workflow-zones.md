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

- [ ] A: independent data worker owns zone_mappings.py, resource JSON,
  tools/import_country_zones.py and new tests/unit/test_zone_mappings.py only.
- [ ] B: main implementer owns country_reports.py, country_analysis.py,
  country_cases.py and corresponding non-GUI report/job/cases tests.
- [ ] C: GUI worker owns country_app.py, country_layout.py,country_results.py,
  new GUI helper modules, GUI integration tests; default/missing pack, automatic
  sibling output and concurrent single lookup. No edits to data/jobs/io/tools.
- [ ] D: benchmark worker owns benchmark_country_repeat.py,
  country_benchmark_verify.py and their two unit-test modules only; authenticate
  schema2/zone metadata/new fields, preserve legacy verification where explicit.
- [ ] Main integrates candidate version/CI/packaging assertions, per-task reviews,
  full local/remote regression, actual candidate EXE and offline smoke.
- [ ] Real private 9,604-row replay: identical original cells/country/status/reason;
  42 unresolved retained; correct zones. Frozen 336 public cases stay passing.
- [ ] Fresh million workload + cancel500k/fresh-process resume; exhaustive source,
  code/zone/diagnostic/count and CSV/manifest equivalence. No runtime edits/commits
  or other heavy work during measurements. Only 9,606 distinct keys, report honestly.
- [ ] Warm quick lookup >=48 distinct public addresses, idle and batch concurrent,
  P95 <=1s target; initial validation separately timed/progress visible.
- [ ] Candidate GitHub Draft PR and local out/v0.3.0rc1 artifact for manual test;
  do not overwrite current formal executable or published artifacts.

## Evidence / ledger

TDD failing tests before code, focused verification and frequent coherent commits.
Independent per-task and final reviews. Record actual outputs, reviews, timings,
DB/artifact sizes and remaining blockers here. Private inputs/replays/oracles
remain only in ignored exports/.tmp; public-only source and aggregate receipts
may enter Git. Existing v0.2.0 snapshot is the legacy compatibility baseline.
