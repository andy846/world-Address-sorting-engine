# ALS source audit — 24 October 2026

Status: **strict source gate failed; no final regional database produced**.
The existing v0.1.0 release is unaffected.

## Preserved official snapshot

| File | Bytes | SHA256 |
|---|---:|---|
| ALS-GeoJSON.zip | 20,777,483 | `4549e4f774224abdef062cb6ffaa7e75f0d8dc02187a64bc6c05434472b6f577` |
| als-geojson.schema.json | 25,127 | `67deb2349be44ad8cce20650065833e12e6895d394998da8b44377135fe634f6` |

Sources: [official download](https://www.als.gov.hk/data/ALS-GeoJSON.zip),
[official schema](https://www.als.gov.hk/docs/als-geojson.schema.json),
[DATA.GOV.HK resource](https://data.gov.hk/en-data/dataset/hk-dpo-als_01-als/resource/92eed8bd-9e6f-4aac-9c9a-5ea6f5dbb4b8).
The resource reports a 23 October 2026 update. The raw files are retained locally
under `builds/hk-als-2026-10-23/source`, outside Git and outside installed packs.

## Complete strict pass

All 19 GeoJSON members were consumed with ZIP CRC checks: 18 districts and one
public-housing 3D member. Full nested schema validation included 3D arrays,
without expanding units into matching records.

| Measure | Result |
|---|---:|
| Features read | 183,964 |
| Schema-valid features | 174,456 |
| Invalid features | 9,508 (5.17%) |
| Duplicate 2D projections among valid features | 1,241 |
| Districts represented among valid features | 18 |
| Detailed audit elapsed | 566.672 seconds |
| Final DB | **Not produced** |

The first pass took 273.951 seconds; the detailed pass additionally collected
all schema errors and missing-field counters. These are audit timings, not
classification benchmarks. Different schema errors can overlap on one feature;
do not add the following counters to infer the number of rejected records.

| Missing required child | Occurrences |
|---|---:|
| English block number | 8,085 |
| Chinese block number | 83 |
| English street name | 1,373 |
| Chinese street name | 1,373 |
| English village name | 12 |
| Chinese village name | 1 |
| English floor number in 3D arrays | 444 |
| Chinese floor number in 3D arrays | 444 |
| WGS84 coordinates | 2 |
| HK1980 Northing | 2 affected features |
| HK1980 Easting | 2 affected features |

Direct reinspection confirms that only two features lack coordinates; each
lacks all three coordinate fields. The preserved detailed audit reports four
missing-field occurrences for Northing and Easting because it ran the older
counter: each of two required-field errors repeated both missing names. The
counter has since been fixed with a RED/GREEN regression, without rewriting
the historical audit. Four `properties` required errors are valid error counts;
two affected features per missing field are the reconciled counts above.
English blocks include 8,002 ordering-only
objects and 83 objects containing descriptive information. Nameless street and
village objects still contain house-number data. The 444 floor cases in each
language contain floor descriptions and occur across 35 address features.
Deleting these nonempty objects indiscriminately would hide source information.

The two records without any coordinates are Sha Tin member record 8,796 and
Yuen Long member record 856 (one-based). Neither has another same-CsuId record
or an identical complete bilingual projection in the source. There is no
source-backed repair available from this snapshot.

## Disposition

The builder refuses to publish a DB when any record is invalid. It preserves
aggregate audit evidence and removes unpublished database files. The detailed
local receipt is `builds/hk-als-2026-10-23/pack-candidate-audited/audit.json`.
The original source and official schema have not been rewritten.

A user decision has been requested on a narrowly scoped alternative: quarantine
all invalid features and build an explicitly partial-coverage test pack from
the valid features. That policy has **not** been applied. A data release, actual
regional-enabled private replay and real-pack performance/recovery gates remain
blocked until an acceptable source policy or corrected source is available.
