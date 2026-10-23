# Country Code analysis implementation

Approved purpose: input address rows -> Country_Code -> counts by Country_Code.
No air/surface, pricing, Zone or Novsn decisions. This supersedes any earlier
assumption that country statistics require a production-approved postal master.
The strict postal classifier and its approval requirements remain available.

## Interfaces and ownership

- Versioned, bundled Country Code JSON derived from the user-provided five-page
  CountryList_20250708.pdf (SHA-256
  41b84a0938c1ebe320514b29c567ceedcf9f9868e99f84f3387bb8899cf2f373).
  Preserve 236 source rows, produce 235 geographic entries; CN is canonical,
  CNS is a service-only duplicate. Source XK is Caroline Islands; geographic
  Kosovo XK maps to source XO. Never assume these codes are ISO or approved HKP.
- CountryClassifier.classify(AddressRecord) -> CountryInference(record_no,
  country_code, status, reason, evidence, candidates). Status is DETERMINED,
  INFERRED or UNRESOLVED; only UNRESOLVED has no country code. Country evidence
  is independent of the strict ClassificationResult and signed HKP catalogue.
- analyze_job/resume_analysis provide streaming, cancel/resume and reconciled
  per-row/summary/diagnostic output. Input, pack, mapping and rules are pinned.
- CountryAnalysisWindow is the default GUI; existing MainWindow remains the
  strict compatibility interface. CLI gains analyze without HKP approvals.

## Milestones

1. Source mapping: TDD import, full wrapped names/provenance, crosswalks, packaged
   resource. No recipient data or private source rows in repository fixtures.
2. Estimator: explicit names/abbreviations, contextual Hong Kong localities,
   mainland administrative regions, useful first lines and single-city leaders.
   Comparable rival countries and absent geographic evidence stay unresolved.
3. Jobs/UI: preserve original fields/IDs/order/duplicates; append Country_Code;
   Country_Summary, Country_Diagnostics, manifest last. No postal service fields.
4. Integrate, independent review, complete regression, real-data aggregate
   validation, Windows frozen build and new developer release if gates pass.

## Acceptance

The supplied input contains 9,604 valid logical rows. Old-engine diagnostic
using Extended k2 and a 36-country synthetic postal master: 5,809 MATCHED,
3,260 UNKNOWN, 535 REVIEW; 63.28 seconds. This is not the unavailable original
run configuration or an accuracy label. Important failure reasons: 1,706
single-place rejection and 1,554 no-geography matches.

Target <=192 unresolved rows (2%) without forced guesses. Country counts plus
unresolved must equal all input rows. Report aggregate before/after results,
measured time/RSS and independently reviewed public-safe edge cases. Missing
ground-truth labels prevent a measured real-data accuracy claim; inspect new
inferences locally and do not present coverage as accuracy.

Original private CSV, row-level outputs and checkpoint details stay local and
gitignored. Diagnostics exposed in chat/commits are counts/reasons only.
