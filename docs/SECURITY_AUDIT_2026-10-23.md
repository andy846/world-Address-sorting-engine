# Independent security and accuracy audit — 2026-10-23

An independent reviewer audited the classification, catalogue, checkpoint, IO
and reporting paths at commit `4fff20c` using read-only source review plus 24
executable probe scenarios. No repository file was modified by the reviewer.

The prototype is **not production ready**. Three findings are P0: a path
exists that asserts a postal code for a destination that was never reviewed,
and two paths emit a confident `MATCHED` for the wrong country.

## Findings

| # | Sev | Area | One-line defect | Status |
|---|---|---|---|---|
| 1 | P0 | Production gate | `_hkp_audited()` reads `production_approved` from the very catalogue file it is vetting, so a hand-made SQLite passes the gate | Fixed — `ed05659` |
| 2 | P0 | Conflict handling | A country hint plus weak geography emits the *wrong* country as confident `MATCHED` | Fixed — 525e0e2 |
| 3 | P0 | Explicit evidence | A company name on any line but the first is accepted as explicit country evidence | Fixed — 525e0e2 |
| 4 | P1 | Checkpoint | A tampered shard, renamed with a recomputed digest, publishes an arbitrary code under a `COMPLETE` manifest | Fixed — `81c6e3b` |
| 5 | P1 | Scoring | The `MATCHED` threshold is exactly "two place rows", so a lone city token can be asserted | Fixed — 525e0e2 |
| 6 | P1 | Catalogue | The two-letter code format is validated at import only, never at query time, so a 3-letter code can be emitted under the 2-character scheme | Fixed — 525e0e2 |
| 7 | P1 | Catalogue | The ISO crosswalk is not injective, and a missing approved HKP row raises `KeyError` instead of `REVIEW_CODE_MAPPING` | Fixed — 525e0e2 |
| 8 | P1 | Provenance | "Official source" validation is a URL-host string check, and `approval_status` ships inside the data file it is supposed to police | Fixed — `ed05659` |
| 9 | P1 | Labelling | A `--test-only` export is byte-for-byte indistinguishable from a production export | Fixed — `81c6e3b` |
| 10 | P2 | Privacy | `.gitignore` does not cover the default export filenames, so customer addresses can be committed | Fixed — `81c6e3b` |
| 11 | P2 | Export | `Country_Summary.csv` bypasses the spreadsheet formula sanitizer | Fixed — `81c6e3b` |
| 12 | P2 | Export | The detailed export omits most fields the spec requires | Fixed — `81c6e3b` |
| A1 | P2 | Builder | `UNIQUE (place_id, search_key)` plus insert order discards the authoritative language tag, so alias language provenance is lossy | Fixed — 63d2c32 |

## Detail

### 1. P0 — the production-approval gate is self-asserted inside the untrusted file

`src/world_address_engine/jobs/runner.py:19-26`

`_hkp_audited()` reads `production_approved` from the `metadata` table of the
same `--hkp-db` file it is meant to vet. There is no signature, no separate
manifest and no hash binding.

Probe: a hand-made SQLite with `metadata(catalogue_version, csv_sha256,
production_approved=1)` and `destinations` rows marked `APPROVED` with
`code='ZZ'` produced `status=MATCHED code='ZZ'` and a manifest reporting
`production_approved = True`, `data_approval = INDEPENDENTLY_AUDITED`, with
`allow_unverified_reference_data=False`.

This also means the gate currently protects nothing: the sanctioned importer
(`src/world_address_engine/hkp/catalogue.py:70-71`) creates a `metadata` table
without a `production_approved` column, so no legitimately imported catalogue
can pass it. The forged path is the only path in.

**Required fix.** Move approval out of the data file into a release-controlled
signed manifest bound to `catalogue_version` + `csv_sha256` + row count, with
the key held outside the repository. The importer must record a *verified*
approval derived from that manifest and fail closed when it is absent.

### 2. P0 — a country column plus weak geography emits the wrong country

