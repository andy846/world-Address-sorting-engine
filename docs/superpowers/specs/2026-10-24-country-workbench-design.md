# Country Analysis Workbench Design

## Approved direction

The user selected option 1, the side-by-side workbench, after reviewing the
alternatives (workbench versus multi-screen wizard). Extend the existing offline
PySide6 desktop application; do not rebuild it as a web application. This is a
presentation-only change. Preserve country rules, source-order column mapping,
report formats, checkpoint validation, case hashes and export safeguards.

## Layout and visual direction

- Top identity bar: existing globe/routing icon, product name, short offline
  assurance, and an input-settings toggle. Keep the existing window title.
- Horizontal resizable workbench: left scrollable input sidebar (around 320
  logical pixels), right flexible results workspace. Sidebar can be collapsed
  and reopened with the existing toggle. Keep existing completion collapse.
- Sidebar groups file/output selection, worksheet/encoding, address columns,
  and offline reference selection. Explicit labels and keyboard buddies; column
  selection stays MultiSelection and is always interpreted in source order.
- Right workspace: operation buttons, compact preview feedback, progress card,
  four metric cards, and country/case tabs. Cases retain 100-row bounded paging,
  full-address details and full-filter export. Details use a resizable splitter.
- Footer: output folder/open action remains prominent. A collapsed diagnostics
  disclosure contains source versions and bounded log; repeated internal
  summaries should not compete with headline metrics. Failures expand diagnostics.
- Follow the platform's light/dark scheme, with restrained teal for primary
  actions and amber for pending cases, consistent with the installed app icon.
  Neutral layered surfaces, clear focus, semantic badges and numeric alignment.
  No remote fonts, icon CDNs, animations, fake progress or promotional content.

## UI UX Pro Max application

Verified style lookup: data-dense-dashboard (BI/Analytics), compact spacing and
responsive metric grid. Use general accessible-table and keyboard/focus guidance.
Reject the generator's marketing landing pattern as inappropriate for this app.
PySide6 has no dedicated skill stack dataset: Qt implementation decisions are
native engineering choices, not claims of a verified Qt stack match. No private
addresses were included in search queries or persisted design research.

## Acceptance

- 1280x800: settings and usable results side by side; ordinary controls never
  clipped or hidden behind a footer. 960x720 and large text remain operable via
  sidebar scrolling, splitters and table scrolling; no oversized top-level window.
- Metric cards reflow to two columns in narrow workspaces. Full addresses remain
  available in a plain-text detail view, not HTML interpretation.
- Tab order follows the visual input order; focused input fields scroll into
  view. All buttons retain accessible text names, not icon-only controls.
- Existing GUI job/cancel/resume/selection-order, report and frozen-bundle gates
  pass. New light/dark contrast, resizing, diagnostics and layout tests pass.
- Synthetic screenshots inspected at desktop and compact sizes and with large
  text; no customer rows used for screenshots or test fixtures.
- New separately named EXE for operator testing. Do not close old user windows,
  overwrite released artifacts, merge main or upload private inputs/reports.
