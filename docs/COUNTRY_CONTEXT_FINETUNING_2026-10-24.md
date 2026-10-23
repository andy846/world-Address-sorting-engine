# Country context fine-tuning validation

## Scope and commits

User-approved corrections: distinguish HK districts/abbreviations from countries,
do not treat street/building names as destinations, respect mainland administrative
context, and recheck all rows instead of only reducing the unresolved count.

- `15f155b`: occurrence roles, contextual HK references, mainland administration,
  complete bounded per-place contributions and support recalculation.
- `42e03ac`: compound locality context and list-wide reconciliation regressions.
- Country rules identity is now `2026-10-24.country.2`. Older checkpoints cannot
  resume silently with the new rules. Strict postal approval remains unchanged.

## Fixes and independent review

- TST variants, supported Jordan street/district context, Central/Admiralty paired
  with distinctive streets, and compound locality/landmark references are handled.
  Bare Central, Admiralty, KL and NT do not default to HK.
- Country words inside buildings/streets are withdrawn from both explicit matching
  and later GeoNames retrieval; this prevents rejected evidence reappearing.
- Chinese and English Inner Mongolia remain a mainland region, not Mongolia.
  Embedded/shared neighbourhood names under a full mainland hierarchy do not
  automatically create HK conflicts. Separate geographic conflicts remain open.
- Independent review reproduced tiny-place weight amplification, street-city
  ambiguity and display-evidence truncation. Complete `(term, weight, place_id)`
  contributions now survive the display cap; each contribution is individually
  qualified and role-filtered before country support is recomputed. Thresholds
  were not lowered and batch-majority assumptions were not introduced.
- Final review reproduced true Jordan destinations incorrectly suppressed by HK
  context, building-contained regional anchors, and English Inner Mongolia.
  All received observed RED-to-GREEN synthetic regressions. Substantial independent
  Jordan locality evidence is retained; conflicting explicit countries stay open.
- Reconciliation additionally covered compound landmarks and mainland embedded
  localities. No private customer rows were copied into repository tests.

## Tests and Windows build

- 62 new synthetic context/regression cases. Country/context/retrieval target:
  149 passed. Important review findings were reproduced failing before fixing.
- Final full local suite with both real k2 packs and slow integrity checks:
  **932 passed, 1 skipped, 2 known strict-retrieval xfails in 183.27 seconds**.
- Syntax and whitespace checks passed.
- Final Windows onefile build: **48,563,291 bytes**. Frozen self-test passed from
  an empty working directory with the packaged 235-entry catalogue, both OpenCC
  converters, country-analysis GUI and synthetic outputs. Legacy production
  approval refusal also passed. No reference DB is bundled in the EXE.
- Source fixes are on the feature branch/draft PR, not a replacement of published
  alpha.2. Package-version metadata remains unchanged pending a future release.

## Whole-input aggregate comparison

The supplied private file contains 9,604 rows. Both versions' original fields,
leading-zero IDs, row order and duplicate-address consistency were checked.
Summary counts reconcile to every row. No private rows, source file, diagnostics
or checkpoint shards are uploaded to GitHub or CI.

| Measure | Published alpha.2 rules | Fine-tuned rules |
| --- | ---: | ---: |
| DETERMINED | 7,120 | 7,136 |
| INFERRED | 2,322 | 2,351 |
| UNRESOLVED | 162 | 117 |
| Rows with a code | 9,442 | 9,487 |
| Unresolved share | 1.69% | 1.22% |

- 101 rows changed codes: 62 unresolved rows gained a code, 22 previously assigned
  codes changed, and 17 previous estimates were withdrawn for insufficient evidence.
  This is not a process that only fills blanks to improve a coverage figure.
- Remaining reasons: 82 no geographic match, 26 competing plausible countries,
  9 conflicting country signals. No administrative-region conflict remains in
  this input. These are classifier outcomes, not proof the addresses are invalid.
- Complete job/export/revalidation/cleanup: **48.847 seconds**, peak job RSS
  **54,800,384 bytes**. The subsequent full comparison audit peaked at 71,794,688
  bytes. The four standard reports total **1,580,439 bytes**. This measured run
  is not a speed improvement claim or a hardware-independent performance promise.
- Plaintext checkpoint and finalization folders were removed after completion.
  Original outputs are preserved separately. Supplemental changed-code and
  unresolved extracts remain local only.
- Both installed DBs remain unchanged: Compact **142,577,664 bytes**, Extended
  **1,087,344,640 bytes**. Actual pinned hashes and integrity are covered by the
  real-pack regression suite.

## Remaining gates

Code coverage is **98.78%, not measured accuracy**. There is no fully labelled
ground-truth copy of the private file. The remaining 117 rows and changed estimates
still merit human review; do not label them invalid or guess from the batch mix.
1M/5M throughput, clean disconnected Windows operator acceptance and separate
official postal-master approval remain outstanding. No production-readiness claim
is made. Main and all published release tags/assets must remain unchanged.
