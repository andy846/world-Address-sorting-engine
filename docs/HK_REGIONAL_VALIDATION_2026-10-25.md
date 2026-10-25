# Hong Kong partial-source test pack — 25 October 2026

Historical receipt for fc19ef6 / country rules6. The two label errors below
were subsequently fixed in country rules7; see the separate
[correction report](COMPOUND_STREET_FIX_2026-10-25.md). The runtime, benchmark
measurements and publication identity in this receipt are not rewritten.

Application runtime: `fc19ef6`, candidate `0.2.0rc1`, country rules
`2026-10-25.country.6`. The existing `v0.1.0` formal release and GitHub Latest
remain unchanged. This report concerns an optional, separate TEST data pack.

## Source and installed data

The operator explicitly approved quarantine of all 9,508 invalid features.
Default builds still fail on any invalid feature. Raw official ZIP, official
schema and historical failed strict audits are retained without modification.

| Measure | Actual result |
|---|---:|
| Official features read | 183,964 |
| Valid features | 174,456 |
| Quarantined features | 9,508 |
| Exact projected duplicates among valid features | 1,241 |
| Indexed addresses | 173,215 |
| Building identities | 150,092 |
| Aliases (English / Traditional / derived Simplified) | 419,863 / 419,193 / 419,193 |
| SQLite bytes | 747,376,640 (712.754 MiB) |
| Build/audit seconds | 488.498 |
| ZIP bytes | 228,726,810 |

SQLite SHA256: `bd5edd2eaacbfe9459df27d7c338899c29bdaa828c76bb13573799077a926ac8`.
ZIP SHA256: `3ca4bf9a4302b1a893890a014dfed39697a14106aba6e9f49bd0952f50bc29bd`.
Quarantine SHA256: `89a5ed2e9b21587b1048c3008584f61044dadeb5aa98ad017a680bef1c35858c`.

Installed offline at `packs/hk-bilingual-als-2026-10-23-r1-partial/pack.db`.
Full integrity, foreign keys, indexes, counts, actual hashes and the complete
quarantine receipt were checked. The final ZIP was reopened and every member
streamed through hash/CRC verification against the installed bytes. It contains
only public reference data, attribution and receipts. Customer rows are absent.

Existing global DBs remain unchanged: Compact 142,577,664 bytes and Extended
1,087,344,640 bytes. Regional data supplement the Extended pack in the real-data
checks below; they cannot replace the global database.

