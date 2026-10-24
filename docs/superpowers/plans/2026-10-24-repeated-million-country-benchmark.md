# Repeated million-row country benchmark implementation plan

**Goal:** Execute the operator's AAAAA.csv plus verified-public-controls,
whole-batch-times-100 benchmark locally, without uploading private addresses.

**Architecture:** A separate streaming benchmark tool prepares a private CSV,
executes the unchanged country-analysis runner in fresh worker processes, and
verifies every exported row/result against the source block and controls. An
independent recovery run pauses/cancels and resumes from a fresh process.

**Tech stack:** Python standard library, existing country runner, real Extended
k2 SQLite pack, pytest. Existing branch and published releases are preserved.

**Spec:** The user's 2026-10-24 instruction to reuse AAAAA.csv, insert verified
addresses, and duplicate the whole list 100 times.

## Rulings and constraints

- 9,604 original rows + 396 controls = 10,000 rows; repeat the complete block 100
  times = 1,000,000. Preserve original cells/IDs; add independent cycle/base-row
  columns for positional verification. Never add a trusted Country hint column.
- Controls are four official public institution addresses (GB, SG, NZ, AU),
  each repeated 99 times, not 396 independently verified unique addresses.
- Original country predictions are consistency checks, not accuracy labels.
- Record real distinct-address count, cache behavior and repetition pattern;
  do not reorder into adjacent duplicates to inflate performance.
- Generated source/checkpoints/reports stay in a new ACL-restricted ignored
  directory. Only aggregate measurements and public controls may enter Git.
- Test the shipping classifier first. Any necessary performance fix requires
  measured evidence, separate RED/GREEN tests, independent review and disclosure.

## Tasks

- [x] Implement private streaming preparation and exact expected-count oracle,
  with synthetic RED/GREEN tests for fields/order/duplicates and refusal to
  overwrite, unsupported/colliding metadata columns and incomplete source rows.
- [x] Implement fresh-process run/progress/validation, streaming full row/result
  comparison, source/baseline hash preservation, numeric RSS/disk metrics and
  cooperative cancellation/resume; test with a small synthetic pack/workload.
- [x] Independently review tooling and controls, fix important findings, run
  full regression and commit the reproducible public tool.
- [x] Prepare and run the private million-row workload; verify completion,
  summary arithmetic, controls, no lost/shifted rows and checkpoint cleanup.
- [x] Complete recovery comparison in fresh processes, report measured times,
  peak memory and sizes, limitations and remaining low-duplication/5M gates.

## Acceptance

One output for every logical input row; all originals preserved under the
existing spreadsheet-safe export contract; cycle/base-row order exact; all
39,600 control rows have their labelled code; all original replicas have the
same code/status/reason/candidates as the baseline, counts match the multiplied
oracle, and resumed reports are byte-identical to uninterrupted reports.
No estimated timing or synthetic accuracy is presented as measured evidence.

## Execution ledger

- Existing rules4 baseline: 9,604 records, 42 unresolved, 9,602 distinct
  classification keys. Only two exact address/hint duplicates in the source.
- Original 8,192-entry LRU measured 9,602 fresh inferences / 23.658 seconds in
  cycle one and 9,600 / 22.571 seconds in cycle two. Whole-block repetition
  exceeds its capacity and therefore repeatedly evicts useful results.
- Ruling: improve the application cache to 16,384 entries with an additional
  16 MiB UTF-8 key-text budget (not a total process-memory limit). Three tests
  failed first, then passed; independent cache review found no important
  residual issues. Country rules and outputs remain unchanged.
- Initial preparation tests: 11 RED failures. Reviewed preparation/orchestration
  now has 16 tests including fresh-process cancellation/recovery and dirty-code
  provenance. Verifier has 66 tests and authenticates the bytes it consumes.
- Independent findings addressed: workspace Git-ignore protection, oracle hash
  pinning/metadata agreement, explicit address-column order and runtime source
  hashing, including tracked/untracked changes while already dirty.
- Formal dataset: 1,000,000 rows, 132,199,207 bytes, whole-block repetition,
  9,606 distinct classification keys. The first provisional preparation is
  preserved but excluded from final measurements; reviewed workspace is new.
- Full real-pack regression: 1,287 passed, 1 skipped, 2 existing xfails;
  latest focused tool/verifier/cache checks: 85 passed with warnings as errors.
  Completed million-row job: 152.847 seconds, 73,265,152-byte peak working set.
  Cancelled at 500,000 rows; fresh-process resume completed in 151.896 seconds.
  Every row matched the oracle and all three CSVs were byte-identical. Detailed
  measurements and limits: docs/REPEATED_MILLION_BENCHMARK_2026-10-24.md.
