# World Address Sorting Engine

A Python, **offline-first**, high-volume address classifier under development. Target output: **Hongkong Post two-letter postal destination codes**, with English, Traditional Chinese and Simplified Chinese input.

## Current development status (October 2026)

- Completed prototype modules: typed contracts, HKP code catalogue validation, compact/extended local GeoNames builder, offline pack integrity checks, trilingual normalization, candidate retrieval, conservative classification rules, streaming CSV/TXT/XLSX readers, spreadsheet-safe reports, and privacy-safe input preview.
- **Not production ready:** No fully audited Hongkong Post destination master has been imported; full real-world GeoNames data has not been built; geographical scoring and country aliases still require extensive calibration; integrated job runner, checkpoint/resume, Windows GUI, and packaged Windows acceptance remain incomplete.
- Test examples use synthetic fixtures. No actual recipient address file is committed to this repository.

## Preview a production address file (no database needed)

From the repository root:

```bash
python -m pip install -e .
world-address-engine preview --input "AAAAA.csv"
```

Or without installing the package:

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m world_address_engine.cli preview --input "AAAAA.csv"
```

The preview prints JSON containing only the input filename, number of records, names/number of columns, counts of populated address lines, and decoding/unnamed-column anomalies. It **does not print or upload recipient addresses** or claim to have classified them.

For a nonstandard CSV header, pass one or more `--address-column "Column Name"`. For a Big5 file, pass `--encoding big5`. Excel input requires `python -m pip install -e ".[excel]"` and optional `--sheet SheetName`.

The current sample file uses `NAME_ADDRESS_LINE1` ... `NAME_ADDRESS_LINE5` and `Control no`. The input layer automatically detects all five address fields, preserves control identifiers (including leading zeros when represented as text), and retains all original cell values, including the six duplicate blank-header columns under unique internal names (`Unnamed_1` ...).

## Dev tests

```bash
python -m pip install -e ".[excel,test]"
python -m pytest -q
```

Linux unit/integration checks are not substitutes for independent code review, comprehensive HKP postal-master verification, and Windows offline end-to-end acceptance.

See `docs/PHASE1_PROGRESS.md` and `docs/superpowers/plans/2026-10-23-hkp-trilingual-mvp-implementation.md` for plan and release gates.
