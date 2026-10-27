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

- [ ] Identity RED/GREEN; independent source-equivalence review.
- [ ] Full formal-version regression, EXE/offline smoke and installed wheel.
- [ ] Preparation CI, PR #4 merge and main tree/CI validation.
- [ ] New tag and draft assets verified before final publication as Latest.
- [ ] Canonical local deployment and exact remote/local hashes verified.

Public assets: EXE, wheel, Release_Manifest.json and SHA256SUMS.txt only.
Manual acceptance applies to application behavior, not exhaustive HK coverage,
global accuracy or strict-postal approval. HK pack remains partial-source TEST.
