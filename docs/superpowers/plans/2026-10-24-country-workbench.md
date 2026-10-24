# Country Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved compact side-by-side offline analysis workbench without inference/output changes.

**Architecture:** Keep the existing controller and worker contracts. Build a scoped Qt presentation module with palette-based design tokens, reorganize the existing window into a scrollable settings/sidebar and results workspace, and refine the existing results widget.

**Tech Stack:** Existing Python/PySide6/PyInstaller only; no runtime dependencies or network assets.

**Spec:** docs/superpowers/specs/2026-10-24-country-workbench-design.md

## Global Constraints

- Presentation only; country rules, source-order selection, public widget IDs and report formats remain unchanged.
- Native offline UI, semantic light/dark palette, visible keyboard focus, no remote fonts or animation.
- Existing 100-row case pages and immutable output guarantees remain.
- Continue on the current feature branch; no main merge or release overwrite.

## Review Focus

- Long file paths and long status/error text must not inflate the minimum window width.
- Narrow window and large text must retain accessible actions and scrollable inputs.
- Failed/paused/cancelled runs must not show stale result metrics or hide their diagnostics.
- Toggles/splitters/filter changes must not create QObject/Python lifetime cycles.
- Any sequence of column clicks must retain source ordering, including after layout changes.

### Task 1: Presentation tokens and workbench shell

**Files:** new gui/presentation.py; modify gui/country_app.py; new integration tests/test_country_workbench.py.
**Interfaces:** palette_tokens(dark: bool) -> dict[str,str]; apply_workbench_theme(window) -> None. Existing controller/widget attributes remain unchanged. New workbench QSplitter, settings_scroll QScrollArea, diagnostics_toggle QPushButton, diagnostics QWidget.
- [ ] Write and observe failing light/dark contrast, sidebar/splitter, compact geometry and diagnostics tests.
- [ ] Implement scoped presentation tokens, layered native surfaces, primary/secondary actions and focus styles.
- [ ] Reorganize the existing fields and results; add scrollable sidebar and collapsed diagnostics; keep worker/mapping semantics unchanged.
- [ ] Run GUI/selection-order regression and commit.

### Task 2: Compact results panel

**Files:** gui/country_results.py; tests/integration/test_country_results.py.
**Interfaces:** preserve CountryResultsPanel properties/signals/methods. New metric_cards list of QFrame, metrics_grid QGridLayout, case_splitter QSplitter. Semantic properties workbenchRole and tone are used by the shared presentation styles.
- [ ] Add failing compact metric reflow, split detail/table, read-only and numeric alignment tests.
- [ ] Refine four metric cards, country/case table density, status labels and full-address detail splitter; keep counts and case data unchanged.
- [ ] Test baseline panel contracts and QObject collection; independently review and commit.

### Task 3: End-to-end validation and operator build

**Files:** tools/gui_entry_point.py; tests/unit/test_windows_packaging.py; milestone receipt.
- [ ] Add a failing frozen-bundle workbench layout attestation test, then strengthen real self-test.
- [ ] Verify synthetic preview/analyze/cancel/resume/pending/export flows and source-order equivalence; inspect synthetic light/dark, compact and large-text screenshots.
- [ ] Run full real-pack regression, build and smoke-test separate EXE; independent whole-change review and fixes.
- [ ] Record commit, test counts, measurements, unchanged DB sizes and remaining acceptance gates; push existing draft PR and open new operator build.

## Execution

Keep D:\WASE and the installed packs/operator setup. Main owns presentation.py,
country_app.py and integration/build validation; a disjoint helper owns the
results panel and its tests. Reviewers never access private customer inputs.
