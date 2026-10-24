# Approved partial-source continuation — 25 October 2026

The user explicitly approved quarantining all invalid official ALS features and
building a **partial-coverage test pack** from schema-valid features. This
supersedes the all-record source gate only for an explicit quarantine build;
the default remains strict. Retain original ZIP/schema and prior failed audits.

- [ ] TDD explicit quarantine builder, complete record locators and hashes.
- [ ] Verify/install/pin source coverage and quarantine receipt; display partial coverage.
- [ ] Build real source snapshot; reconcile 183,964 read / 174,456 valid / 9,508 excluded before deduplication.
- [ ] Independent reviews, full regression, public four-language controls and private replay.
- [ ] Real regional-enabled million-row and fresh-process recovery; report limitations.
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
