# Repeated million-row country benchmark — 2026-10-24

## Scope and reproducible identity

The operator requested the original private 9,604-row input, additional verified
addresses, and 100 whole-list copies. The completed benchmark uses **9,604
original rows + 396 public control rows = 10,000 rows per block**, repeated
**100 times = 1,000,000 rows**. Original cells, leading-zero IDs, duplicates,
address-column mapping and within-block order are preserved. Independent
cycle/base-row columns identify every generated row without changing addresses.

The 396 controls are **four distinct public institution addresses, 99 copies
each**, not 396 independently verified locations. Country labels were checked
from the official institution sources before insertion; they are kept outside
the classification input, never supplied as a trusted country-hint column:

| Public control | Country code | Official address source |
|---|---|---|
| British Museum | GB | https://www.britishmuseum.org/visit |
| National Gallery Singapore | SG | https://www.nationalgallery.sg/sg/en/visit.html |
| Museum of New Zealand Te Papa Tongarewa | NZ | https://www.tepapa.govt.nz/visit/plan-your-visit/getting-here |
| Sydney Opera House | AU | https://www.sydneyoperahouse.com/visit/eat-drink/bennelong |

Sources checked 2026-10-24. Public fixtures and provenance are in
`tests/fixtures/public_country_controls.json`. Only public addresses and
aggregate measurements are committed; private source/oracle/generated CSV,
checkpoints and reports stay local in an ACL-restricted, Git-ignored workspace.

Measured code: **`bd7e6d04209fc0658c4b4621e3dfb6be9f850b1a`**, clean committed
tree. Runtime-source SHA-256 before/after every worker:
`b0861b5139d1ac5c0f688f360c2ba36401a3bc97e19fef3721e6d1edc4c94b5a`.
Country rules stay **`2026-10-24.country.4`**. Cache performance change is
`0c08116`; repeat harness/oracle/verifier is `bd7e6d0`.

Dataset: **132,199,207 bytes** (126.075 MiB), **9,606 distinct address/hint
keys**. SHA-256:
`5e2b972e9277e80426c40332de55ec2b6f133c78bcf50ad0ee1251186b2e09bc`.
This is a highly repetitive workload, not one million distinct addresses.

## Measured results

Windows / Python 3.13.2, real Extended k2 pack. Each runner leg starts in a
separate OS process. Measurements use the ordinary application's country runner,
including source/pack verification, classification, checkpointing, export,
reverification and default checkpoint cleanup. Lightweight call counters observe
classification/inference without changing returned results. The harness's own
preflight checks and independent final verifier are outside runner timing.

| Run | Completed/committed rows | Seconds | Peak process working set bytes |
|---|---:|---:|---:|
| Uninterrupted complete job | 1,000,000 | **152.847** | **73,265,152** |
| Second job, cooperatively cancelled | 500,000 | **48.908** | **73,064,448** |
| Fresh-process resume through complete export | 1,000,000 | **151.896** | **75,157,504** |

Uninterrupted throughput: **6,542.49 records/second**, peak **69.871 MiB**.
Recovery's resume leg peaks at **71.676 MiB**. Cancellation plus resume takes
**200.804 seconds**, excluding the idle gap between processes. Resume verifies
all 500,000 saved records before proceeding; it does not skip source/inference
authentication to achieve a faster time.

Uninterrupted classifying starts at 1.466 s, source reverification at 77.856 s,
export at 80.834 s, finalization at 150.826 s and completion at 152.697 s.
The job makes **2,000,000 classification calls** (initial processing plus full
export reverification), with **9,606 actual inferences**; remaining calls reuse
cached results. This cache behavior is an explicit property of the workload.

Peak retained checkpoints: **856,393,211 bytes** (816.720 MiB), removed on
successful completion. Four completed reports total **173,100,244 bytes**
(165.081 MiB) per run. Both completed runs have no checkpoint/finalization
directory left. The retained private dataset/oracle/completed reports are not
deleted automatically.

## Exact validation

