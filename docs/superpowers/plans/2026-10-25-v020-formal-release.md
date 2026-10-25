# Operator-accepted v0.2.0 formal deployment

On 25 October 2026 the user confirmed manual testing passed and requested this
as the sole formal deployed version, uploaded to GitHub. This supersedes the
earlier keep-Draft/no-main/current-v0.1.0 deployment constraints for integration
of this accepted version; published history remains immutable.

Freeze business behavior at a99d94e / country rules7. Prepare v0.2.0 identity,
documentation and CI identity only. Integrate existing PR #3 into its existing
base, then PR #2 into main, using exact expected head SHAs and normal merge
checks; do not bypass branch protections. Verify the merged tree against the
tested release-preparation tree before tagging. Preserve branch/history and
all older release assets. New v0.2.0 is non-prerelease and explicitly Latest.

- [x] Release identity RED (rc1 versus formal), GREEN scoped metadata/packaging.
- [x] Independent release-scope review, business-source equivalence, full suite.
- [x] Fresh formal EXE/wheel, actual offline self-test and installed-wheel check.
- [x] Integrate existing PRs and validate exact main release tree/CI.
- [x] Immutable v0.2.0 tag and verified public-only assets; sole Latest entry.
- [x] Canonical local EXE/receipt, final public/local hashes and handoff.

Canonical local deployment: D:\WASE\WorldAddressEngine.exe. Older out folders
are history, not additional active deployments. The optional HK data pack remains
an explicit partial-source TEST snapshot; the accepted app release does not
relabel data coverage or assert global/strict-postal production certification.
Private input, row output, checkpoint and benchmark oracle files stay ignored.

Release identity TDD: one metadata test failed as expected, then the changed
version + existing packaging guards passed (112 passed, 1 optional actual-build
test skipped in 30.24s). The actual formal build must also pass separately.

Completed: independent review found no important issues; accepted business
source unchanged except version string. Formal local full suite: 1,738 passed,
1 skipped, 2 existing xfails / 328.55s. Actual formal EXE self-test passed,
fresh isolated local wheel core installation passed, full-dependency wheel
installation passed in Linux CI. All preparation CI jobs passed.

PR #3 merged at 42c113d; PR #2 merged into main at 846cfaf. Complete merged
tree equals tested preparation ee11701. Main CI 40165445500 and Windows
40165445535 passed before tagging/publication. Annotated tag v0.2.0 points
to 846cfaf2dbc9135a3cfecbaff6afe76036df74fa.

Published release ID 423167195 is non-draft/non-prerelease and Latest.
All four remote artifact hashes/sizes match; all v0.1.0 original artifacts
remain unchanged. Canonical local EXE/receipt deployed and verified. Further
changes are documentation-only receipts; accepted business behavior is frozen.
Detailed durable receipt: docs/releases/v0.2.0-validation.md.
