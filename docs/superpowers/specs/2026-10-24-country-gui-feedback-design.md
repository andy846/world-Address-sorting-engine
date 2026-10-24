# Country GUI Feedback Design

## Intent and approval

The operator approved the proposed icon, detailed offline analysis progress,
and completion summary with actionable cases on 2026-10-24. Default pending
cases are UNRESOLVED (including reader input errors); INFERRED is a separate
filter, not a failure. Country classification rules remain unchanged.

## Approach

Extend the existing PySide6 application, not a second web UI. Keep the native
look and input workflow. A persistent results area has Country summary and
Cases tabs, with a completion overview and bounded, read-only case pages.
A modal completion dialog would obscure the results and is rejected. Loading
every recipient into a table is rejected because million-row jobs must remain
memory bounded. Do not implement corrections or mutate completed reports.

## Requirements

- Original globe/address-routing vector icon, multiresolution Windows ICO,
  packaged with the application and used by EXE, windows and taskbar identity.
- Preserve integer committed-count callbacks and add optional structured
  events: input validation, source hashing, loading reference data, restored
  record verification, classification, output verification/export, finalizing,
  complete/paused/cancelled. Events contain counts/stages only, never addresses.
- Refresh elapsed time even during hashing/loading; show stage count, committed
  count and stage throughput. Show a percentage only for a known stage total;
  classification reaching EOF is not whole-job completion. Do not invent ETA.
- Completed view shows total, determined, inferred, pending, country count,
  elapsed time, coverage (explicitly not accuracy), and output location.
- Pending/inferred/all case filters show logical source record number, address,
  status, code, reason and candidate codes. Explain record numbering, including
  that blank XLSX rows may be skipped. Do not call this a physical worksheet row.
- Stream paired Classified_Addresses.csv and Country_Diagnostics.csv on a worker,
  with bounded pages of 100 rows and previous/next navigation; cancellation and
  malformed/mismatched reports fail visibly. No customer rows in logs.
- Export the entire selected filter (not just the page), UTF-8 BOM CSV with
  spreadsheet-formula protection, exclusive publication/no overwrite. Default
  destination is outside completed report files. Never change original inputs,
  completed report files or their manifest, even on export failure/cancellation.
- Failure/paused/cancelled states must not present a completed summary or stale
  case data. Cases load/export asynchronously; controls prevent overlapping jobs.
- Keep existing source/pack validation, immutable output and approval safeguards.

## Validation

Synthetic TDD for stages, small jobs, cancellation/resume, empty results, case
filtering/paging/export integrity and window transitions. Full real-pack
regression and frozen offline bundle self-test. Inspect a synthetic screenshot;
open a separately named new local EXE for the operator without closing old ones.
No private source or row-level report is uploaded. Do not overwrite releases or
merge main. Manual Windows operator acceptance remains a user gate.
