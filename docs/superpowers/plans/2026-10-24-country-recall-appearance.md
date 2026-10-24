# Country recall and appearance implementation plan

**Goal:** Resolve explainable omissions from the remaining cases, expose the
existing theme choices, and state the current development stage accurately.

**Architecture:** Extend the existing occurrence-role and locality evidence;
retain explicit conflicts and source-order input contracts. Use a window-owned
System/Light/Dark selector with a persistent preference. No batch-majority
guessing or postal-service logic. This implements the user's authorized
fine-tuning and visible-theme-setting request; routine choices are the builder's.

**Tech stack:** Python, SQLite, PySide6, pytest.

## Tasks

- [x] Reproduce locality abbreviations, country substrings inside named places,
  compound territories and administrative names with synthetic failing tests.
- [x] Correct occurrence roles and bounded geographic context; bump country
  rules identity so old checkpoints cannot mix generations.
- [x] Add visible accessible System/Light/Dark control, persist only the UI
  preference, and test restart, explicit override and live system changes.
- [x] Independently review changes, especially street-only false positives,
  foreign overrides, separated genuine conflicts and Qt object lifetime.
- [x] Replay all 9,604 private rows into a new ignored folder; compare all codes,
  preserve every original field/row and record only aggregate measurements.
- [ ] Run complete real-pack regressions and frozen offline Windows self-test;
  commit/push existing draft branch and record remaining acceptance gates.

## Constraints and review focus

Never commit customer content or row-level diagnostics. Preserve old outputs,
published releases and main. Coverage is distinct from labelled accuracy.
Compound locality evidence must not erase separate destination lines. Company,
street and building words must not become standalone countries. Explicit theme
selection must survive both restart and subsequent OS theme changes. No forced
assignment of returned-mail records lacking any address.
