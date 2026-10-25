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
- [ ] Independent release-scope review, business-source equivalence, full suite.
- [ ] Fresh formal EXE/wheel, actual offline self-test and installed-wheel check.
- [ ] Integrate existing PRs and validate exact main release tree/CI.
- [ ] Immutable v0.2.0 tag and verified public-only assets; sole Latest entry.
- [ ] Canonical local EXE/receipt, final public/local hashes and handoff.

Canonical local deployment: D:\WASE\WorldAddressEngine.exe. Older out folders
are history, not additional active deployments. The optional HK data pack remains
an explicit partial-source TEST snapshot; the accepted app release does not
relabel data coverage or assert global/strict-postal production certification.
Private input, row output, checkpoint and benchmark oracle files stay ignored.

Release identity TDD: one metadata test failed as expected, then the changed
version + existing packaging guards passed (112 passed, 1 optional actual-build
test skipped in 30.24s). The actual formal build must also pass separately.
