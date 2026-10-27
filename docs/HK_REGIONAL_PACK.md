# Optional Hong Kong address evidence

The Hong Kong regional pack is separate from the application and the global
GeoNames pack. It helps resolve previously unresolved country-code estimates;
it does not certify that an address is deliverable. Existing assigned country
codes, explicit conflicts and returned-mail markers are preserved.

## Use an already verified pack offline

Extract the data-pack ZIP to a new folder. Keep `pack.db`, `manifest.json`,
`audit.json` and `ATTRIBUTION.txt` together. Never replace files inside a pack
that an analysis is using.

A partial-source pack also requires `quarantine.jsonl`. Keep it with the other
files: its checksum and complete excluded-record count are verified during
installation and analysis. The GUI identifies partial source coverage and
shows how many official source features were excluded.

From a source checkout, verify and install it with:

```powershell
python tools/install_hk_regional_pack.py --source-dir extracted-hk-pack --active-root packs
```

The installer verifies checksums, SQLite integrity, counts and indexes and
creates a new versioned directory. Reinstalling the same version is refused.
No network access is needed.

In the formal v0.2.0 GUI, enable the optional Hong Kong regional pack and choose
its `pack.db`; the option is disabled by default in that release. The v0.3
candidate discovers installed packs and starts with Hong Kong enabled. Choose
a valid installed pack or explicitly switch the option off if unavailable.
The GeoNames selector still requires a global pack in both versions.

The command-line equivalent is:

```powershell
world-address-engine analyze --input addresses.csv --output countries --geo-db packs/geonames-extended-global-2026-10-22-k2/pack.db --hk-regional-db packs/hk-bilingual-als-VERSION/pack.db
```

Run `world-address-engine analyze --help` for the supported input mapping
options. Completed reports record the actual regional version and both file
hashes. Resume uses the original selection; replacing or removing either
regional file prevents resume. Finish old v0.1.0 checkpoints with v0.1.0.
Country rules6 checkpoints likewise require their matching rules6 build;
the rules7 street-evidence correction applies only to new analyses.

## Evidence and limits

Official English and Traditional Chinese components share one address ID.
Simplified Chinese aliases are derived with pinned OpenCC, with provenance
retained. Translations are alternative spellings, not extra votes.

A match requires a building/estate plus street, or a street plus house number
plus district, on the same official address record. Supplied contradictory
house numbers reject the match. Recipient and company lines cannot supply
the missing address evidence. A complete official building/estate name with a
typed building ending can remain eligible even when it contains company words;
recipient prefixes are still excluded. Candidate queries are bounded and indexed.

Only `NO_GEOGRAPHIC_MATCH` and `MULTIPLE_PLAUSIBLE_COUNTRIES` can be upgraded.
A successful fallback is `INFERRED`, country code `HK`, reason
`HK_REGIONAL_ADDRESS_MATCH`; it is still an estimate. CSV columns are unchanged.

## Rebuild from saved official sources

Build dependencies are optional and are not required by the GUI or EXE:

```powershell
python -m pip install -e ".[data-build]"
python tools/build_hk_als_pack.py ALS-GeoJSON.zip als-geojson.schema.json new-output --source-date 2026-10-23 --pack-version 2026-10-23-r1
```

The default command remains strict and refuses any invalid feature. On
25 October 2026 the operator approved a partial-coverage **test pack** using
only schema-valid features from the preserved snapshot:

```powershell
python tools/build_hk_als_pack.py ALS-GeoJSON.zip als-geojson.schema.json new-partial-output --source-date 2026-10-23 --pack-version 2026-10-23-r1-partial --quarantine-invalid
```

This explicit mode records every excluded feature's member, one-based index
and reason in a hashed receipt. It does not repair invalid features or weaken
the official schema. Broken JSON/envelopes, CRC failures, source mutation and
zero valid records still prevent publication. `complete` in source-validation
metadata refers to this snapshot's accepted features, not geographic coverage.

Sources: [official ALS download](https://www.als.gov.hk/data/ALS-GeoJSON.zip),
[official schema](https://www.als.gov.hk/docs/als-geojson.schema.json).
The raw archive and schema remain outside the installed pack. A failed audit
does not produce a usable database. Inspect aggregate `audit.json` for the
failure counts and schema paths; do not bypass the source-validation gate.

The regional data retains its source attribution and
[DATA.GOV.HK terms](https://data.gov.hk/en/terms-and-conditions), separately
from the software license. This phase contains ALS only; it makes no claim of
exhaustive Hong Kong address coverage. Release approval also requires real-data
audit reconciliation, regression, private replay, performance and recovery
validation. See the dated implementation ledger for actual gate results.
