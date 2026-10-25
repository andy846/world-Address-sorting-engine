"""Offline public ALS sample QA; needs only the installed runtime and two DBs.

Select four source-eligible addresses each from HK/KLN/NT, in address_id order,
before constructing any predictor. Write casebank.json before predictions and
report.json with every case, full baseline/enabled country results, direct
matcher evidence, checks and aggregates. Use a NEW output directory. Exit 0
means sample checks passed, 1 means reported QA failures, 2 means an input or
operational error. No input address file, country hints or network are used.

Example (after the main builder confirms publication)::

    python tools/validate_hk_regional_public.py --global-db geo.db \
        --hk-regional-db packs/hk-bilingual-als-2026-10-23-r1-partial/pack.db \
        --output-dir out/hk-public-qa

The expected HK label is from the verified pack's declared official ALS source,
not a prediction. Integrity/provenance metadata is not independent verification
of government source contents. See LIMITATIONS for the deliberately narrow
sampling contract. Raw public source aliases and IDs are included in outputs.
"""
import argparse
from collections import Counter
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from world_address_engine.data.hk_regional import verify_hk_pack
from world_address_engine.data.pack_registry import require_readable_pack
from world_address_engine.matching.country import CountryClassifier
from world_address_engine.matching.hk_regional import HKRegionalMatcher
from world_address_engine.models import AddressRecord


REGIONS = ('HK', 'KLN', 'NT')
FORMS = ('en', 'hant', 'hans', 'mixed')
PER_REGION = 4
WRONG_NUMBER = '99999999'
LIMITATIONS = (
    'Deterministic source-derived smoke controls, not an estimate of global accuracy '
    'or exhaustive Hong Kong coverage. Four addresses per region are the first '
    'eligible address IDs in binary lexical order; this is not a random sample. '
    'Sampling requires official English and Hant building/street aliases plus '
    'pack-derived Hans aliases on the same address ID. Translations are alternative '
    'spellings of the same components, not independent evidence or an independent '
    'held-out translation test. We restrict to typed building suffixes '
    '(building/bldg/house/tower in English, 大廈 in Hant, 大厦 in Hans) so each form '
    'can exercise the address-role contract without artificial recipient prefixes. '
    'This excludes untyped buildings, estates, villages and many valid addresses. '
    'Numbers must be nonconflicting ascending Arabic endpoints of 1-7 digits '
    'with an optional Latin suffix; the lower endpoint is used. Region/district '
    'and country names are not appended to positives. Controls reuse installed '
    'aliases and are not a deliverability test. Any quarantined or absent source '
    'records are outside this installed pack sample. Country preservation is '
    'checked for every baseline-assigned case in this bank only.'
)


