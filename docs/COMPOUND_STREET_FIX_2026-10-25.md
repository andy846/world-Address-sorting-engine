# Compound street country-evidence correction — 25 October 2026

Historical bugfix receipt. The operator subsequently accepted manual testing;
[v0.2.0 formal deployment](releases/v0.2.0-validation.md) now freezes this
business behavior with the formal version identity.

Runtime commit `a99d94e`, country rules `2026-10-25.country.7`. This corrects
the two public errors documented against fc19ef6; the published TEST data pack,
original source, SQLite databases, v0.1.0 Latest and main remain unchanged.

## Cause and resulting behavior

Both real Compact and Extended packs interpreted `Lai` inside
`288 LAI CHI KOK ROAD` as TD (place 2429296), and `Yan` inside
`2A YAN HING STREET` as MY (ADM2 1735487). The old evidence filter excluded
only names immediately followed by a street/building suffix. Earlier words
inside compound street names survived and supplied the whole country estimate.

The corrected global evidence filter masks numbered Latin street spans before
checking place occurrences. It recognizes streets within comma/semicolon
fragments, then retains full-line normalization for aliases such as Washington,
D.C. An explicit boundary marker prevents joining words across a removed street
into a fabricated city. Independent city occurrences, same-name destinations
on another line/fragment, country hints and explicit foreign countries retain
their existing paths. The input-size cap and bounded street-word matching remain.

Without the optional regional pack the two public inputs are now unresolved
rather than misassigned abroad. With the verified ALS pack both become
`INFERRED HK / HK_REGIONAL_ADDRESS_MATCH` from their official building/street
pair. Regional matching still never overrides an assigned country result; the
false global evidence is removed first. No specific address whitelist or
database edits are used. Old rules6 checkpoints/oracles must not be relabelled.

## Test and review evidence

- Initial reproductions: 16 failed / 32 passed, including both actual global
  packs. Targeted first correction: 245 passed.
- Long-house-number guard: failed with TD before allowing arbitrary digit
  lengths within the existing input cap. Street-role detection must not make
  long numeric input a new source of foreign evidence.
- Independent review found a punctuation regression in the first correction.
  Washington, D.C. and New, Delhi both failed before the fix. Full-line alias
  matching was restored while street masking remains fragment-bounded.
- Final focused country/context/recall tests: **226 passed in 11.93s**.
  Includes independent same-name city, comma/line boundaries, explicit foreign
  country/conflict and anti-joining guards. Complete real-pack checks are also
  part of the final full regression below.

## Frozen public bank and private replay

The complete case-bank bytes are identical to the earlier failed bank, SHA256
`88b4c839171f07e25a51bd895ee66fd515efb05b90488e24244ba1ec3ee1339b`.
No source selection, expected country or case text was changed to fit the fix.

Final rules7 report: **336 cases passed, zero failures**; 48/48 direct
regional positives and 48/48 final HK-positive country labels. All 144 explicit
foreign and 144 insufficient/contradictory-component cases passed. There are
45 eligible regional upgrades, with all 155 new-global-baseline assignments
preserved when enabling the pack. The lower baseline count reflects withdrawal
of six false street-homonym country assignments; it is not a preservation
comparison between rules6 and rules7. This remains a small, selected,
source-derived smoke bank, not a global accuracy estimate or deliverability test.

Independent comparison against the saved rules6 report confirmed exactly six
case changes: the two positives TD/MY to HK, and their four wrong-house or
street-only counterparts TD/MY to unresolved. The other 330 complete results
and all 336 direct regional matcher results are unchanged. Thus no foreign
control was silently reassigned and no insufficient pair was promoted to HK.

Private source: 9,604 original rows, both regional-disabled and enabled under
the final frozen rules7 code. All three CSV files are byte-identical to the
reviewed rules6 baseline, confirmed against actual file hashes and row counts.
7,143 determined / 2,419 inferred / 42 unresolved; zero changed country codes
or diagnostics, all original fields/order/duplicate rows preserved. No private
addresses or row-level results are published. The fix does not resolve those 42.

The earlier rules6 million-row timing/recovery receipts remain historical
measurements of that runtime. They are not relabelled as rules7 results.
The final regression covers ordinary cache, jobs, metadata and recovery guards;
this bugfix does not claim a new million-row throughput measurement.

## Final regression, CI and local candidate

- Full local regression with both real global packs, actual regional pack and
  slow checks: **1,738 passed, 1 skipped, 2 pre-existing xfails in 358.66s**.
  The optional actual-build test is skipped in that suite; the separate actual
  Windows build/self-test below passed. Source was frozen throughout this run.
- [Release validation 40159872972](https://github.com/andy846/world-Address-sorting-engine/actions/runs/40159872972):
  all jobs succeeded at a99d94e. Linux with both real global packs: 1,509 passed,
  93 skipped, 2 xfailed in 119.67s; fresh installed wheel acceptance passed.
  Windows: 1,422 passed, 319 skipped in 342.64s; actual built EXE
  (49,329,060 bytes) passed its offline self-test. Remote regional fixtures are
  synthetic; the actual ALS pair/case-bank checks ran locally.
- [Windows regression 40159872925](https://github.com/andy846/world-Address-sorting-engine/actions/runs/40159872925):
  1,423 passed, 318 skipped in 308.40s, including actual packaging.
- New local candidate: `out/v0.2.0rc1-country-r7-20261025/WorldAddressEngine.exe`,
  **48,768,859 bytes**, SHA256
  `3637ece9609602b5f6705b0c7a943703d774cc7d228db59f69655f9a9bbbb973`.
  Actual frozen offline self-test passed, including GUI completion, partial
  source display, selected regional pack, house-number rejection and pinned
  quarantine identity. Existing candidate files are retained.
- Wheel: 198,259 bytes, SHA256
  `d4aceff11503c71ffcb8e4367d3e2ac481a104eadc4c3ff2cea3bdf63a81c8e4`.
- Runtime source SHA256:
  `12ecbbb2c728c99ec2d1abee7325fadcca0ca39aea3353319b1a83945e5bd983`.

Database sizes unchanged: Compact 142,577,664 bytes, Extended 1,087,344,640
bytes, optional HK 747,376,640 bytes. Existing release tags/assets and main are
preserved. Draft PR #3 contains the source fix; no new formal application
release or production-readiness claim is made. For real pair resolution in the
candidate, explicitly enable the installed Hong Kong regional pack and start
a new rules7 analysis. The remaining 42 private unresolved cases are unchanged
and require a separate local investigation.
