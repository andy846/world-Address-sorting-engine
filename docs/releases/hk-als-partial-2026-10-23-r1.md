# Hong Kong ALS partial-source TEST data pack

This independent data prerelease is for the WASE `0.2.0rc1` development
candidate. It does not replace the formal application release `v0.1.0`, change
GitHub Latest, or certify production readiness. The regional option is off
by default and only supplements eligible unresolved country estimates.

The operator approved quarantining 9,508 invalid features from the preserved
23 October ALS snapshot. Only 174,456 valid features entered projection;
1,241 exact projected duplicates coalesced into **173,215 addresses**, with
150,092 building identities and 1,258,249 language aliases. Original source
and schema remain unchanged. A hashed quarantine receipt identifies every
excluded feature by archive member and one-based position.

The ZIP contains `pack.db`, `manifest.json`, `audit.json`, `quarantine.jsonl`,
`ATTRIBUTION.txt` and installation notes in a versioned folder. Keep them
together. The separately required global GeoNames database is not included.
No private customer addresses, test input, row results or benchmark oracles
are included.

- SQLite: 747,376,640 bytes; SHA256
  `bd5edd2eaacbfe9459df27d7c338899c29bdaa828c76bb13573799077a926ac8`.
- ZIP: 228,726,810 bytes; SHA256
  `3ca4bf9a4302b1a893890a014dfed39697a14106aba6e9f49bd0952f50bc29bd`.
- Source validation: partial; 183,964 features read, 9,508 quarantined.
- Integrity, foreign keys, indexes, counts, actual hashes, receipt and
  final ZIP members verified offline.

Use the development branch's installer, or extract under `packs` and select
the versioned `pack.db` through the optional Hong Kong setting. Installation:

```powershell
python tools/install_hk_regional_pack.py --source-dir extracted/hk-bilingual-als-2026-10-23-r1-partial --active-root packs
```

Public smoke controls passed 48/48 direct regional positives, 144/144 explicit
foreign controls and 144/144 component/contradictory-number controls. Final
country labels still have **two pre-existing MY/TD global-classifier errors**
among 48 Hong Kong positives. Those assignments remain protected by the
unresolved-only policy. All-label QA is therefore FAILED; the application
remains a test candidate. The original private input still has 42 unresolved
cases; enabling the pack did not improve that input's reports.

Full local regression: 1,701 passed, 1 skipped, 2 pre-existing xfails. The
rebuilt Windows EXE passed its actual offline self-test.
Real-pack repeated million: 183.661 seconds enabled, 149.293 seconds disabled;
cancel at 500,000 and fresh-process resume passed exhaustive verification.
All three CSVs agree across full/recovery and enabled/disabled runs; all 39,600
public labelled control rows per run match. This is 9,606 distinct keys
repeated, not a million unique-address accuracy test. See
[the dated validation report](../HK_REGIONAL_VALIDATION_2026-10-25.md) for
performance, recovery, CI, review evidence and sampling limitations.

Source: [Address Lookup Service, Digital Policy Office, Hong Kong SAR Government](https://www.als.gov.hk/data/ALS-GeoJSON.zip).
Data ownership and attribution remain with the Government and DATA.GOV.HK;
reuse is subject to [the original terms](https://data.gov.hk/en/terms-and-conditions).
Reference data are not relicensed under the software license. No exhaustive
Hong Kong coverage, global accuracy or deliverability claim is made.