Source attribution remains with the Hong Kong SAR Government / Digital Policy
Office and DATA.GOV.HK, under [the original terms](https://data.gov.hk/en/terms-and-conditions).
Data are not relicensed under the software license.

## Accuracy and compatibility

The deterministic public bank selects four eligible official address identities
per HK/KLN/NT region before prediction, then freezes 336 cases. It is a narrow
source-derived smoke bank, not a random or held-out global accuracy assessment.
Simplified aliases derive from the same official bilingual records.

| Check | Result |
|---|---:|
| Direct regional positives, four language forms | 48 / 48 |
| Explicit foreign controls (JP, GB, CN) | 144 / 144 |
| Component-only / contradictory-number controls | 144 / 144 |
| Previously assigned public results changed | 0 / 161 |
| Eligible previously unresolved cases upgraded to HK | 43 |
| Positive cases with final country HK | 46 / 48 |
| All-label QA | **FAILED: two pre-existing country errors** |

The two English positives are MAN ON BUILDING / LAI CHI KOK ROAD (TD) and
TAI PO MERCHANTS ASSOCIATION / YAN HING STREET (MY). The global geographic
leader assigns these before regional fallback; the approved unresolved-only
policy preserves those assignments. They are recorded as errors, not relabelled
as successful cases. Changing assignment precedence requires a separate tested
accuracy change. This blocks promotion of the application as a new formal release.

Public case-bank SHA256:
`88b4c839171f07e25a51bd895ee66fd515efb05b90488e24244ba1ec3ee1339b`.
The tool `tools/validate_hk_regional_public.py` reports every case and exits 1
when labels fail; it does not suppress the two errors.

The original private 9,604-row input was rerun under rules6 with the pack both
disabled and enabled: 7,143 determined, 2,419 inferred, 42 unresolved. All three
CSVs are byte-identical to the reviewed baseline. This pack provides no extra
resolved private rows on this input. Source fields/order/duplicates remain intact.
Private inputs, row outputs and repeated-workload oracles stay local and ignored.

## Regression and review

- Full local regression with real global packs and slow checks: **1,701 passed,
  1 skipped, 2 pre-existing xfails in 260.57 seconds**.
- Cache/public-validator focused tests: 73 passed in 13.36 seconds.
- Independent reviews found quarantine metadata/locator grammar defects,
  paired-query fallback suppression, unbounded query work and an ABA verification
  cache race. Each received failing-then-passing regression coverage.
- The protected temporary SQLite snapshot binds SQL checks to the bytes whose
  hash is cached. The original independent ABA reproducer now rejects the bad
  source, retains no cache receipt and rejects subsequent static calls.
- After an initial agent usage interruption, the independent reviewer completed
  the bounded review of fc19ef6: no remaining Important/Critical defects in the
  protected snapshot cache or limited company-alias guard review. It confirmed
  ABA rejection, empty cache on failure, verification levels and cleanup.
- A separate reviewer checked the saved public bank against r1: unchanged bytes,
  48/48 direct positives, 43/43 eligible upgrades, 161/161 assignments preserved,
  190/192 country-labelled cases correct. It confirmed the two failures and
  found no important validator issue.

Remote CI for exact runtime commit fc19ef6:

- [Release validation 40157329609](https://github.com/andy846/world-Address-sorting-engine/actions/runs/40157329609):
  all jobs succeeded. Linux installed both real global packs; 1,476 passed,
  89 skipped, 2 xfailed in 114.61s. The fresh installed wheel, catalogue,
  Chinese conversion and CLI checks passed. Windows: 1,393 passed, 311 skipped
  in 512.68s; built EXE 49,329,252 bytes and actual offline self-test passed,
  including both partial-source and quarantine-identity assertions.
- [Windows regression 40157329613](https://github.com/andy846/world-Address-sorting-engine/actions/runs/40157329613):
  1,394 passed, 310 skipped in 264.48s, including the actual packaging test.
- These remote jobs use real global packs on Linux and synthetic regional
  fixtures; actual 747 MB regional-pack QA and private replay were local.

Rebuilt local Windows EXE: 48,767,534 bytes, SHA256
`c012f72bff270916dad1c53acaea8b0b8f64ae49a098ff5a0835fd643e41bb4d`.
Actual frozen offline self-test passed. Its size differs from the CI build
because the host/runtime dependency environments differ. Neither is a new
formal application release.

## Repeated-million performance and recovery

The original 9,604 rows plus 396 rows cycling through four source-labelled
public addresses formed one 10,000-row block, repeated 100 times. Enabled and
disabled datasets have identical bytes and 9,606 distinct classification keys.
This is a repeated-workload throughput/recovery test with substantial memoized
reuse, not a million distinct regional addresses or a classification accuracy
test. All private oracles remain local. The 39,600 public control rows are
independently labelled; the source-derived regional controls are tested above.

All measured processes used fc19ef6, runtime source SHA256
`30018e8b22cc9a127e16a345086ee3399ac4f5322abec7361e8bea8cda9446fe`.
The tracked tree was dirty only with the in-progress documentation reported
here. No runtime edits/commits, builds or other test suites ran during timing.

| Run | Records | Seconds | Rows/s | Peak process RSS bytes | Peak checkpoint bytes |
|---|---:|---:|---:|---:|---:|
| Regional disabled, uninterrupted | 1,000,000 | 149.293 | 6,698.25 | 75,087,872 | 856,393,235 |
| Regional enabled, uninterrupted | 1,000,000 | 183.661 | 5,444.82 | 78,045,184 | 861,393,966 |
| Regional enabled, cancel | 500,000 | 78.342 | — | 76,185,600 | 430,536,813 |
| Regional enabled, fresh-process resume | 1,000,000 completed | 197.167 | — | 77,598,720 | 861,393,966 |

These are single sequential observations on one host, not a controlled speedup
claim. Cancel and resume used different processes (21124 and 38804), and all
four measured legs had the same runtime fingerprint. Resume time includes
restoring/validating the first 500,000 rows and exporting all 1,000,000 rows;
it is not a throughput figure for only the remaining half.

Exhaustive streaming verification passed separately for disabled full, enabled
full and enabled recovery. Every source cell, row order, country code,
diagnostic, count and report hash matched its one-block oracle. The 39,600
public control rows per run matched their source labels. All three CSV files
are byte-identical across enabled/disabled/recovery, and the enabled full and
recovery manifests are byte-identical. All completed plaintext checkpoints
were removed. Reports contain 753,900 determined / 241,900 inferred / 4,200
unresolved rows; the latter are the original 42 repeated 100 times.

Completed report bytes including manifest: 173,100,270 disabled and
173,101,028 enabled. Only regional manifest identity differs. A documentation
review caught a premature performance/recovery reference while measurements
were still pending; this final receipt supplies the actual results.

The local wheel also built successfully using existing build tools offline:
198,028 bytes, SHA256
`0b06efd7669f7ba940f965285d49028b248693455d54332eb3eae95e1d0adbb1`.
Initial local pip attempts failed due to sandbox DNS/temp paths; setting the
workspace TEMP and disabling build isolation avoided downloading build tools.
Installed-wheel acceptance is independently covered by the successful Linux CI.

## Published test data and preserved formal release

[Hong Kong ALS partial-source TEST data prerelease](https://github.com/andy846/world-Address-sorting-engine/releases/tag/hk-als-partial-2026-10-23-r1)
is published as release ID 423126651, prerelease=true, draft=false, latest=false.
Its annotated tag targets tested runtime fc19ef6. All four remote asset sizes
and GitHub SHA256 digests exactly match the locally verified files.

Post-publication verification confirmed v0.1.0 is still Latest (release ID
422605557, target 13ed06a75335da31daad2fc797f7012e07bb043c), with all three
original asset sizes and SHA256 digests unchanged. Main remains
6fb302dd30bbed14dbc369da406a13bb488c2c54. Draft PR #3 was updated with these
receipts and limitations; it and PR #2 retain their original bases and Draft
state. The 0.2.0rc1 application remains a local/CI candidate, not a new formal
release. Documentation-only commits do not change the tested runtime hash.

No exhaustive coverage, deliverability, million-distinct throughput or
production-readiness claim follows from these results. The regional option is
off by default, and global GeoNames data remain separately required.
