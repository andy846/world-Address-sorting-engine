"""Evaluate the classifier against a labelled, public-safe golden set.

The golden set holds synthetic addresses only: no customer data ever enters
this repository. Every case states the destination it should produce, and
where the catalogue in use does not issue that destination, the case still
states the *country* the geography has to resolve to. The two are separate
questions:

* did the engine find the right place on the map, and
* does the approved catalogue issue a postal code for it.

A catalogue that has no row for Portugal is a coverage gap of the master,
not a geographic error, and the report says so.

The tool reports the confusion matrix, precision over asserted codes,
coverage, the review rate and the unknown rate, plus every case where the
engine asserted a destination the label does not expect. Those false
positives are the number that matters: an address that is silently sent to
the wrong country.

Usage:

    python tools/evaluate_golden_set.py \
        --pack packs/geonames-extended-global-2026-10-22/pack.db \
        --golden-set tests/fixtures/golden_set.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'src'))

from world_address_engine.matching.classify import classify_record  # noqa: E402
from world_address_engine.models import AddressRecord  # noqa: E402

GOLDEN_SET = REPO_ROOT / 'tests' / 'fixtures' / 'golden_set.csv'


def load_golden_set(path: Path) -> list[dict]:
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return [row for row in csv.DictReader(stream)
                if (row.get('address') or '').strip()]


def build_master(directory: Path):
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tests.hkp_master_fixture import build_master as _build
    return _build(directory)


def catalogue_indexes(catalogue: Path):
    """The codes the catalogue issues, and the ISO each destination carries."""
    from world_address_engine.sqlite_util import open_db
    with open_db(Path(catalogue)) as conn:
        codes = {str(row[0]) for row in conn.execute(
            "SELECT DISTINCT code FROM destinations "
            "WHERE code_scheme='HKP_DESTINATION_2' AND profile='HKP_DESTINATION_2' "
            "AND approval_status='APPROVED'")}
        iso_by_destination = {str(row[0]): str(row[1]) for row in conn.execute(
            "SELECT destination_id, code FROM destinations "
            "WHERE code_scheme='ISO_ALPHA2' AND profile='ISO'")}
    return codes, iso_by_destination


def resolved_iso(result, iso_by_destination: dict) -> str:
    """The country the engine settled on, if it settled on one."""
    if result.status == 'MATCHED' and result.destination_id:
        return iso_by_destination.get(result.destination_id, '')
    for entry in result.evidence:
        if entry.startswith('GEOGRAPHY:'):
            return entry.split(':', 1)[1]
    return ''


def evaluate(golden_set: list[dict], pack: Path, master) -> dict:
    confusion: Counter = Counter()
    per_language: dict[str, Counter] = defaultdict(Counter)
    false_positives: list[dict] = []
    false_negatives: list[dict] = []
    geography_errors: list[dict] = []
    status_errors: list[dict] = []
    status_counts: Counter = Counter()
    issued_codes, iso_by_destination = catalogue_indexes(master.db_path)
    correct = 0
    asserted = 0
    geography_correct = 0
    geography_expected = 0

    for index, row in enumerate(golden_set, 1):
        address = row['address']
        hint = (row.get('country_hint') or '').strip() or None
        expected_code = (row.get('expected_code') or '').strip()
        expected_iso = (row.get('expected_iso') or '').strip()
        expected_status = (row.get('expected_status') or '').strip()
        record = AddressRecord(index, 'golden_set.csv', None, str(index),
                               {'Address': address}, address, hint)
        result = classify_record(record, pack, master.db_path, master.approval)
        status_counts[result.status] += 1
        language = (row.get('language') or 'en').strip()
        per_language[language][result.status] += 1
        found_iso = resolved_iso(result, iso_by_destination)

        # 1. A status the label forbids must be produced exactly.
        if expected_status and expected_status != 'MATCHED' \
                and result.status != expected_status:
            status_errors.append({
                'address': address, 'language': language,
                'expected': expected_status, 'predicted': result.status,
                'reason': result.reason,
            })
            confusion[f'{expected_status} -> {result.status}'] += 1
            continue

        # 2. The country the geography has to resolve to.
        if expected_iso:
            geography_expected += 1
            if found_iso == expected_iso:
                geography_correct += 1
            elif result.status == 'MATCHED' or found_iso:
                geography_errors.append({
                    'address': address, 'language': language,
                    'expected': expected_iso, 'predicted': found_iso,
                    'status': result.status, 'reason': result.reason,
                })

        # 3. The code that may be asserted.
        if result.status == 'MATCHED':
            asserted += 1
            predicted = result.hkp_code or ''
            if expected_code and predicted == expected_code:
                correct += 1
                confusion[f'{expected_code} -> {predicted}'] += 1
            else:
                confusion[f'{expected_code or expected_status or "ANY"} -> {predicted}'] += 1
                false_positives.append({
                    'address': address,
                    'language': language,
                    'expected': expected_code or expected_status or 'ANY',
                    'predicted': predicted,
                    'status': result.status,
                    'reason': result.reason,
                    'confidence': result.confidence,
                })
            continue

        if expected_code:
            if expected_code in issued_codes:
                confusion[f'{expected_code} -> {result.status}'] += 1
                false_negatives.append({
                    'address': address,
                    'language': language,
                    'expected': expected_code,
                    'predicted': result.status,
                    'reason': result.reason,
                })
            else:
                # The master issues no code for this country, so a review is
                # the right answer, not an error.
                confusion[f'{expected_code} -> {result.status} (no mapping)'] += 1
        else:
            confusion[f'{expected_status or expected_iso or "ANY"} -> {result.status}'] += 1

    total = len(golden_set)
    return {
        'total': total,
        'asserted': asserted,
        'correct_assertions': correct,
        'precision': round(correct / asserted, 4) if asserted else None,
        'coverage': round(asserted / total, 4) if total else None,
        'geography_expected': geography_expected,
        'geography_correct': geography_correct,
        'geography_accuracy': (round(geography_correct / geography_expected, 4)
                               if geography_expected else None),
        'false_positives': false_positives,
        'false_negatives': false_negatives,
        'geography_errors': geography_errors,
        'status_errors': status_errors,
        'status_counts': dict(status_counts),
        'review_rate': round(sum(count for status, count in status_counts.items()
                                 if status.startswith('REVIEW')) / total, 4) if total else None,
        'unknown_rate': round(status_counts.get('UNKNOWN', 0) / total, 4) if total else None,
        'confusion': dict(confusion),
        'per_language': {language: dict(counts)
                         for language, counts in per_language.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--golden-set', type=Path, default=GOLDEN_SET)
    parser.add_argument('--work-dir', type=Path,
                        default=REPO_ROOT / '.tmp' / 'golden-master')
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.pack.is_file():
        raise SystemExit(f'reference pack not found: {args.pack}')
    golden_set = load_golden_set(args.golden_set)
    master = build_master(args.work_dir)
    report = evaluate(golden_set, args.pack, master)
    report['pack'] = str(args.pack)
    report['golden_set'] = str(args.golden_set)

    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('confusion',)}, indent=2, ensure_ascii=False))
    print('\nconfusion matrix (expected -> predicted):')
    for key, count in sorted(report['confusion'].items()):
        print(f'  {key}: {count}')
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                            encoding='utf-8')
        print(f'\nwrote {args.out}')
    return 1 if (report['false_positives'] or report['geography_errors']
                 or report['status_errors']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