def _sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _read_only(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return closing(db)


def _region(row):
    names = {'hk': 'HK', 'hong kong': 'HK', 'hong kong island': 'HK', '香港': 'HK',
             '香港島': 'HK', 'kln': 'KLN', 'kowloon': 'KLN', '九龍': 'KLN',
             'nt': 'NT', 'new territories': 'NT', '新界': 'NT'}
    found = []
    for field in ('region_en', 'region_hant'):
        value = row[field]
        if value and value.strip():
            normalized = names.get(' '.join(value.casefold().split()))
            if normalized is None:
                return None
            found.append(normalized)
    return found[0] if found and len(set(found)) == 1 else None


def _endpoint(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'([0-9]{1,7})([a-z]?)', value.strip().casefold())
    return (int(match[1]), match[2]) if match and int(match[1]) > 0 else None


def _typed(name, language):
    suffix = {'en': r'\b(?:building|bldg|house|tower)\s*$',
              'zh-Hant': r'大廈\s*$', 'zh-Hans': r'大厦\s*$'}[language]
    return re.search(suffix, name, re.I) is not None


def _entity(db, row, region):
    low = _endpoint(row['number_from'])
    high = _endpoint(row['number_to'] or row['number_from'])
    if row['number_conflict'] or low is None or high is None or low > high:
        return None
    aliases = [dict(alias) for alias in db.execute(
        'SELECT address_id,kind,language,name,search_key,derived FROM hk_aliases '
        "WHERE address_id=? AND kind IN ('building','street') "
        'ORDER BY kind,language,search_key COLLATE BINARY,name COLLATE BINARY', (row['address_id'],))]
    groups = {kind: {a['search_key'] for a in aliases if a['kind'] == kind}
              for kind in ('building', 'street')}
    if groups['building'] & groups['street']:
        return None
    selected = {}
    for kind in ('building', 'street'):
        selected[kind] = {}
        for language in ('en', 'zh-Hant', 'zh-Hans'):
            options = [a for a in aliases if a['kind'] == kind and a['language'] == language
                       and a['derived'] == int(language == 'zh-Hans')
                       and a['name'].strip() and not any(ord(c) < 32 for c in a['name'])
                       and (kind != 'building' or _typed(a['name'], language))]
            if not options:
                return None
            selected[kind][language] = options[0]
    return {**dict(row), 'region': region, 'number': row['number_from'].strip(), 'aliases': selected}


def _forms(entity, number):
    aliases = entity['aliases']
    def name(kind, lang):
        return aliases[kind][lang]['name']
    return {
        'en': (name('building', 'en'), f"{number} {name('street', 'en')}"),
        'hant': (name('building', 'zh-Hant'), f"{name('street', 'zh-Hant')}{number}號"),
        'hans': (name('building', 'zh-Hans'), f"{name('street', 'zh-Hans')}{number}号"),
        'mixed': (name('building', 'en'), f"{name('street', 'zh-Hant')}{number}號"),
    }


def _cases(entity):
    wrong = _forms(entity, WRONG_NUMBER)
    cases = []
    for form, (building, street) in _forms(entity, entity['number']).items():
        original = building + '\n' + street
        variants = [('positive', original, 'HK', True)]
        variants.extend(('foreign', original + '\n' + country, code, None)
                        for code, country in (('JP', 'Japan'), ('GB', 'United Kingdom'), ('CN', 'China')))
        variants.extend((('wrong_house', '\n'.join(wrong[form]), None, False),
                         ('building_only', building, None, False),
                         ('street_only', street, None, False)))
        for kind, text, country, direct in variants:
            cases.append({'case_id': f"{entity['region']}:{entity['address_id']}:{form}:{kind}"
                          + (f':{country}' if kind == 'foreign' else ''),
                          'address_id': entity['address_id'], 'region': entity['region'],
                          'form': form, 'kind': kind, 'text': text,
                          'expected_country': country, 'expected_direct_match': direct})
    return cases


def build_casebank(hk_regional_db):
    """Select solely from verified source rows; never call a predictor here."""
    path = Path(hk_regional_db).resolve()
    manifest_path = path.with_name('manifest.json')
    manifest_hash = _sha256(manifest_path)
    metadata = verify_hk_pack(path)
    url = urlsplit(metadata['source_url'])
    if (url.scheme != 'https' or url.hostname not in {'als.gov.hk', 'www.als.gov.hk'}
            or url.username is not None or url.password is not None):
        raise ValueError('Expected official HTTPS ALS Hong Kong source provenance')
    selected = {region: [] for region in REGIONS}
    scanned = 0
    with _read_only(path) as db:
        for row in db.execute('SELECT * FROM hk_addresses ORDER BY address_id COLLATE BINARY'):
            scanned += 1
            region = _region(row)
            if region is None or len(selected[region]) == PER_REGION:
                continue
            entity = _entity(db, row, region)
            if entity is not None:
                selected[region].append(entity)
            if all(len(group) == PER_REGION for group in selected.values()):
                break
    counts = {region: len(group) for region, group in selected.items()}
    if any(count != PER_REGION for count in counts.values()):
        raise ValueError(f'Require four (4) source-eligible addresses per HK/KLN/NT region; found {counts}')
    if _sha256(path) != metadata['db_sha256'] or _sha256(manifest_path) != manifest_hash:
        raise ValueError('Hong Kong pack changed during source selection')
    entities = [entity for region in REGIONS for entity in selected[region]]
    return {'schema_version': 1, 'selection_version': 'hk-public-source-v1',
            'pack': metadata, 'pack_path': str(path), 'manifest_sha256': manifest_hash,
            'expected_hk_basis': 'Verified installed pack declares official Hong Kong ALS source; '
                                 'not inferred from model outputs or supplied as an input hint.',
            'selection': {'per_region': PER_REGION, 'region_counts': counts,
                          'order': 'address_id COLLATE BINARY', 'source_rows_scanned': scanned},
            'limitations': LIMITATIONS, 'entities': entities,
            'cases': [case for entity in entities for case in _cases(entity)]}


def _global_identity(path):
    """Validate global/runtime pack identity without any build-time dependencies."""
    path = Path(path).resolve()
    version = require_readable_pack(path)
    with _read_only(path) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='hk_addresses'").fetchone():
            raise ValueError('global-db must be a global GeoNames pack')
        profile = db.execute('SELECT profile FROM pack_metadata LIMIT 1').fetchone()[0]
    manifest = path.with_name('manifest.json')
    return {'path': str(path), 'db_sha256': _sha256(path), 'profile': profile,
            'pack_format_version': version,
            'manifest_sha256': _sha256(manifest) if manifest.is_file() else None}


def _result(value):
    return {key: list(item) if isinstance(item, tuple) else item for key, item in asdict(value).items()}


def _evaluate(case, baseline, enabled, direct):
    checks = {}
    if baseline.country_code is not None:
        checks['baseline_assigned_preservation'] = baseline == enabled
    if case['expected_country'] is not None:
        checks['enabled_country'] = enabled.country_code == case['expected_country']
    if case['kind'] == 'foreign':
        checks['foreign_baseline_assignment'] = baseline.country_code == case['expected_country']
    if case['expected_direct_match'] is True:
        checks['direct_positive'] = direct is not None and case['address_id'] in direct.address_ids
    elif case['expected_direct_match'] is False:
        checks['direct_negative'] = direct is None
        checks['no_regional_promotion'] = enabled.reason != 'HK_REGIONAL_ADDRESS_MATCH'
    return {'case_id': case['case_id'], 'region': case['region'], 'form': case['form'],
            'kind': case['kind'], 'baseline': _result(baseline), 'enabled': _result(enabled),
            'direct': _result(direct) if direct is not None else None,
            'checks': checks, 'failures': [name for name, passed in checks.items() if not passed]}


def _counts(results):
    def counts(which, field):
        return dict(sorted(Counter(r[which][field] or 'UNRESOLVED' for r in results).items()))
    return {'cases': len(results), 'failures': sum(bool(r['failures']) for r in results),
            'failure_counts': dict(sorted(Counter(f for r in results for f in r['failures']).items())),
            'baseline_assigned': sum(r['baseline']['country_code'] is not None for r in results),
            'baseline_assigned_changed': sum('baseline_assigned_preservation' in r['failures'] for r in results),
            'regional_upgrades': sum(r['baseline']['country_code'] is None
                                     and r['enabled']['reason'] == 'HK_REGIONAL_ADDRESS_MATCH' for r in results),
            'baseline_countries': counts('baseline', 'country_code'),
            'enabled_countries': counts('enabled', 'country_code'),
            'baseline_reasons': counts('baseline', 'reason'), 'enabled_reasons': counts('enabled', 'reason')}


def _write_json(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')


def validate(global_db, hk_regional_db, output_dir):
    """Freeze the complete source-based bank, then evaluate every case unchanged."""
    global_db, hk_regional_db, output_dir = map(lambda p: Path(p).resolve(),
                                               (global_db, hk_regional_db, output_dir))
    bank = build_casebank(hk_regional_db)
    global_identity = _global_identity(global_db)
    output_dir.mkdir(parents=True, exist_ok=False)
    bank_path = output_dir / 'casebank.json'
    _write_json(bank_path, bank)
    bank_hash = _sha256(bank_path)
    results = []
    with CountryClassifier(global_db) as baseline, CountryClassifier(
            global_db, hk_regional_db=hk_regional_db) as enabled, HKRegionalMatcher(hk_regional_db) as matcher:
        for number, case in enumerate(bank['cases'], 1):
            # Pass original public source text through the public country API.
            # Expected labels and source identity stay outside the input record.
            record = AddressRecord(number, 'public-als-controls', None, None,
                                   {'Address': case['text']}, case['text'], None)
            results.append(_evaluate(case, baseline.classify(record), enabled.classify(record),
                                     matcher.match(case['text'])))
    if (verify_hk_pack(hk_regional_db) != bank['pack']
            or _sha256(hk_regional_db.with_name('manifest.json')) != bank['manifest_sha256']
            or _global_identity(global_db) != global_identity or _sha256(bank_path) != bank_hash):
        raise ValueError('Input pack or case bank changed during QA; no completed report published')
    aggregate = _counts(results)
    for field in ('region', 'form', 'kind'):
        aggregate['by_' + field] = {value: _counts([r for r in results if r[field] == value])
                                    for value in sorted({r[field] for r in results})}
    report = {'schema_version': 1, 'passed': aggregate['failures'] == 0,
              'casebank_sha256': bank_hash, 'global_pack': global_identity,
              'hk_pack': bank['pack'], 'hk_manifest_sha256': bank['manifest_sha256'],
              'country_rules_version': CountryClassifier.rules_version,
              'limitations': LIMITATIONS, 'aggregate': aggregate, 'results': results}
    _write_json(output_dir / 'report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--global-db', type=Path, required=True)
    parser.add_argument('--hk-regional-db', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New directory for public case bank and report')
    args = parser.parse_args(argv)
    try:
        report = validate(args.global_db, args.hk_regional_db, args.output_dir)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f'Public HK QA could not complete: {exc}', file=sys.stderr)
        return 2
    print(json.dumps({'passed': report['passed'], 'aggregate': report['aggregate'],
                      'output_dir': str(args.output_dir.resolve())}, ensure_ascii=True, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