`src/world_address_engine/matching/classify.py:46-52,60,63` and
src/world_address_engine/matching/retrieve.py:58`

A competing country is only treated as contradictory at `score >= .87`, but
`0.35 + 0.26 * len(ids[code])` gives exactly `0.87` for two places and `0.61`
for one. A single place-name hit in the other country therefore never
contradicts the supplied country.

Probe: address `Tokyo` with `Country="US"` produced
`MATCHED, code='US', conf=0.98, reason=EXPLICIT_DESTINATION`. The same text
without a hint correctly produced `UNKNOWN / SINGLE_PLACE_IS_NOT_ENOUGH`.

### 3. P0 — a company name is accepted as explicit country evidence

`src/world_address_engine/matching/classify.py:38-45`

The classifier assumes line 1 is the recipient name and drops it; every later
line is searched for destination names. Latin needles are word-bounded, so
`INDIA` does not match `INDIANA`, but `CHINA` does match `CHINA
CONSTRUCTION`. Han needles degrade to a plain substring test with no boundary
at all.

Probe: `Jane Doe / CHINA CONSTRUCTION LTD / 1 Main St, Springfield, US`
produced `MATCHED code='CN'`. `北京市 / 中国银行` produced `MATCHED code='CN'`.

### 4. P1 — a tampered checkpoint shard publishes an arbitrary code

`src/world_address_engine/jobs/checkpoint.py:78-85,96-97`

The shard digest lives **in the filename**, so it is self-referential: an
editor recomputes SHA-256, renames the file, and `committed_shards()` accepts
it. Row boundaries are checked, but the payload — including `status` and
`hkp_code` — is trusted verbatim and written straight into the export.

Probe: a paused job's shard was rewritten to `status=MATCHED, hkp_code='ZZ'`
and renamed with the recomputed digest. `resume_job` published
`status=MATCHED code='ZZ'` under a `COMPLETE` manifest. Editing without
renaming is correctly rejected with `checkpoint checksum mismatch`.

### 5. P1 — the MATCHED threshold is exactly "two place rows"

`src/world_address_engine/matching/retrieve.py:20-24,50-52,58`

`ids[code]` counts distinct `place_id`s matched by *any* 1-4-token n-gram of
the whole address. Two same-named places in one country give `0.87`, so a
lone city token reaches `MATCHED`. Unrelated common tokens such as `main`,
`road` and `street` each contribute their own `place_id`s.

This is confirmed against the **real** packs: in `EXTENDED_GLOBAL` the single
token `springfield` matches 68 place ids in `US`, 15 in `GB`, 12 in `JM`, 9 in
`AU`, 7 in `CA`, 5 in `ZA` and 4 in `IE`. Under the current formula every one
of those countries scores `0.99`, so the score model saturates on real data
and can no longer discriminate. `berlin` similarly saturates across 17
countries and `paris` across 20.

### 6. P1 — the two-letter format is validated only at import time

`src/world_address_engine/hkp/catalogue.py:108-118`

`_validate_row()` enforces `[A-Z]{2}` for the HKP scheme at import, but
`lookup_hkp_code()` and `_postal_catalogue()` filter only on
`code_scheme` / `profile` / `approval_status`. A forged or later-mutated row
`('france','HKP_DESTINATION_2','FRA',...)` returned `'FRA'` — a 3-letter
EC-Ship-style code emitted under the 2-character scheme.

### 7. P1 — the ISO crosswalk is not injective

`src/world_address_engine/matching/classify.py:18-20,51-52,63`

`dict(...)` silently collapses duplicate ISO codes, and the importer does not
prevent two ISO rows sharing a code. A master with both `('MO','macau')` and
`('MO','china')` imports cleanly. Separately, an ISO row whose destination has
no approved `HKP_DESTINATION_2` row makes `codes[did]` raise `KeyError`,
where the spec requires `REVIEW_CODE_MAPPING`.

### 8. P1 — "official source" validation is a URL-host string check

`src/world_address_engine/hkp/catalogue.py:45-48`

An `APPROVED` row only needs a `source_url` whose host is `hongkongpost.hk` —
a string the CSV author typed — and `approval_status` is a column of the same
CSV as the data.

### 9. P1 — a test-only export is indistinguishable from a production export

`src/world_address_engine/jobs/runner.py:106-113` and
`src/world_address_engine/io/reports.py:76-86`

The `TEST_ONLY_UNVERIFIED` label lives only inside `Run_Manifest.json`. The
CSV exports carry no banner, column or filename marker.

### 10. P2 — export filenames are not ignored

`.gitignore` covers `.job-state/`, but not `Classified_Addresses.csv`,
`Manual_Review.csv`, `Country_Summary.csv`, `Run_Manifest.json` or
`Classified_Addresses.machine.csv`. The final export holds the same
plaintext recipient data as the ignored checkpoint folder.

### 11. P2 — `Country_Summary.csv` bypasses the formula sanitizer

`src/world_address_engine/io/reports.py:91-94`

### 12. P2 — the detailed export omits required fields

`src/world_address_engine/io/reports.py:18-22`

`RESULT_FIELDS` has 9 columns; the spec also requires
`Destination_Name_EN`, `Destination_Name_TC`, `Match_Method`,
`Match_Evidence`, `Review_Reason`, `HKP_Catalogue_Version`,
`Geo_Pack_Versions` and `Rules_Version`.

### A1. P2 — alias language provenance is lossy

`src/world_address_engine/data/geonames_builder.py:88-120`

See `docs/benchmarks.md` for the measured effect.

## Confirmed safe

- **No ISO substitution; `TP` never becomes `TL`.** `classify.py:15-17` reads
  only `code_scheme='HKP_DESTINATION_2' AND profile='HKP_DESTINATION_2' AND
  approval_status='APPROVED'`, and `catalogue.py:110-111` returns `None` for
  any other profile. `FR`/`FRA` and `HK`/`HKG` separation holds structurally.
- **A non-`MATCHED` result can never carry a code.**
  `src/world_address_engine/models.py:53-56` raises `ValueError` for that
  combination and requires `MATCHED` to carry both a code and a destination.
- **No parent-state collapsing logic exists anywhere in the source.**
- **Row-count conservation, ordering and duplicates.** Identical addresses
  remain separate mail pieces; an invalid byte becomes one `INPUT_ERROR` row,
  not a dropped row.
- **Malformed framing fails the job; no partial publish.** The manifest is
  written last and refuses to overwrite an existing manifest.
- **Embedded newlines stay one logical record** (`csv.reader(..., strict=True)`).
- **Resume re-verifies the input, the geo pack and the catalogue**, and
  aborts before `write_reports` if any changed mid-run.
- **Formula injection is neutralized** in the Excel-facing view and the manual
  review file (finding 11 is the one exception).
- **No address text is logged by default.** The preview command returns
  counts only; error messages carry column names and row numbers, not values.
- **Unsupported scripts are rejected before matching** with
  `UNKNOWN / UNSUPPORTED_LANGUAGE`.

## Audit gaps

- The real HKP master does not exist yet, so every master-dependent property
  is unverified against an official snapshot.
- The `tests/unit/test_classify.py` master is a 9-row synthetic stand-in.
- Non-UTF-8 encodings (Big5) and the explicit `--encoding` paths are untested.
- `machine_export=True` is reachable through the library API only; the CLI
  never enables it today.
- XLSX `Source_Record_No` is a logical sequence after blank rows are skipped,
  not the physical spreadsheet row.


## Remediation — Milestone 2 (commits `525e0e2`, `63d2c32`)

The findings marked *Fixed* above were closed by replacing the place-count
score with a weighted evidence mass. Each search term contributes at most one
weight per destination, however many gazetteer rows it matches, so the model
no longer saturates on a global pack:

| Evidence | Weight |
|---|---:|
| country entity (`PCLI`/`PCLX`/`PCLS`/`PCLD`, or `admin1_code = '00'`) | 0.60 |
| `ADM1` | 0.26 |
| `ADM2` | 0.16 |
| deeper administration | 0.08 |
| populated place | 0.26 x min(1, log10(population+1)/6) |
| place with no population | 0 (no evidence) |

A destination is assertable only when `support >= 0.15` **and** it either
carries at least two independent search terms or is a country entity.

### Probe results before and after

| Audit probe | Before | After |
|---|---|---|
| `Tokyo` with `Country="US"` | `MATCHED US`, confidence 0.98 | `REVIEW_CONFLICT`, no code |
| `Jane Doe / CHINA CONSTRUCTION LTD / 1 Main St, Springfield, US` | `MATCHED CN` | `REVIEW_AMBIGUOUS`, no code |
| `北京市 / 中国银行` | `MATCHED CN` | `UNKNOWN`, no code |
| a lone city token | `MATCHED` at 0.87 (two rows) | `UNKNOWN` / `REVIEW_AMBIGUOUS` |
| a forged `code='FRA'` row under `HKP_DESTINATION_2` | `FRA` emitted | `REVIEW_CODE_MAPPING`, no code |
| an ISO code claimed by two destinations | silently collapsed | `REVIEW_CODE_MAPPING`, no code |
| an ISO row whose destination has no HKP row | `KeyError` | `REVIEW_CODE_MAPPING`, no code |

### Deliberate behaviour changes

- **A lone city token is no longer asserted.** `Tokyo` alone is `UNKNOWN`,
  and `Frankfurt` alone is `UNKNOWN`; the evidence is real but a single
  token cannot carry a country. A structured country field supplied by the
  operator still resolves these: `Frankfurt` with `Country="DE"` is
  `MATCHED DE`.
- **Generic address words are not evidence.** `main`, `street`, `road`,
  `suite` and similar words are place names in the gazetteer, and counting
  them was one reason the old score saturated. They are now dropped unless
  they are part of a longer place name (`Hyde Park` still resolves).
- **The first line of a multi-line address is the recipient.** It is
  excluded from geographic evidence as well as from catalogue matching.
- **The published 2026-10-22 packs are unaffected in content.** The
  builder fix changes only the `language` label of an alias row, so the
  indexed place/alias pairs and therefore matching are identical; the bytes
  differ, so packs built after `63d2c32` must be published as a new pack
  version.

## Remediation — Milestone 3 (commits `ed05659`, `81c6e3b`, `8faff89`, `0957f1d`)

### The findings that are now closed

| # | Sev | How it is closed now |
|---|---|---|
| 1 | P0 | The catalogue file can no longer approve itself. A production run needs a **signed approval manifest** whose key is held outside the repository, and the manifest binds the catalogue version, the source CSV digest, the row count, the built database digest and the official documents that were vetted. The signature, the digests and the approved destinations are all checked; anything missing fails closed (`hkp/approval.py`). |
| 4 | P1 | A checkpoint shard is local, writable data, so its own digest in its filename proves nothing. Every committed record is re-derived and compared with the shard before the export is published (`jobs/runner.py --verify-shards`), and every exported code is re-checked against the approved catalogue. |
| 8 | P1 | `approval_status` inside the data file no longer grants anything. A code is resolvable only when the signed approval names the destination *and* ratifies the exact source document the row was taken from. A `TEST_FIXTURE` signed manifest can never authorise production, whatever it claims. |
| 9 | P1 | Every export carries a `Data_Class` column and a `DATA_CLASS.txt` marker, and the run manifest records the same class. A test export is `TEST_ONLY_UNVERIFIED` everywhere and can no longer be mistaken for a production mailing list. |
| 10 | P2 | The default export file names and the checkpoint state directory are ignored by git, and the checkpoint shards are deleted once the exports are published (`--keep-checkpoint` keeps them on request). |
| 11 | P2 | `Country_Summary.csv` is written through the same formula sanitizer as the detailed export. |
| 12 | P2 | The detailed export now carries the destination identity, the catalogue version, the pack versions, the rules version and the data class next to the original columns. |

### Review findings of the geographic milestone

| # | Sev | How it is closed now |
|---|---|---|
| P0-1 | P0 | `Wake, United States Minor Outlying Islands` was matched to the United States. The country name is now parsed as a complete entity, so the territory resolves to `UM` and ends in a review instead of a wrong country (`8faff89`). |
| P0-2 | P0 | A postcode was read as a company word. `Dublin, Ireland D02` is now matched to Ireland, and an alphanumeric postcode is no longer treated as a company suffix (`8faff89`). |
| P0-3 | P0 | The search key of the pack and the reader could drift apart. Both now use one shared `normalize_search_key`, so a producer and its consumer cannot disagree (`8d49d57`). |

### New findings from the 2026-10-23 evening audit

| # | Sev | Area | Defect | Status |
|---|---|---|---|---|
| 13 | P1 | Quality control | The review panel took its authority from the operator's text boxes instead of from the run | Fixed — `55eaef1` |
| 14 | P1 | Quality control | A manual correction was written into the export before it was known to be allowed | Fixed — `f1f0aed` |
| 15 | P1 | Threading | A running worker thread was destroyed with the window, aborting the interpreter | Fixed — `55eaef1` |
| 16 | P2 | Cancellation | A cancel was ignored for any job smaller than one batch, so the run published anyway | Fixed — `957a1e0` |
| 17 | P2 | Privacy | The plaintext customer checkpoint stayed in the output folder after a successful run | Fixed — `957a1e0` |
| 18 | P2 | Build tool | The pack build crashed after the database was written, because the alias language counts were removed from the metrics before the manifest was built from them | Fixed — `13c8e24` |
| 19 | P2 | Retrieval | A Han place name with an administrative suffix (`臺北市`) was unreachable when the address left the suffix out (`臺北`) | Fixed — `54b5f26` |
| 20 | P2 | Transparency | A review that could not map its country did not name the country | Fixed — `f27dcd9` |

### Confirmed safe after the remediation

- The production gate cannot be satisfied by a file the operator supplies.
  A catalogue built from a hand-made CSV fails without a signed approval,
  and a `TEST_FIXTURE` approval never authorises production.
- A manual correction may only assert a code the approval in force issues,
  and the correction is rejected before the published export is touched.
- The review panel is bound to the run that produced the export.
- A cancelled run never publishes a manifest, and the plaintext checkpoint is
  removed once the exports exist.
