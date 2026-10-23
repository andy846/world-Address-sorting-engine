# Country GUI Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a recognizable Windows app, honest live progress and a usable completion/case-review view.

**Architecture:** Extend the existing Qt window and worker. Add an optional structured runner callback, a streaming report case reader/exporter and a bounded Qt results panel. Icon assets are package resources.

**Tech Stack:** Python 3.12+, PySide6, csv, existing PyInstaller; no new runtime dependencies.

**Spec:** docs/superpowers/specs/2026-10-24-country-gui-feedback-design.md

## Global Constraints

- Default pending cases are UNRESOLVED; INFERRED is a separate filter.
- Country classification rules remain unchanged; offline only.
- Bounded pages of 100; no report/input mutation or private data uploads.
- Existing integer progress callbacks remain compatible.
- No merge or published-release overwrite; retain existing feature branch.

## Review Focus

- Small jobs below batch size must report activity before first commit.
- Stage completion must not imply completed exports; cancellation stays resumable.
- Empty/all-success cases must display zero pending, not stale preceding results.
- Long/multiline/formula-like input and duplicate original Country_Code headers preserve positional data.
- Worker cancellation, paging/filter changes and new jobs must not expose stale rows or overwrite files.

### Task 1: Structured runner progress

**Files:** jobs/country_analysis.py; new tests/integration/test_country_progress.py.
**Interfaces:** analyze_job/resume_analysis gain optional on_event(dict); events use stage, processed, committed, total (optional), status_counts (optional).
- [ ] Add failing synthetic tests for stage order, early progress, legacy callbacks, verification/export and cancellation/resume.
- [ ] Add throttled stage events without changing checkpoint or classifier contracts.
- [ ] Run runner/preflight/progress tests, independently review and commit.

### Task 2: Icon and packaging

**Files:** resources/wase.svg and wase.ico, gui/branding.py, tools/package_windows.py, pyproject.toml, tests/integration/test_branding.py.
**Interfaces:** apply_branding(window) sets window/app icon and Windows taskbar identity; packaging includes actual ICO.
- [ ] Add failing resource/runtime/package argument tests.
- [ ] Create original globe/routing art and multiresolution ICO; integrate wheel and frozen resources.
- [ ] Test resource loading from unrelated working directories and review packaging diff.

### Task 3: Streaming case review

**Files:** gui/country_cases.py and gui/country_results.py; new unit/integration tests.
**Interfaces:** load_case_page(output, mode='pending', after_record=0, limit=100, address_columns=(), cancel_requested=None) returns rows/has_next/cursor; export_cases streams all matching rows into a new CSV. CountryResultsPanel handles read-only rendering and emits page/export requests.
- [ ] Write failing filter/page/empty/malformed/multiline/formula/export-no-overwrite tests.
- [ ] Implement bounded positional report pairing and atomic exclusive exports.
- [ ] Test Qt panel metrics, filters, navigation, no-results and disabled states.
- [ ] Commit tested report reader and panel.

### Task 4: Window integration and validation

**Files:** gui/country_app.py, gui/app.py (worker signal), tests/integration/test_country_gui.py, tools/gui_entry_point.py (bundle validation).
- [ ] Add failing stage/timer/summary/pending worker/paused/cancelled/stale-state tests.
- [ ] Integrate detailed worker signal, timer, stage display, results tabs and asynchronous case actions; keep existing counts/summary contracts.
- [ ] Run focused suites then full pytest with real k2 packs/slow checks; inspect synthetic UI image.
- [ ] Build separate local EXE and pass frozen self-test; open for user testing.
- [ ] Independent whole-change review, address actionable findings, record measured results and remaining gates; commit/push existing draft PR only.

## Execution Notes

Continue in D:\WASE on the existing feat/country-code-analysis branch so the
operator's local test setup and installed packs stay usable. Do not create a
second checkout or alter user-owned running windows. Delegate disjoint backend
progress and branding tasks while the main worker builds case UI and integration.
