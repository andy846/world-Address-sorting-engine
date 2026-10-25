# Country GUI Feedback Milestone - 2026-10-24

## Delivered

- `ee76ce1`: count-only structured runner stages, alongside compatible integer
  committed-count callbacks. Small jobs report activity before batch commit.
- `3e60b90`: original globe/routing SVG and seven-frame ICO (16 to 256 pixels),
  wheel resources, Windows executable icon, window/application/taskbar branding.
- `d6eec9f`: streaming, authenticated case pages and exclusive CSV export.
- `6784e26`: live stage/elapsed/count/throughput display and completion overview.
  Settings collapse after completion to leave space for results, and pending
  cases open automatically when present. Settings can be expanded again.

The completion overview distinguishes determined, inferred and pending records.
Pending means UNRESOLVED, including input reader errors. Inferred estimates have
their own filter and are not labelled failures. Cases show logical source record
number, full address, reason/explanation and candidate codes. This is not a
physical worksheet-row number: blank XLSX rows can be skipped.

Processing shows input validation, source/database fingerprint checks, catalogue
loading, checkpoint verification, classification, output verification/export and
finalization. A timer stays active through blocking I/O. Percentages are only for
known stage totals and never reach whole-job 100% before completion. No ETA or
classification-accuracy claim is fabricated.

## Privacy, integrity and volume

Case pages retain at most 100 rows. Both paired report streams are authenticated
against their manifest SHA-256 using the exact bytes parsed before any page is
displayed or export published. Each page therefore scans both reports completely
on a worker; very large reports may take noticeable time, with cancellable UI.
Export streams the entire selected filter, not just the visible page. UTF-8 BOM
and spreadsheet formula protection are retained. Publication refuses an existing
destination, including a creation race; cancellation/failure cleans staging.
New case files must be outside the immutable completed report directory.

No original input, completed report, manifest, published release or main branch
is modified. Classification rules remain `2026-10-24.country.3`. No customer input,
checkpoint or row-level output was uploaded or used in the new synthetic tests.

## Independent review

Two independent reviewers checked disjoint changes and integration. Three issues
were confirmed, reproduced RED and fixed: protected-header collisions, ignored
report hashes, and legitimate long TXT report fields exceeding CSV's default
field limit. The fixes were independently rechecked, including mutation during
reading; no actionable findings remain. A standalone panel country-table concern
was withdrawn: the window intentionally supplies bilingual country rows before
the panel renders metrics, covered by the real-runner GUI test.

Qt shutdown was also tested explicitly: a signal lambda retaining the panel was
replaced with a bound slot; closed panels and windows do not retain Python cycles.

## Measurements

Local synthetic real-Extended-pack GUI run, 10,000 records:

- 7,500 explicit-country rows and 2,500 deliberately empty rows; repetitive
  fixtures exercise caching and UI/job plumbing, not real-world accuracy.
- Full analysis, manifest/summary load and first pending page: **7.666 seconds**,
  **1,304.51 records/second** end to end.
- Export all 2,500 pending cases: **0.120 seconds**; visible page capped at 100.
- Peak process working set: **81,158,144 bytes** (not a machine-wide measurement).
- Destination counts reconcile: CN/HK/JP each 2,500; unresolved 2,500, all expected
  empty rows. Next-page source record cursor checked (4 then 404).

Installed k2 SQLite sizes are unchanged: Compact **142,577,664 bytes**; Extended
**1,087,344,640 bytes**. No new databases were built or embedded in the EXE.

## Verification and remaining gates

Focused final review regressions passed with warnings treated as errors (58
cases covering case reader, panel and GUI). Runner/preflight/progress: 90 passed.
Packaging contracts include frozen icon loading, stage evidence, completion
metrics and the first unresolved record; legacy approval refusal remains required.

Final full regression with the real installed k2 packs and `WASE_SLOW_CHECKS=1`:
**1,039 passed, 1 skipped, 2 known strict-retrieval xfailed in 280.60 seconds**.
No test failures. The two expected failures are pre-existing strict-retrieval
limitations, not hidden country-GUI failures. Source compilation and diff checks
also passed. Full validation ran concurrently with the final packaging build;
the standalone synthetic throughput measurement above did not.

Frozen Windows build/self-test passed: icon loaded, all required stage events
observed, total 4/pending 1, first pending logical record 4. EXE size is
**48,708,294 bytes**, SHA-256
`d03415435ac511c901d2f23fa2b2d90d324d33026760e9c5fb0453d282e8c851`.
The separately named local artifact is
`D:\WASE\out\WorldAddressEngine-gui-feedback-20261024.exe`.

Synthetic screenshots were inspected for layout and icon legibility. Manual
Windows operator acceptance remains required; labelled
classification accuracy, million-scale acceptance and production-readiness gates
are not claimed by this UI milestone. No release overwrite or main merge.
