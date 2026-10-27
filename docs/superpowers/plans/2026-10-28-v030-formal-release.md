# Operator-accepted v0.3.0 formal release

On 28 October 2026 the user confirmed candidate testing completed, requested
merging the final version and publishing a GitHub Release. This supersedes
candidate-only/no-main/no-promotion restrictions for the accepted e42eeca
behavior. Keep historical releases/tags/assets immutable.

Prepare v0.3.0 identity and documentation only; retain country rules7, schema2,
zone mappings, reference bytes and all accepted GUI/business behavior. Merge
existing PR #4 into main with exact expected head and ordinary branch checks.
Verify the complete merged tree equals the tested preparation tree. Publish
new immutable v0.3.0 tag/release as non-prerelease Latest. No force push or
branch-protection bypass. Preserve candidate and historical artifacts.

- [x] Identity RED/GREEN; independent source-equivalence review.
- [x] Full formal-version regression, EXE/offline smoke and installed wheel.
- [x] Preparation CI, PR #4 merge and main tree/CI validation.
- [x] New tag and draft assets verified before final publication as Latest.
- [x] Canonical local deployment and exact remote/local hashes verified.

Public assets: EXE, wheel, Release_Manifest.json and SHA256SUMS.txt only.
Manual acceptance applies to application behavior, not exhaustive HK coverage,
global accuracy or strict-postal approval. HK pack remains partial-source TEST.

Completed: preparation cb427fd, independent source-equivalence review clear;
identity 200 passed / 1 optional build skip, formal full local regression
1,984 passed / 1 skipped / 2 existing xfails in 568.95s. Fresh formal EXE and
isolated installed wheel passed. Main merge 32e69b4 has the exact preparation
Git tree; main CI 40553816527 and Windows40553816402 both passed.

Annotated v0.3.0 targets 32e69b4. Release425805597 is published, non-prerelease
and Latest. All four remote asset hashes/sizes and downloaded bytes match;
all eight historical releases (including names/bodies/asset metadata) and
all historical tags are unchanged. Canonical EXE/CURRENT_RELEASE updated with
verified hashes and backups. Formal deployment receipt:
docs/releases/v0.3.0-validation.md. Subsequent receipt commit is docs only.
