# Official postal code data sources (Phase 1)

**Important:** A full production-approved Hongkong Post destination catalogue has not been assembled. The code in `hkp/catalogue.py` validates a CSV and its manifest but DOES NOT independently verify that a source document contains a particular destination mapping. Examples in unit tests are isolated fixtures, not an authoritative current service list. Do not use fixture catalogues for mailing production.

1. EC-Ship Bulk Mail API specification v1.23 — service-specific two-character destination code appendices: https://ec-ship.hongkongpost.hk/API-portal/Bulk_API_Specification.pdf
2. HK Post Destination & Zone Chart (historical, verify current status before use): https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf
3. HK Post PostageRate Open Data schema, including `destinationCode`: https://www.hongkongpost.hk/opendata/DataDictionary/en/DataDictionary_PostageRate.pdf
4. EC-Ship individual mail API (3-character scheme; NOT interchangeable with the bulk two-character codes): https://ec-ship.hongkongpost.hk/API-portal/EC-Ship_API_Specification_Restful.pdf

Operator/source-audit workflow required before any approved release: download official documents, preserve hashes and versions, verify each entry against the actual document, reconcile retired/conflicting codes, review service-specific membership separately, and build a versioned complete HKP_DESTINATION_2 master.

## How an approval is granted (the approval-manifest design)

The catalogue file is **data**, never authority. A row marked `APPROVED`
inside `hkp_test_master.db` grants nothing on its own.

Production authority lives in a separate **approval manifest** that the
release process signs with a key held **outside** the repository:

| Field | What it binds |
|---|---|
| `approval_id` | the name of this approval |
| `scope` | `PRODUCTION` or `TEST_FIXTURE`; only `PRODUCTION` may authorise a mailing run |
| `catalogue_version` | the catalogue build the approval is about |
| `csv_sha256` | the exact source CSV the catalogue was imported from |
| `row_count` | the number of rows the catalogue must hold |
| `catalogue_db_sha256` | the exact built database the approval is about |
| `approved_destinations` | the destinations that may be asserted at all |
| `approved_sources` | the official documents, with version and SHA-256, that the rows were taken from |
| `signature` | HMAC-SHA256 over the rest of the manifest |

`load_approval()` verifies the signature, the database digest, the
catalogue version, the source CSV digest, the row count and the presence of
every approved destination. A missing or mismatching field fails closed.
The key path is never written into a published artefact.

A code is resolvable only when the approval names the destination **and**
ratifies the exact source document, version and checksum of the row. A
`TEST_FIXTURE` signed manifest can never authorise production, whatever it
claims about itself.

## Open blocker — the official Hongkong Post master is still unreachable

The official sources listed above could not be retrieved from this
environment. Every route tried returned a CloudFront `403`:

- `https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf`
- `https://ec-ship.hongkongpost.hk/platform/data/supported_countries.html`
- the same document through a real browser session, through a text proxy
  and through a generic CORS proxy

The consequence is deliberate and must stay visible:

- a clearly labelled **synthetic 36-country test fixture** ships with the
  repository so the automated tests can exercise the whole path, and it is
  signed with a `TEST_FIXTURE` scope key, which can never authorise a
  production run;
- **no master may ever be marked `APPROVED` without the genuine document and
  its checksum**, and the production mode fails closed until that approval
  exists;
- the fixture is never presented as the Hongkong Post master, in the data,
  in the documentation or in a release note.

Before an approved release, the release process has to download the official
documents, record their version, URL and SHA-256, verify every row against
the actual document, reconcile retired or conflicting codes, review the
service-specific membership separately, and only then sign a
`PRODUCTION` approval manifest.

## GeoNames reference data

| Archive | Bytes | SHA256 |
|---|---|---|
| `allCountries.zip` | 422,156,786 | `4b8a10021d69736be2f78b75cbd6f49648f50bcd90da117cc1c4f84767725182` |
| `alternateNamesV2.zip` | 204,950,999 | `1ea8afef7da35370529cd2f7c38caac78e821ca3578f18f0207e5c31ee81fb05` |
| `cities1000.zip` | 11,077,563 | `9d3916f7a9448bb4ea45e93c06c5413d2cceb1a89e03f75c2178bbb08af12018` |

License: CC BY 4.0. Attribution: GeoNames (https://www.geonames.org/export/).

The pack builder indexes the **English and Chinese** alternate names only
(`en`, `zh`, `zh-CN`, `zh-TW`, `zh-Hans`, `zh-Hant`) plus the Latin-script
source name. A country endonym in any other language is therefore **not**
evidence: `Deutschland, Berlin` resolves on "Berlin" alone and stays a
review, while `Germany, Berlin` is matched. Extending the indexed language
set is a documented follow-up, not an accident.
