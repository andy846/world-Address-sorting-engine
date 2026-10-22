"""Evaluate the classifier against a labelled, public-safe golden set.

The golden set holds synthetic addresses only: no customer data ever enters
this repository. Every case carries the destination it should produce, or
the status it should produce when no destination may be asserted.

The tool reports the confusion matrix, precision over asserted codes,
coverage, the review rate and the unknown rate, plus every case where the
engine asserted a destination that the label does not expect. Those false
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


def evaluate(golden_set: list[dict], pack: Path, master) -> dict:
    confusion: Counter = Counter()
    per_language: dict[str, Counter] = defaultdict(Counter)
    false_positives: list[dict] = []
    false_negatives: list[dict] = []
    status_counts: Counter = Counter()
    correct = 0
    asserted = 0

    for index, row in enumerate(golden_set, 1):
        address = row['address']
        hint = (row.get('country_hint') or '').strip() or None
        expected_code = (row.get('expected_code') or '').strip()
        expected_status = (row.get('expected_status') or '').strip()
        record = AddressRecord(index, 'golden_set.csv', None, str(index),
                               {'Address': address}, address, hint)
        result = classify_record(record, pack, master.db_path, master.approval)
        status_counts[result.status] += 1
        language = (row.get('language') or 'en').strip()
        per_language[language][result.status] += 1

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

        confusion[f'{expected_code or expected_status or "ANY"} -> {result.status}'] += 1
        if expected_code:
            false_negatives.append({
                'address': address,
                'language': language,
                'expected': expected_code,
                'predicted': result.status,
                'reason': result.reason,
            })

    total = len(golden_set)
    return {
        'total': total,
        'asserted': asserted,
        'correct_assertions': correct,
        'precision': round(correct / asserted, 4) if asserted else None,
        'coverage': round(asserted / total, 4) if total else None,
        'false_positives': false_positives,
        'false_negatives': false_negatives,
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
    return 1 if report['false_positives'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
