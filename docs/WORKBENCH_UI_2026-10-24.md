# Native Country Workbench Milestone - 2026-10-24

## Approved scope and implementation

The operator selected the side-by-side workbench rather than a wizard. The
existing offline Qt application remains the same application and engine.

- `29ab48c`: responsive semantic metric cards, readable numeric values and
  accessibility names, compact country/case tabs, full-address details splitter.
- `70d88c4`: scoped light/dark presentation tokens, native-font propagation,
  scrollable input settings and flexible results workbench, compact progress,
  output footer and collapsible diagnostics. Strengthened frozen self-test.
- `26e6415`: wrapped-text pane-height protection at 18-point text and live
  system-palette refresh, with retained window-collection guarantees.

Settings are a resizable sidebar, initially around 320 logical pixels wide.
The output folder and open action remain visible at the bottom. Diagnostics are
collapsed until requested or a failure occurs. A failed initial case view is
shown as partial success with an explicit warning, not hidden behind "Complete".

Existing globe/routing identity is retained. Teal actions, neutral layered
surfaces and semantic success/inferred/pending cards work in platform light or
dark mode. No remote fonts, web framework, network assets or animations were
introduced. The UI UX Pro Max data-dense-dashboard guidance was adapted to Qt;
its marketing landing template and unrelated web-stack guidance were rejected.

## Data safety

Classification modules, runners, readers, report writers, rules, country master
and real reference databases are unchanged. Address selection is still read in
source/display order, regardless of the click order. CSV and XLSX integration
tests compare all three report CSVs to the direct runner and confirm exact byte
equality, including with reversed column clicks. Input bytes remain unchanged.

Case pages remain read only, bounded at 100 displayed rows, authenticated against
the manifest and exported only to a new destination outside completed reports.
No customer input or row-level output was used for new fixtures, screenshots,
skill searches, documentation or GitHub uploads. Existing private results and
operator-owned windows were not modified or closed.

## UX and review gates

- Actual rendered-pixel checks ensure dark results/case backgrounds and native
  table gutters do not retain light-system colors. Semantic text/primary/focus
  contrast tokens are tested, not assumed from a generated palette.
- Font changes propagate through styled descendants without changing other
  windows. Metric numbers reflow using their actual rendered width (4/2/1 cards),
  so million-scale counts do not lose leading digits at large text sizes.
- Runtime system-palette changes refresh only the owned workbench. Wrapped
  labels contribute their actual required height, so reopening settings with
  18-point text cannot overlap the case table and detail panes.
- Metric accessibility names include both caption and current number. Labels
  reset to "not available" rather than exposing stale numeric values.
- Progress percentages live outside the colored bar for legible contrast; stage
  completion cannot display whole-job 100% before the worker completes.
- Settings scrolling follows keyboard focus. No signal lambdas retain windows or
  panels. Existing shutdown, cancel, resume and source-order regression tests pass.
- Independent review findings (numeric accessibility, large-count clipping,
  initial case-error disclosure, palette refresh and large-text pane overlap)
  were reproduced with six failing tests and fixed. Successful case retry clears
  the partial-success warning.

Synthetic screenshots were inspected at 1280x820 and 960x720 in light/dark
themes and at 14-point native body text. Normal desktop results use the full
682-pixel viewport without an unnecessary outer scrollbar. Compact/large-text
content scrolls instead of forcing a larger window; table/detail panes remain
resizable and full paths/details remain accessible.

## Measured local performance

Standalone synthetic real-Extended-pack GUI workflow, 10,000 repeated explicit
country/blank fixtures (7,500 determined and 2,500 deliberately empty/unresolved):

- Analysis, report publication and first pending page: **4.651 seconds**,
  **2,150.05 records/second** end to end.
- Export all 2,500 pending cases: **0.082 seconds**; display limited to 100 rows.
- Peak process working set: **87,388,160 bytes**.
- This exercises cache/job/UI plumbing, not representative geographical accuracy
  or million-record acceptance. It is not a controlled speedup comparison.
- Compact DB: **142,577,664 bytes**; Extended DB: **1,087,344,640 bytes**, unchanged.

## Verification and remaining gates

Focused reviewed GUI/panel/workbench/packaging suite: **137 passed, 1 skipped**
with warnings treated as errors. The skipped case is the separate real-bundle
gate, exercised by the actual Windows packaging smoke test.

Final full regression with both real k2 packs and slow checks enabled:
**1,076 passed, 1 skipped, 2 pre-existing strict-retrieval xfailed in 185.88
seconds**, command exit 0. Source compilation and commit-range whitespace
checks passed. No changes were made to matching, job, input/output or reference
data modules relative to the previously verified address-order fix.

The actual frozen Windows build/self-test passed: workbench layout and numeric
accessibility, source-order selection, icon, stage events, summary/pending case
view, offline normalization and legacy approval refusal were exercised.
The separate local operator build was opened without closing existing windows:
`D:\WASE\out\WorldAddressEngine-workbench-20261024.exe`.
Size **48,727,076 bytes**; SHA-256
`8443d010c7214dc87b62a139a6ed5efa7d38b3177cdb7662cf3a0d9d7003e2d1`.

Both independent rechecks reported no important residual findings. Pane minima
100/64 pixels plus a 4-pixel gap were verified through compact/desktop resize,
and window collection passed with the live palette receiver connected.

This milestone does not merge main, overwrite a published release, certify inferred
accuracy or declare production readiness. Manual Windows operator acceptance,
labelled accuracy and the broader million-scale release gates remain required.
