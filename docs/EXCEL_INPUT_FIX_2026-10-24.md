# Excel custom-column input fix

## Reported failure and cause

The supplied extracted XLSX uses `Page` and `Field 1` through `Field 6`, not the
standard `NAME_ADDRESS_LINE` headers. Displaying those fields in the GUI did not
mean they were selected. The recorded failed configuration had zero selected
address columns.

The runner attempted validation with `_records(...).close()`. These readers are
generators, so creating and closing one never executed its header validation.
Consequently a missing mapping was detected only after a checkpoint configuration
had been written. Retrying a new run against that directory correctly refused
to overwrite it, but the workflow was confusing. Separately, an error changed
the job state but left the main label saying `Analysis running...`.

## Corrections

- Validate CSV/XLSX headers, selected columns, worksheet and record-ID mappings
  before hashing the reference pack or creating output/checkpoint state. Validate
  lazy TXT options by advancing a closed probe. Keep valid empty input support.
- Require an explicit selection in the GUI before starting. Show the selected
  column count, instructions for multiple fields, and a taller field list.
  Arbitrary generic fields are not silently auto-selected.
- Reject occupied output paths before starting a worker, with clear new-run vs
  resume guidance. Never delete old checkpoints or overwrite previous output.
- Replace the running label when an operation fails. A failed/unfinished preview
  does not falsely claim it is ready to analyze.

Country classification rules remain `2026-10-24.country.3`; no country threshold,
mapping or postal-service logic changed.

## Verification

- Observed four failing GUI regressions before the fix. Additional synthetic
  `Page`/six-field XLSX flow verifies manual selection, preview, analysis and
  preservation of the Page field without using it as an address line.
- Input-preflight worker observed 27 failing cases before its fix. All 43 new
  preflight cases passed, including header-only invalid mappings, valid empty
  inputs, formulas without cached values, TXT and generator closure.
- Combined country GUI/preflight/runner/report target: **110 passed**.
- Independent GUI review found no actionable findings; runner changes were
  separately reviewed by the integrating agent. A synthetic UI render verified
  the field-count guidance and layout without displaying private rows.
- Windows onefile build and actual frozen self-test passed. Local EXE size:
  **48,565,188 bytes**. No reference database is bundled.
- Full local real-pack/slow regression: **981 passed, 1 skipped, 2 known
  strict-retrieval xfails in 169.51 seconds**. Final GitHub checks are recorded
  in the PR validation receipt. Existing acceptance gates remain unchanged.

## Supplied-file local verification

The source workbook and the user's previously failed output directory were not
modified. The original failed directory retains its existing configuration;
there is no automatic cleanup or silent checkpoint rewrite.

Using a separate workspace output folder, the GUI flow loaded all seven headers,
rejected an empty selection without creating output, explicitly selected the six
address fields (not Page), previewed and completed **398 rows**. **396** received
a country code and **2** remained unresolved. All original cell values, row order
and the Page column were verified against the output; the source hash was
unchanged. Plaintext checkpoint/finalization state was removed after completion.

Measured complete GUI job: **4.829 seconds**. Peak GUI-process RSS including the
verification process: **80,482,304 bytes**. These are local measurements, not a
performance promise or a measured country-accuracy claim. Private rows and
row-level reports stay local and are not GitHub/CI fixtures or release assets.

For another manual run, choose `Field 1` through `Field 6`, leave `Page` unselected,
and choose a new empty output folder. Resume only continues the original saved
configuration; it is not a way to change the previous run's address mapping.
