# GeoNames data pack preservation - 2026-10-23

The original Actions run `39827512415` databases and the k2 rebuild are now
preserved as separate GitHub geographic developer-preview prereleases:

- [Original CI k1 archives](https://github.com/andy846/world-Address-sorting-engine/releases/tag/geonames-packs-2026-10-22)
- [Current k2 reference packs](https://github.com/andy846/world-Address-sorting-engine/releases/tag/geonames-packs-2026-10-22-k2)

Both target commit `adafeed`. These private-repository release assets require
repository access. They have no scheduled Actions retention expiry; they
remain available until explicitly deleted or the repository becomes
unavailable. They do not replace the published `v0.1.0-alpha.0` release.

## Verified database identities

| Generation | Profile | SQLite bytes | MiB | ZIP bytes | SQLite SHA-256 |
|---|---|---:|---:|---:|---|
| k1 | COMPACT_GLOBAL | 143,949,824 | 137.281 | 56,535,390 | `e3b8b710e7acf05e0fe3618abecc5745d13d07a7826ae1f2a41767561faa2d2d` |
| k1 | EXTENDED_GLOBAL | 1,098,661,888 | 1,047.766 | 423,280,495 | `fb0e4774cc360ec5fe7b22d2b8176feea031abf02a6277dc42a3877c9da2074a` |
| k2 | COMPACT_GLOBAL | 142,577,664 | 135.973 | 56,480,487 | `f4ef044e94aa3d206f8fce1fa3e0d7ab5f03d6081d142fd7f9e8cf5837ab1b3f` |
| k2 | EXTENDED_GLOBAL | 1,087,344,640 | 1,036.973 | 420,832,046 | `70d617a532b8faedd7d9703c9b952945f101334907df5936725123d20be1f70f` |

Each release carries eight assets: two SQLite ZIPs, two install manifests,
`build_report.json`, `SHA256SUMS.txt`, `ATTRIBUTION.md`, and `verification.json`.
The original CI build report and database/archive bytes are unchanged.
The k1 companion manifests explicitly identify key format k1 while retaining
the original installed pack version `2026-10-22`.

SQLite header writer versions: k1 `3.45.1`; k2 `3.45.3`. Both retain the
same pinned source archives. All source, place and alias counts are in the
reports and manifests. Data is GeoNames, CC BY 4.0, with attribution and
transform notes in each release.

## Validation evidence

- Full real-pack suite with `WASE_SLOW_CHECKS=1`: 39 passed for each
  `WASE_PACK_GENERATION` (`2026-10-22` and `2026-10-22-k2`). Tests include
  exact database SHA-256, SQLite integrity, schema, counts, language
  distribution, indexed query plans, installation, activation and tampering.
- Every released ZIP member was streamed and its uncompressed SQLite hash
  compared with the installed database and manifest. The installer never
  relies only on a compressed-file hash.
- All 16 GitHub asset sizes and server-reported SHA-256 digests were compared
  with the local release files, including the final metadata corrections.
- The complete k2 release was independently downloaded from GitHub. All
  downloaded assets passed `SHA256SUMS.txt`; both SQLite payloads matched
  their manifests. Both were installed into fresh versioned directories
  with Python socket connect operations denied. Indexed Tokyo/Shinjuku and
  Hong Kong retrieval succeeded offline in both profiles.
- An independent reviewer approved publication as geographic preview data.
  Two documentation caveats were corrected before publication: the test
  command now names its generation, and the notes list all eight assets.

## Download and install

On a connected machine with repository access:

```powershell
gh release download geonames-packs-2026-10-22-k2 --repo andy846/world-Address-sorting-engine --dir downloaded-packs
```

Verify the downloaded files against `SHA256SUMS.txt`, extract the desired
ZIP, and transfer the database and matching manifest to the offline machine.
For example:

```powershell
python tools/install_reference_pack.py --database downloaded-packs/compact_global.sqlite --manifest downloaded-packs/compact_global.manifest.json --active-root packs
```

The manifest pins the extracted database hash. Installation is immutable
and refuses to overwrite an existing version. Install Extended using the
corresponding two Extended files.

The current batch runner requires k2. The archived k1 databases remain
installable and directly queryable with SQLite for audit, but the runner
refuses them because their punctuation-bearing keys differ from its reader.

## Remaining application gates

These are geographic reference packs. The verified Hongkong Post destination
master remains unavailable; fixture codes do not authorize production use.
Known nested-name classification defects, completed 100k/1M/5M measurements,
and usable Windows packaged/offline acceptance remain separate gates. A
real Windows onefile build was attempted and its self-test correctly
reported a QtCore DLL import failure; no successful packaged-startup claim
is made here.
