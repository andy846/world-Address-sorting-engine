# Hong Kong regional candidate validation — 24 October 2026

Historical receipt. The operator approved partial-source quarantine on
25 October; see [the continuation validation](HK_REGIONAL_VALIDATION_2026-10-25.md)
for real-pack results. The failed strict audit below is not rewritten.

This receipt covers code and the **regional-disabled** repeated workload.
The official real HK pack gate is blocked; no regional-enabled real-data or
million-row result is claimed. v0.1.0 remains GitHub Latest.

## Code and packaged application

- Source regression with both real k2 packs and slow integrity checks:
  **1,487 passed, 1 skipped, 2 pre-existing strict-retrieval xfails in 224.25s**.
- Independent reviews covered registry/jobs, matcher, builder, GUI and final
  integration. All reported code findings have RED/GREEN regressions, including
  the benchmark-verifier defect that could conceal the wrong regional setting.
- Actual Windows one-file candidate passed its synthetic offline self-test,
  including regional selection and conflicting house-number rejection.
  The earlier failed self-test fixture was corrected and rebuilt.
- EXE: 48,760,746 bytes, SHA256
  `b09d0e6c28fa0b25ef4b483112d68282f8149b97dcc811b4e3dd5e5adce27c18`.
- Wheel: 194,789 bytes, SHA256
  `c8c229cb7719653245a8bbcd1179e98b7cd4b18dbd3142ebddcd09a8bf49b24e`.
  Installed-wheel module location/version, catalogue, Chinese conversion and
  regional CLI/module smoke passed.

## Original file regression

The original 9,604-row file was replayed locally with the regional option
disabled. It produced 7,143 determined, 2,419 inferred and 42 unresolved records.
All three report CSVs are byte-identical to the reviewed v0.1.0/rules4 baseline.
The source, row outputs, oracle and checkpoints remain private and ignored.

## Repeated million workload

The operator-requested construction is unchanged: 9,604 original rows plus 396
labelled public institution controls form a 10,000-row block, repeated 100
times. There are 9,606 distinct address/hint keys. The original predictions are
consistency references, not verified labels. Public controls have independent
labels; their repetitions do not create additional distinct test addresses.

Runtime commit: `cfd8779c413d73a06751120f7fb779d5dfdc13ac`.
Runtime source SHA256:
`11afe323373d54c214976b81658e6412a26d4bc2885b1732fbc5b4867146daee`.
Tracked documentation was being updated; the tool verified the code fingerprint
and Git identity remained unchanged through every measured run.

Private dataset: 132,199,207 bytes, SHA256
`5e2b972e9277e80426c40332de55ec2b6f133c78bcf50ad0ee1251186b2e09bc`.
Regional selection is explicitly null and is checked against each completed
manifest, including the run used for recovery comparison.

| Measurement | Result |
|---|---:|
| Complete uninterrupted records | 1,000,000 |
| Complete elapsed | 158.456 seconds |
| Complete throughput | 6,310.89 records/second |
| Peak process working set | 74,280,960 bytes |
| Peak checkpoint size before completion | 857,393,236 bytes |
| Completed report files | 173,100,270 bytes |
| Classifier calls, including final verification | 2,000,000 |
| Actual uncached inference calls | 9,606 |
| Determined / inferred / unresolved | 753,900 / 241,900 / 4,200 |
| Cooperative cancellation boundary | 500,000 committed rows |
| Cancel leg elapsed | 48.911 seconds |
| Cancel checkpoint retained | 428,536,083 bytes |
| Fresh-process resume elapsed | 159.043 seconds |
| Resume peak working set | 74,444,800 bytes |

Fresh-process resume completed all 1,000,000 records; cancellation and resume
used different processes (19,256 and 45,608). All three report CSVs and the
manifest are byte-identical to the uninterrupted run. Both completed runs
removed their sensitive plaintext checkpoints. Exhaustive per-row verification
passed for both 1,000,000-row runs (10.355s / 10.903s). Every repeated original
row matched its consistency oracle, and all 39,600 inserted control rows
matched their labels. The three uninterrupted report CSVs are also
byte-identical to the v0.1.0 repeated-million baseline.

This single local measurement does not establish a speedup or a controlled
performance comparison with v0.1.0. It does not test million-distinct workloads,
global accuracy, GUI interaction at that scale, 5M rows or power-loss recovery.

## Reference data and outstanding gate

Real global packs remain unchanged: Compact 142,577,664 bytes and Extended
1,087,344,640 bytes. The preserved ALS archive is 20,777,483 bytes; no final HK
DB size exists because strict validation failed. See the
[source audit](HK_ALS_SOURCE_AUDIT_2026-10-24.md) and
[implementation ledger](superpowers/plans/2026-10-24-hk-bilingual-regional.md).
Regional-enabled real-pack measurements and a data release require the source
policy decision or a corrected official snapshot.
