# Official postal code data sources (Phase 1)

**Important:** A full production-approved Hongkong Post destination catalogue has not been assembled. The code in `hkp/catalogue.py` validates a CSV and its manifest but DOES NOT independently verify that a source document contains a particular destination mapping. Examples in unit tests are isolated fixtures, not an authoritative current service list. Do not use fixture catalogues for mailing production.

1. EC-Ship Bulk Mail API specification v1.23 — service-specific two-character destination code appendices: https://ec-ship.hongkongpost.hk/API-portal/Bulk_API_Specification.pdf
2. HK Post Destination & Zone Chart (historical, verify current status before use): https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf
3. HK Post PostageRate Open Data schema, including `destinationCode`: https://www.hongkongpost.hk/opendata/DataDictionary/en/DataDictionary_PostageRate.pdf
4. EC-Ship individual mail API (3-character scheme; NOT interchangeable with the bulk two-character codes): https://ec-ship.hongkongpost.hk/API-portal/EC-Ship_API_Specification_Restful.pdf

Operator/source-audit workflow required before any approved release: download official documents, preserve hashes and versions, verify each entry against the actual document, reconcile retired/conflicting codes, review service-specific membership separately, and build a versioned complete HKP_DESTINATION_2 master.
