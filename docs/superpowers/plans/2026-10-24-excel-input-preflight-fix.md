# Excel input preflight and failure state correction

User-reported GUI failure: custom XLSX fields were not selected; failure left a
configuration-only checkpoint, subsequent retries rejected the output directory,
and the main summary still claimed analysis was running.

## Scope

- Validate the selected input schema before hashing reference packs or creating
  output/checkpoints. Creating and immediately closing a generator is not validation.
- Keep custom field mapping explicit. Show the selected count and clear guidance;
  do not guess arbitrary `Field N` columns or include metadata automatically.
- Explain nonempty output folders before starting a job. Never delete existing
  checkpoints, overwrite completed output, or silently change resume configuration.
- Show failure truthfully instead of leaving `Analysis running...` on screen.
- Reproduce using synthetic XLSX/CSV fixtures, then verify the supplied 398-row
  XLSX locally with explicit mapping and a new workspace-only output folder.
- Keep the original XLSX and the user's BBBB directory untouched. No private
  rows or per-row outputs in Git, CI or release assets. Country rules stay unchanged.

## Verification

- RED-to-GREEN invalid schema/no-state, valid empty sheet, explicit mapping,
  nonempty output preservation, selected-count and failure-summary regressions.
- Country runner/report/GUI targets, full real-pack suite and frozen EXE self-test.
- Independent review and a separate local EXE, preserving existing executables.
