# Country recall, appearance and development stage — 2026-10-24

## Delivered behavior

Implementation commits: `1530a0d` (geographic recall) and `2d8ced1` (persistent
appearance). Both were pushed to the existing development branch/Draft PR #2.

The country estimator now distinguishes further Hong Kong locality/abbreviation
pairs and public landmark/street combinations, mainland administrative names,
compound Chinese territory expressions, New South Wales, London/postcode and
Seoul/Korea context. Street, industrial-park and building occurrences no longer
introduce spurious country conflicts. Country rules are `2026-10-24.country.4`;
earlier checkpoints retain their existing version guard and cannot mix rules.

An independent full-line foreign metropolis withdraws a contextual estimate.
Short aliases such as KL do not become independent foreign-city evidence.
Standalone countries, explicit foreign destinations, separate country conflicts
and street/building roles remain covered by regression tests. Returned-mail
markers without usable address context receive `RETURNED_MAIL_NO_ADDRESS`.

Appearance is visible in the header: System, Light and Dark. The selected mode
is saved using QSettings; explicit modes resist later system palette changes,
while System follows them. Styles stay scoped to the owned window. The header
reflows from actual label widths, including installed Segoe UI at 18 points.

## Whole-file aggregate validation

The supplied private input was replayed in full with the real Extended k2 pack.
No input, row-level results, identifiers or private screenshots are committed.
The corrected baseline and input hashes were checked unchanged.

| Measure | Previous rules3/source order fixed | Reviewed rules4 |
|---|---:|---:|
| Total | 9,604 | 9,604 |
| Determined | 7,136 | 7,143 |
| Inferred | 2,351 | 2,419 |
| Unresolved | 117 | 42 |
| Code coverage | 98.782% | 99.563% |

New assignments: 75 (57 HK, 14 CN, one each GB/KR/AU/MO). Four previously
assigned codes were corrected: two HK-to-CN mainland street-name occurrences
and two US-to-HK locality/address combinations. No previously assigned record
became unresolved in the final comparison. Every original exported field,
leading-zero identifier, row order and duplicate-code consistency was checked.
Counts reconcile exactly; completed checkpoints were removed.

Of the remaining 42, 40 source records explicitly state returned mail/unknown
address. The other two contain partial street/facility information without
sufficient country context. No country is filled from the batch majority.
Coverage is not labelled accuracy or postal deliverability.

Final whole-job wall time: **54.811 seconds**, **175.22 records/second**.
Peak process working set including the comparison validation: **63,078,400
bytes**. Four completed report files total **1,580,226 bytes**. Concurrent
regression activity means this is not a controlled speedup comparison.

Final local output is in the ignored, new folder
`exports/AAAAA-country-analysis-recall-rules4-reviewed-20261024`.
An earlier provisional replay is preserved separately; its 67 unresolved result
contained short-alias conflicts and is not the final result.

Real DB files remain unchanged: Compact **142,577,664 bytes** (135.973 MiB),
Extended **1,087,344,640 bytes** (1,036.973 MiB). Their pinned k2 fingerprints and
integrity checks remain part of the real-pack regression suite.

## Test-first changes and independent review

- Initial synthetic reproduction: 41 failures, 14 passes; subsequent refinements
  reproduced three role/marker defects, seven review findings and two KL alias
  conflicts before their fixes. Synthetic tests use public terms and invented
  records, never customer rows.
- The independent review found standalone-China suppression, incomplete building
  guards, foreign-city conflicts and large-font header truncation. Each received
  a regression fix. The whole-file comparison then found the KL alias collision;
  it was reproduced and corrected before accepting final totals.
- Both installed real databases exercise the geographic context regressions.
  Latest matching target: 221 passing tests. Appearance review: 17 passing
  tests, 25 additional layout probes and 30 GC-disabled lifetime cycles.
- Separate-process preference persistence was checked. Theme notifications were
  simulated through Qt; actual operator Windows theme changes still require
  manual acceptance.
- Independent matching and appearance rechecks reported no important residual
  findings. The added foreign-metropolis guard concerns separate whole lines;
  complex multiple-city text within one line still needs labelled evaluation.

Final full regression with real k2 packs and slow integrity checks:
**1,203 passed, 1 skipped, 2 pre-existing strict-retrieval xfailed in 189.21
seconds**, exit 0. Final focused appearance/workbench/packaging checks with
warnings as errors: **103 passed, 1 skipped**. The skipped bundle check was
exercised separately by the actual frozen Windows EXE self-test, exit 0 and
zero assertion failures. Source compilation and whitespace checks passed.

The new local executable is **48,733,911 bytes**, built separately from all
published release assets. Its frozen workbench gate includes the visible
System/Light/Dark selector, address source order, icon, progress, summary and
bounded pending cases. Offline normalization and strict approval refusal still
pass. Package metadata stays `0.1.0a2`; this is an unreleased development build.
Local operator file: `out/WorldAddressEngine-recall-themes-20261024.exe`.
SHA-256: `528111069cc4a284bcfc2e7a4c801fe9072a9f28581efa45033f58873557ee9b`.

## Current development stage

This is an implemented and testable **developer preview** of the user's
country-code list-analysis workflow. Offline reference packs, country catalogue,
CSV/TXT/XLSX input, streaming/resume, reports, progress, bounded read-only case
inspection, appearance preferences and a Windows executable are implemented.

Remaining country-analysis acceptance gates are a labelled accuracy benchmark,
1M/5M throughput/recovery measurements, clean disconnected Windows installation
and operator acceptance. The case interface currently inspects/exports records;
country-estimate correction writeback is not an implemented acceptance claim.
The separate strict postal workflow retains its own official-catalogue approval
gate and does not change the country-statistics purpose.

This work does not merge main, alter published alpha assets, or establish
production readiness. Existing draft PR #2 continues to carry development.
