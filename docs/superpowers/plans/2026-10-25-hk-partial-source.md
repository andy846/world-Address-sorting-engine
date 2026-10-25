# Approved partial-source continuation — 25 October 2026

The user explicitly approved quarantining all invalid official ALS features and
building a **partial-coverage test pack** from schema-valid features. This
supersedes the all-record source gate only for an explicit quarantine build;
the default remains strict. Retain original ZIP/schema and prior failed audits.

- [x] TDD explicit quarantine builder, complete record locators and hashes.
- [x] Verify/install/pin source coverage and quarantine receipt; display partial coverage.
- [x] Build real source snapshot; reconcile 183,964 read / 174,456 valid / 9,508 excluded before deduplication.
- [x] Independent reviews, full regression, public four-language controls and private replay (two preserved baseline label errors explicitly recorded).
- [x] Real regional-enabled million-row and fresh-process recovery; report limitations.
- [ ] Candidate bundle/CI, independent attributed data-pack publication, update draft PR #3.

Manifest extension `source_validation` contains policy (`strict` or
`quarantine-invalid`), coverage (`complete` or `partial`), feature_count,
valid_feature_count, quarantined_feature_count, quarantine_file and
quarantine_sha256. Complete refers to validation of this source snapshot,
never exhaustive geographical coverage. A quarantine build emits
`quarantine.jsonl`, with one source_member/source_index/reason locator per
invalid feature; no inferred repair or invalid feature enters SQLite.

The source archive hash plus member and one-based index resolve every excluded
record. The receipt is installed and hash-checked with the pack; run metadata
and resume pin the full coverage identity. Structural JSON/schema/envelope,
ZIP CRC, source mutation and zero-valid-address failures still block publishing.
The official schema is unchanged. Preserve v0.1.0 Latest and main; candidate
application and data are pre-release scope only.

Builder TDD: seven new quarantine cases initially failed; explicit opt-in and
source identity implemented. Builder/quarantine regression: 55 passed in
10.85s with warnings treated as errors. Real build started against the exact
preserved source/schema hashes; no source edits or schema relaxation applied.

Actual build completed: 183,964 read, 174,456 valid, 9,508 quarantined, 1,241
projected duplicates, 173,215 addresses / 150,092 buildings / 1,258,249 aliases.
SQLite 747,376,640 bytes; SHA256
bd5edd2eaacbfe9459df27d7c338899c29bdaa828c76bb13573799077a926ac8.
Receipt 1,238,402 bytes; SHA256
89a5ed2e9b21587b1048c3008584f61044dadeb5aa98ad017a680bef1c35858c.
Audit elapsed 488.498s. Installed offline with full SQLite/FK/hash/receipt checks.

Private replay with the new data retained 7,143 determined / 2,419 inferred /
42 unresolved. All previously assigned private codes remain protected.

First deterministic public QA bank froze 12 source entities and 336 positive,
foreign and component-negative cases before predictions. It exposed 17 direct
positive misses: common anchor overflow and official building names containing
company words. Full-name same-address retrieval (64-candidate cap retained) and
exact official typed-building restoration are being verified with TDD. Two
existing baseline HK positives were already misassigned MY/TD by the global
leader rule; the unresolved-only policy intentionally does not override them.
All-label sample accuracy remains a separate reported metric; do not hide those
baseline errors or claim the sample is wholly correct.

Country rules advanced to 2026-10-25.country.6 for these matching changes;
old checkpoints/oracles must not be relabelled. Fresh paired benchmarks will
use fresh rules6 baselines. Strict-postal rules and v0.1.0 stay unchanged.

Profiling found repeated real-pack verification costs (under concurrent QA):
13.767s without full integrity, 51.991s with full integrity. A four-entry,
actual-content-hash cache is being reviewed; every call still hashes source
bytes, validates receipt/metadata and checks final identity. A coordinated
source-swap probe found an ABA cache-poisoning gap; a protected SQL snapshot
must bind validation to the actual cached bytes before acceptance.

Commit fc19ef6 binds SQL verification to a private temporary copy whose SHA256
is checked before and after SQL, then rechecks the live files before caching a
boolean receipt. Cache hits still validate actual DB/manifest/quarantine bytes.
The independent review's original ABA probe now rejects the swapped source and
leaves no receipt. Cache/public-validator tests: 73 passed in 13.36s. After an
initial usage interruption, the independent reviewer completed its bounded
fc19ef6 review: no remaining Important/Critical cache or company-alias findings.
The implementer also reran the original probe and the full regression suite.

Final public bank r3 uses the unchanged deterministic source selection and
rules6: 336 cases, 48/48 direct positives, 144/144 foreign controls and 144/144
component/number negative controls passed. Of 48 HK positives, country analysis
returns HK for 46 and preserves the two existing MY/TD global-leader errors.
There are 43 regional upgrades and zero changes to 161 previously assigned
results. All-label QA remains FAILED (two errors); no production-readiness or
new formal application-release claim is justified. These are narrowly selected
source-derived smoke controls, not an independent random accuracy estimate.
Case-bank SHA256: 88b4c839171f07e25a51bd895ee66fd515efb05b90488e24244ba1ec3ee1339b.

Fresh rules6 private replays, with the regional option disabled and enabled,
both retain 7,143 determined / 2,419 inferred / 42 unresolved. All three CSVs
are byte-identical to the reviewed baseline; this source pack does not resolve
the remaining 42 cases in this private input. No private rows are published.

The public-only ZIP was reopened and every member streamed through SHA256/CRC
verification against the installed files. ZIP: 228,726,810 bytes; SHA256
3ca4bf9a4302b1a893890a014dfed39697a14106aba6e9f49bd0952f50bc29bd.
The pack remains a partial-source TEST data prerelease candidate; v0.1.0 Latest
and main remain unchanged.

Final local full suite: 1,701 passed, 1 skipped, 2 pre-existing xfails in
260.57s. All exact-runtime remote CI jobs passed: release validation 40157329609
(Linux 1,476 passed / 89 skipped / 2 xfailed; Windows 1,393 passed / 311 skipped;
fresh installed wheel and actual EXE smoke passed) and Windows regression
40157329613 (1,394 passed / 310 skipped, including actual packaging).

Fresh rules6 million measurements: disabled 149.293s, 6,698.25 rows/s,
75,087,872-byte peak RSS; enabled 183.661s, 5,444.82 rows/s, 78,045,184-byte
peak RSS. Enabled cancel at exactly 500,000 committed rows: 78.342s. Different
process resumed all 1,000,000 rows in 197.167s, peak RSS 77,598,720 bytes.
All three runs passed exhaustive streaming verification; all three CSVs match
enabled/disabled/recovery, enabled recovery manifests match exactly and every
39,600 public labelled control rows per run is correct. Completed checkpoints
are removed. Workload has only 9,606 distinct keys, not a million distinct HK
addresses. Runtime fingerprint 30018e8b22cc9a127e16a345086ee3399ac4f5322abec7361e8bea8cda9446fe.

Independent publication-scope review found only an unfinished performance/
recovery reference, now supplied by the final dated validation report. No
remaining important privacy/source-scope finding. Application all-label QA
still fails on two protected baseline errors; only a separate TEST data
prerelease is eligible, not formal application promotion.
