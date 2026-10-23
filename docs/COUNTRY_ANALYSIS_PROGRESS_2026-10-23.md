# Country Code analysis progress

Plan: docs/superpowers/plans/2026-10-23-country-code-analysis.md

## Milestone 1: catalogue and estimator

Commit: 873ae31.

- Source catalogue: 236 auditable rows, 235 geographic entries; CN canonical,
  CNS excluded, Kosovo geographic XK -> source XO, source XK remains Caroline
  Islands. USER_PROVIDED, not an officially approved HKP master.
- Source importer/catalogue tests: 63 passed, including observed RED-to-GREEN.
- Estimation separates recipient/company text, streets, territory/parent names,
  localities, administrative regions and substantially leading cities.
- Independent review found concrete recipient, street, territory and spacing
  defects. Regression tests now cover these cases; no forced rival-country tie.

## Milestone 2: streaming outputs and recovery

Commit: bc688c0.

- Streaming CSV/TXT/XLSX; original fields, IDs, row order and duplicates retained.
  Summary and diagnostics reconcile to every input row; manifest published last.
- Source, database, catalogue, rules, options and checkpoint data are verified.
  Default completed jobs remove plaintext shards. Restricted metadata-only
  finalization recovery survives failed manifest publication.
- Independent review identified a non-resumable finalization gap. Eight failing
  recovery regressions were added before the fix; runner/report/CLI target:
  46 passed. Further full-suite regression fixed the single-line input filter.

## Milestone 3: default GUI and packaged application

Commit: 1f93bce.

- Default GUI is Country Code analysis, with offline pack selection, preview,
  encoding/worksheet/column mapping, background work, cancel/resume and counts.
  Strict postal GUI/classifier remain separately available.
- Independent review found missing dynamic resource collection in the EXE:
  a real frozen self-test reproduced the failure; explicit resource collection
  fixed it. OpenCC 0.1.7 dictionaries/configs are bundled and checked.
- Preview cancellation was reproduced with a slow synthetic iterator before
  adding cooperative checks and reader closure. Regression passed in 0.58s.
- Final full local suite with real k2 packs and slow checks: 870 passed,
  1 skipped, 2 known strict-retrieval xfails, 152.24s. Syntax and diff checks
  passed. Isolated installed wheel loads 235 entries and both OpenCC converters.
- Onefile EXE: 48,557,449 bytes. Actual frozen self-test passed with the new
  country GUI, four synthetic rows, expected CN/HK/JP counts, one unresolved,
  all 235 mapping entries and loaded normalization. Native Windows font/render
  inspection passed; the offscreen backend alone has no installed fonts.

## Measured real-data aggregate validation

No customer addresses, input files, row-level outputs or checkpoints are in
Git, CI or release assets. Only aggregate measurements are recorded here.

- Input: 9,604 rows, no empty address or decoding errors.
- Old-engine diagnostic: 3,795 UNKNOWN/Review (39.52%), 63.28s; uses Extended k2
  and a 36-code test postal master, not the unavailable original configuration.
- New: 7,120 DETERMINED + 2,322 INFERRED + 162 UNRESOLVED = 9,604.
  Code coverage 98.31%, unresolved 1.69%, meeting the <=192-row target.
- Inference: 17.489s, peak RSS 51,146,752 bytes.
- Complete run/export/revalidation/cleanup: 40.811s, peak RSS 55,025,664 bytes;
  four output files total 1,578,314 bytes. Checkpoint/recovery folders removed.
- Every original field and leading-zero ID was checked against the output.
  Duplicated address groups with inconsistent codes: zero. Summary reconciles.
- SQLite sizes remain Compact 142,577,664 bytes; Extended 1,087,344,640 bytes.
  Both preserved k2 pack hashes and SQLite integrity are covered by regression.

## Rulings, remaining gates and next steps

- Country list statistics do not require postal-service choice or an approved
  postal master. Existing strict postal approval is not weakened.
- Coverage is not accuracy: no complete human-labelled ground truth exists.
  Clear-leading evidence may be inferred; genuine conflicts stay unresolved.
- Reviewer defects above received regression fixes; no reported important
  GUI/packaging finding remains unaddressed. Earlier strict-pack alias xfails
  remain documented, separate from the new country alias rules.
- 1M/5M throughput and clean disconnected Windows operator acceptance remain
  outstanding; no postal production readiness claim is made.
- Next: GitHub Linux real-pack and Windows build validation, draft PR and a new
  alpha.2 developer prerelease. Preserve alpha.0/alpha.1 and do not merge main.
