# Country Context Fine-Tuning Implementation Plan

**Goal:** Fix the reviewed false conflicts and missed Hong Kong/local geographic
context without reducing evidence thresholds or assuming the batch's country.

**Architecture:** Keep the existing country estimator and streaming contracts.
Add bounded role-aware country occurrences, contextual HK abbreviations/landmarks,
and mainland administrative precedence. Revalidate the whole input, including
previously assigned rare codes, not only the 162 unresolved rows.

**Spec:** User-approved corrections in the 2026-10-24 conversation, extending
docs/superpowers/plans/2026-10-23-country-code-analysis.md.

## Constraints

- No postal services, rates, Zone or Novsn logic. No batch-majority guessing.
- Keep private input, row-level evidence, checkpoints and exports local/ignored.
- Preserve old outputs and published alpha.0/alpha.1/alpha.2 bytes and tags.
- Bump country rules identity so old checkpoints cannot mix rule generations.
- Use synthetic regression fixtures, never copy private customer rows into tests.

## Tasks

- [x] Reproduce building-country, Jordan/HK, contextual TST/Central/Admiralty and
  mainland/border-region failures with synthetic RED tests; include genuine
  overseas counterparts and ambiguous bare district/abbreviation negatives.
- [x] Implement occurrence-level/context fixes and mainland admin precedence;
  run country, runner/resume and GUI regressions; commit the verified fix.
- [x] Independent review of evidence filtering and final changed code. Fix
  concrete important findings with RED-to-GREEN regressions.
- [x] Re-run the entire private input to a new output directory. Reconcile
  counts/fields/IDs/duplicates, compare every changed code, record only aggregate
  performance and before/after results in public documentation.
- [ ] Full real-pack regression and Windows frozen self-test; push the existing
  draft PR for GitHub checks. Do not merge main or replace a published release.

Local full regression and frozen self-test passed. Final task remains open until
the verified branch is pushed and GitHub checks finish; evidence is recorded in
docs/COUNTRY_CONTEXT_FINETUNING_2026-10-24.md.

## Review Focus

- Jordan the country must remain distinguishable from Jordan the HK district.
- Central/Admiralty alone and N.T./KL alone must not become HK by default.
- Country words inside buildings/streets must not override the destination.
- Explicit foreign countries/hints and genuine conflicts remain respected.
- Weak gazetteer aliases must not acquire unrelated substantial-place support.
