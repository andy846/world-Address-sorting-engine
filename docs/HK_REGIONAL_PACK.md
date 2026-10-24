# Optional Hong Kong address evidence

The Hong Kong regional pack is separate from the application and the global
GeoNames pack. It helps resolve previously unresolved country-code estimates;
it does not certify that an address is deliverable. Existing assigned country
codes, explicit conflicts and returned-mail markers are preserved.

## Use an already verified pack offline

Extract the data-pack ZIP to a new folder. Keep `pack.db`, `manifest.json`,
`audit.json` and `ATTRIBUTION.txt` together. Never replace files inside a pack
that an analysis is using.

From a source checkout, verify and install it with:

```powershell
python tools/install_hk_regional_pack.py --source-dir extracted-hk-pack --active-root packs
```

The installer verifies checksums, SQLite integrity, counts and indexes and
creates a new versioned directory. Reinstalling the same version is refused.
No network access is needed.

In the GUI, enable the optional Hong Kong regional pack and choose its
`pack.db`. The GeoNames selector still requires the global pack. The regional
option is disabled by default, even if an installed pack is discovered.

The command-line equivalent is:

```powershell
world-address-engine analyze --input addresses.csv --output countries --geo-db packs/geonames-extended-global-2026-10-22-k2/pack.db --hk-regional-db packs/hk-bilingual-als-VERSION/pack.db
```

Run `world-address-engine analyze --help` for the supported input mapping
options. Completed reports record the actual regional version and both file
hashes. Resume uses the original selection; replacing or removing either
regional file prevents resume. Finish old v0.1.0 checkpoints with v0.1.0.

## Evidence and limits

Official English and Traditional Chinese components share one address ID.
Simplified Chinese aliases are derived with pinned OpenCC, with provenance
retained. Translations are alternative spellings, not extra votes.

A match requires a building/estate plus street, or a street plus house number
plus district, on the same official address record. Supplied contradictory
house numbers reject the match. Recipient and company lines cannot supply
the missing address evidence. Candidate queries are bounded and indexed.

Only `NO_GEOGRAPHIC_MATCH` and `MULTIPLE_PLAUSIBLE_COUNTRIES` can be upgraded.
A successful fallback is `INFERRED`, country code `HK`, reason
`HK_REGIONAL_ADDRESS_MATCH`; it is still an estimate. CSV columns are unchanged.

## Rebuild from saved official sources

Build dependencies are optional and are not required by the GUI or EXE:

```powershell
python -m pip install -e ".[data-build]"
python tools/build_hk_als_pack.py ALS-GeoJSON.zip als-geojson.schema.json new-output --source-date 2026-10-23 --pack-version 2026-10-23-r1
```

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