| Status | Count |
|---|---:|
| Determined | 753,900 |
| Inferred | 241,900 |
| Unresolved | 4,200 |
| **Total** | **1,000,000** |

Codes present: **995,800**. The unresolved count is exactly **42 x 100** from
the original baseline: 4,000 returned-mail/unknown-address markers and 200
partial-address cases. No new inconsistency is introduced by repetition.
All **39,600 inserted control rows** match their independently sourced labels.

Every generated source cell, exported cell (under the existing spreadsheet-safe
protection contract), source record number, cycle/base-row position, country
code, status, reason and candidates was streamed against the one-block oracle.
All summary counts/percentages and manifest hashes reconcile. The verifier
authenticates the exact CSV bytes it consumes and never stores a million-row
list in memory. Uninterrupted verification: **7.751 seconds**; resumed
verification plus report comparison: **8.198 seconds**.

The three report CSVs are **byte-identical** between uninterrupted and resumed
runs; the manifests were additionally checked byte-identical. Original input
and corrected 9,604-row baseline hashes remain unchanged. Worker PIDs were
distinct, code identities stayed fixed/clean, and prepared source bytes stayed
pinned throughout.

## Cache improvement and review evidence

The original source has 9,602 distinct classification keys. Its former
8,192-entry LRU cannot retain a complete repeated batch: measured cycle one
needed 9,602 inferences / 23.658 s, cycle two still needed 9,600 / 22.571 s.
The application now bounds retention by **16,384 entries and 16 MiB of UTF-8
key text**, including country hints; the text budget is not a process-memory
limit. Oversized keys still classify, without being retained. No country
classification thresholds, labels or rule identity changed.

Three failing cache regressions preceded the implementation. Independent review
confirmed 186 baseline/new real-pack comparisons, 600 budget/eviction probes
and 30 collection cycles. Separate independent tooling reviews found and fixed
workspace Git protection, saved-oracle pinning, explicit column-order handling
and code provenance while already dirty. Their final rechecks found no important
residual issues. Verifier review additionally rejected 13 rehashed corruptions
and observed stable memory between 6,000 and 60,000 synthetic rows.

Full real-pack regression: **1,287 passed, 1 skipped, 2 pre-existing
strict-retrieval xfailed in 194.02 seconds**. Latest focused preparation,
provenance, verifier and cache tests: **85 passed**, warnings as errors.
Compilation/whitespace checks passed. The separate real Windows frozen bundle
self-test passed with zero assertion failures.

Operator build: `out/WorldAddressEngine-million-batch-20261024.exe`,
**48,734,181 bytes**, SHA-256
`955fecbb86769e4e55ad0c4cd31d813d4c342999a1cb0a2ac76576054f5165af`.
Published alpha releases and existing operator binaries remain untouched.

## Reproduction and remaining gates

Use the public tool `tools/benchmark_country_repeat.py`: `prepare`, `run`,
`run --name recovery --stop-after 500000`, `resume --name recovery`, then
`verify` for each run and `verify --name recovery --compare uninterrupted`.
Every command takes an explicit local workspace; source/baseline/pack paths are
local parameters rather than committed customer paths. Preparation refuses any
existing workspace and writes its private artifacts only after applying ACL
restrictions and local Git-ignore protection. Never upload this workspace.

Final private workspace: `exports/AAAAA-repeat-million-reviewed-20261024`.
An earlier provisional preparation was preserved and excluded from measurements.
The original 9,604-row predictions are **consistency references, not human
ground truth**. Four repeated control addresses do not establish global accuracy.

This completes the requested repeated-million CSV runner and cooperative
cancel/fresh-process-resume checks. It does **not** complete one-million-unique
or low-duplication throughput, 5M processing, GUI interaction at a million rows,
abrupt termination/power-loss recovery, clean disconnected Windows acceptance,
or labelled geographical-accuracy gates. No production readiness is asserted.

Reference DBs remain unchanged: Compact **142,577,664 bytes** (135.973 MiB),
Extended **1,087,344,640 bytes** (1,036.973 MiB). Their pinned hashes and SQLite
integrity were included in regression checks.
