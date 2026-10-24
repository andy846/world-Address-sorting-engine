"""Read-only regional pack verification, normalized keys and immutable install."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import unicodedata

PROFILE = 'HK_BILINGUAL_REGIONAL'
SCHEMA_VERSION = NORMALIZATION_VERSION = 1
_NOISE = frozenset(('the a an of and road rd street st avenue lane ln building bldg '
                    'industrial commercial centre center tower plaza house factory estate '
                    'block floor flat room unit court mansion').split())


def normalize_hk_key(text: str) -> str:
    value = unicodedata.normalize('NFKC', text).casefold()
    value = re.sub(r'[^\w]+|_', ' ', value, flags=re.UNICODE)
    value = re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])', '', value)
    return ' '.join(value.split())


def alias_anchor(key: str) -> str:
    key = normalize_hk_key(key)
    han = re.findall(r'[\u3400-\u9fff]{2,}', key)
    if han:
        return max(han, key=lambda value: (len(value), value))[:3]
    words = [word for word in re.findall(r'[a-z][a-z0-9]*', key) if word not in _NOISE]
    return max(words, key=lambda value: (len(value), value)) if words else ''


def _hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _standalone_database(path):
    with path.open('rb') as stream:
        header = stream.read(20)
    if (len(header) != 20 or header[:16] != b'SQLite format 3\0' or
            header[18:20] != b'\x01\x01' or
            any(path.with_name(path.name + suffix).exists() for suffix in ('-wal', '-journal'))):
        raise ValueError('Hong Kong pack must be a standalone SQLite database without WAL/journal files')


def _verify_source_validation(metadata, db_path):
    """Validate optional source coverage and stream the required quarantine log."""
    if 'source_validation' not in metadata:
        return None
    validation = metadata['source_validation']
    required = {'policy', 'coverage', 'feature_count', 'valid_feature_count',
                'quarantined_feature_count', 'quarantine_file', 'quarantine_sha256'}
    if not isinstance(validation, dict) or set(validation) != required:
        raise ValueError('Hong Kong pack source validation is incomplete')
    if (validation['policy'] not in ('strict', 'quarantine-invalid') or
            validation['coverage'] not in ('complete', 'partial')):
        raise ValueError('invalid Hong Kong pack source validation policy/coverage')
    for key in ('feature_count', 'valid_feature_count', 'quarantined_feature_count'):
        if type(validation[key]) is not int or validation[key] < 0:
            raise ValueError('invalid Hong Kong pack source validation count')
    excluded = validation['quarantined_feature_count']
    if (validation['valid_feature_count'] + excluded != validation['feature_count'] or
            metadata['record_count'] > validation['valid_feature_count'] or
            (validation['coverage'] == 'partial') != (excluded > 0)):
        raise ValueError('Hong Kong pack source validation counts/coverage mismatch')
    if validation['policy'] == 'strict':
        if (excluded or validation['quarantine_file'] is not None or
                validation['quarantine_sha256'] is not None):
            raise ValueError('strict Hong Kong pack cannot quarantine source features')
        return None
    checksum = validation['quarantine_sha256']
    if (validation['quarantine_file'] != 'quarantine.jsonl' or
            not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum)):
        raise ValueError('invalid Hong Kong pack quarantine file/checksum')
    path = db_path.with_name('quarantine.jsonl')
    digest = hashlib.sha256()
    count = 0
    locators = set()
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate Hong Kong pack quarantine object key')
            result[key] = value
        return result
    with path.open('rb') as stream:
        for line in stream:
            digest.update(line)
            entry = json.loads(line.decode('utf8'), object_pairs_hook=unique_fields)
            if (not isinstance(entry, dict) or
                    set(entry) != {'source_member', 'source_index', 'reason'} or
                    not isinstance(entry.get('source_member'), str) or
                    type(entry.get('source_index')) is not int or entry['source_index'] < 1 or
                    entry.get('reason') not in ('feature_schema', 'invalid_hk_address')):
                raise ValueError('invalid Hong Kong pack quarantine entry')
            locator = entry['source_member'], entry['source_index']
            if locator in locators:
                raise ValueError('duplicate Hong Kong pack quarantine feature locator')
            locators.add(locator)
            count += 1
            if count > excluded:
                raise ValueError('Hong Kong pack quarantine count mismatch')
    if count != excluded:
        raise ValueError('Hong Kong pack quarantine count mismatch')
    if digest.hexdigest() != checksum:
        raise ValueError('Hong Kong pack quarantine checksum mismatch')
    return path


def verify_hk_pack(db_path: Path, *, full: bool = True) -> dict:
    db_path = Path(db_path).resolve()
    manifest_path = db_path.with_name('manifest.json')
    if not db_path.is_file() or not manifest_path.is_file():
        raise ValueError('Hong Kong pack requires pack.db and manifest.json')
    try:
        metadata = json.loads(manifest_path.read_text(encoding='utf-8'))
        required = {'pack_id','profile','pack_version','schema_version','normalization_version',
                    'source_date','source_url','source_sha256','schema_sha256','db_sha256',
                    'record_count','building_count','alias_count','alias_count_by_language',
                    'conversion_version','attribution','license'}
        if not isinstance(metadata, dict) or not required <= metadata.keys():
            raise ValueError('Hong Kong pack manifest is incomplete')
        if (metadata['profile'] != PROFILE or type(metadata['schema_version']) is not int or
                metadata['schema_version'] != 1 or type(metadata['normalization_version']) is not int or
                metadata['normalization_version'] != 1):
            raise ValueError('unsupported Hong Kong pack profile/schema/normalization')
        for key in ('pack_id','pack_version'):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', str(metadata[key])):
                raise ValueError('unsafe Hong Kong pack identity')
        for key in ('source_sha256','schema_sha256','db_sha256'):
            if not isinstance(metadata[key], str) or not re.fullmatch('[0-9a-f]{64}', metadata[key]):
                raise ValueError('invalid Hong Kong pack checksum')
        for key in ('record_count','building_count','alias_count'):
            if type(metadata[key]) is not int or metadata[key] <= 0:
                raise ValueError('invalid Hong Kong pack count')
        languages = metadata['alias_count_by_language']
        if (not isinstance(languages, dict) or not languages or
                not set(languages) <= {'en','zh-Hant','zh-Hans'} or
                any(type(count) is not int or count < 0 for count in languages.values())):
            raise ValueError('invalid Hong Kong pack language counts')
        if any(not metadata[key] for key in ('source_url','source_date','conversion_version','attribution','license')):
            raise ValueError('missing Hong Kong pack provenance')
        quarantine_path = _verify_source_validation(metadata, db_path)
        if _hash(db_path) != metadata['db_sha256']:
            raise ValueError('Hong Kong pack checksum mismatch')
        _standalone_database(db_path)
        with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'hk_buildings','hk_addresses','hk_aliases','hk_pack_metadata'} <= tables:
                raise ValueError('invalid Hong Kong pack tables')
            columns = {
                'hk_buildings': {'csu_id'},
                'hk_addresses': set(('address_id csu_id source_member source_index geo_address longitude latitude '
                                     'region_en region_hant district_en district_hant number_from number_to number_conflict').split()),
                'hk_aliases': set('address_id kind language name search_key derived anchor'.split()),
                'hk_pack_metadata': {'profile','schema_version','normalization_version'},
            }
            for table, expected in columns.items():
                if not expected <= {row[1] for row in db.execute(f'PRAGMA table_info({table})')}:
                    raise ValueError('Hong Kong pack query schema is incomplete')
            for table, keys in (('hk_buildings',['csu_id']), ('hk_addresses',['address_id']),
                                ('hk_aliases',['address_id','kind','language','search_key'])):
                info = db.execute(f'PRAGMA table_info({table})').fetchall()
                if [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]] != keys:
                    raise ValueError('Hong Kong pack primary key schema mismatch')
            required_values = {
                'hk_buildings': "csu_id IS NULL OR trim(csu_id)=''",
                'hk_addresses': "address_id IS NULL OR trim(address_id)='' OR csu_id IS NULL OR "
                                "source_member IS NULL OR trim(source_member)='' OR source_index IS NULL OR "
                                "typeof(source_index)!='integer' OR source_index<0 OR number_conflict IS NULL OR "
                                "number_conflict NOT IN(0,1)",
                'hk_aliases': "address_id IS NULL OR kind IS NULL OR language IS NULL OR name IS NULL OR "
                              "search_key IS NULL OR trim(search_key)='' OR anchor IS NULL OR derived IS NULL OR "
                              "derived NOT IN(0,1) OR kind NOT IN('building','estate','street','village','district')",
            }
            for table, invalid in required_values.items():
                if db.execute(f'SELECT 1 FROM {table} WHERE {invalid} LIMIT 1').fetchone():
                    raise ValueError('Hong Kong pack required values are missing or invalid')
            if db.execute('SELECT profile,schema_version,normalization_version FROM hk_pack_metadata').fetchall() != [(PROFILE,1,1)]:
                raise ValueError('Hong Kong pack profile metadata mismatch')
            for table, key in (('hk_buildings','building_count'),('hk_addresses','record_count'),('hk_aliases','alias_count')):
                if db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] != metadata[key]:
                    raise ValueError('Hong Kong pack count mismatch')
            counts = dict(db.execute('SELECT language,COUNT(*) FROM hk_aliases GROUP BY language'))
            if {key: value for key,value in languages.items() if value} != counts:
                raise ValueError('Hong Kong pack alias language mismatch')
            indexes = {row[1]: row for row in db.execute('PRAGMA index_list(hk_aliases)')}
            for index, expected in (
                    ('hk_alias_lookup',['search_key','kind','address_id']),
                    ('hk_alias_anchor',['anchor','address_id']),('hk_alias_address',['address_id'])):
                if (index not in indexes or indexes[index][4] or
                        [row[2] for row in db.execute(f'PRAGMA index_info({index})')] != expected):
                    raise ValueError('Hong Kong pack lookup index missing')
            for child, parent, key in (('hk_addresses','hk_buildings','csu_id'),
                                        ('hk_aliases','hk_addresses','address_id')):
                if db.execute(f'SELECT 1 FROM {child} c WHERE NOT EXISTS '
                              f'(SELECT 1 FROM {parent} p WHERE p.{key}=c.{key}) LIMIT 1').fetchone():
                    raise ValueError('Hong Kong pack broken entity references')
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError('Hong Kong pack broken entity references')
            if full and db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Hong Kong pack integrity check failed')
        # Verify metadata and bytes again after consuming them.
        if (json.loads(manifest_path.read_text(encoding='utf8')) != metadata or
                _hash(db_path) != metadata['db_sha256'] or
                (quarantine_path is not None and
                 _hash(quarantine_path) != metadata['source_validation']['quarantine_sha256'])):
            raise ValueError('Hong Kong pack changed during verification')
        _standalone_database(db_path)
        return metadata
    except (OSError, sqlite3.Error, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid or unreadable Hong Kong regional pack') from exc


def hk_pack_metadata(db_path: Path) -> dict:
    path = Path(db_path).resolve()
    try:
        before = _hash(path.with_name('manifest.json'))
        metadata = verify_hk_pack(path, full=False)
        if _hash(path.with_name('manifest.json')) != before:
            raise ValueError('Hong Kong pack manifest changed during verification')
    except OSError as exc:
        raise ValueError('invalid or unreadable Hong Kong regional pack manifest') from exc
    pinned = {'path': str(path), 'profile': metadata['profile'], 'version': metadata['pack_version'],
              'schema_version': metadata['schema_version'], 'db_sha256': metadata['db_sha256'],
              'manifest_sha256': before}
    if 'source_validation' in metadata:
        pinned['source_validation'] = metadata['source_validation']
    return pinned


def install_hk_pack(staging_dir: Path, active_root: Path) -> Path:
    staging_dir, active_root = Path(staging_dir).resolve(), Path(active_root).resolve()
    metadata = verify_hk_pack(staging_dir / 'pack.db')
    identity = hk_pack_metadata(staging_dir / 'pack.db')
    active_root.mkdir(parents=True, exist_ok=True)
    destination = active_root / f"{metadata['pack_id']}-{metadata['pack_version']}"
    if destination.exists():
        raise FileExistsError('Hong Kong pack version already installed; do not overwrite')
    temporary = Path(tempfile.mkdtemp(prefix='.hk-pack-', dir=active_root))
    try:
        names = ['pack.db', 'manifest.json', 'ATTRIBUTION.txt', 'audit.json']
        if metadata.get('source_validation', {}).get('quarantine_file') == 'quarantine.jsonl':
            names.append('quarantine.jsonl')
        for name in names:
            if (staging_dir / name).is_file():
                shutil.copy2(staging_dir / name, temporary / name)
        copied = verify_hk_pack(temporary / 'pack.db')
        if (copied != metadata or copied['db_sha256'] != identity['db_sha256'] or
                _hash(temporary / 'manifest.json') != identity['manifest_sha256']):
            raise ValueError('Hong Kong pack source snapshot changed during installation')
        if destination.exists():
            raise FileExistsError('Hong Kong pack version appeared during installation')
        temporary.rename(destination)
        return destination / 'pack.db'
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
