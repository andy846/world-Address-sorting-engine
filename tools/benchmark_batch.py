"""Measure end-to-end throughput of the offline classification pipeline.

The tool generates a synthetic address file of a requested size, runs the
real streaming job against a real reference pack, and reports the measured
wall-clock time, throughput, peak resident memory, checkpoint size and
export size. Nothing here is an estimate: every number is produced by the
run that is being measured.

Usage:

    python tools/benchmark_batch.py --rows 10000 --rows 100000 \
        --pack packs/geonames-compact-global-2026-10-22/pack.db

The reference pack must be a real, installed GeoNames pack. The HK Post
catalogue used here is the signed **test fixture** master, so the run is a
throughput measurement of the pipeline, never evidence of postal accuracy.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'src'))

from world_address_engine.jobs.runner import resume_job, run_job  # noqa: E402

# Coherent synthetic places: the city and the country always belong
# together, so a generated address is a plausible mailing address rather
# than a contradiction. The pool is far larger than any cache would hold,
# so the measurement is not dominated by repeated identical lookups.
#
# (city_en, city_tc, city_sc, country_en, country_tc, hkp_code)
PLACES = [
    ('Tokyo', '東京', '东京', 'Japan', '日本', 'JP'),
    ('Osaka', '大阪', '大阪', 'Japan', '日本', 'JP'),
    ('Kyoto', '京都', '京都', 'Japan', '日本', 'JP'),
    ('Mumbai', '孟買', '孟买', 'India', '印度', 'IN'),
    ('Chennai', '金奈', '金奈', 'India', '印度', 'IN'),
    ('Bengaluru', '班加羅爾', '班加罗尔', 'India', '印度', 'IN'),
    ('London', '倫敦', '伦敦', 'United Kingdom', '英國', 'GB'),
    ('Manchester', '曼徹斯特', '曼彻斯特', 'United Kingdom', '英國', 'GB'),
    ('New York', '紐約', '纽约', 'United States', '美國', 'US'),
    ('Chicago', '芝加哥', '芝加哥', 'United States', '美國', 'US'),
    ('Toronto', '多倫多', '多伦多', 'Canada', '加拿大', 'CA'),
    ('Vancouver', '溫哥華', '温哥华', 'Canada', '加拿大', 'CA'),
    ('Macau', '澳門', '澳门', 'Macau', '澳門', 'MO'),
    ('Hong Kong', '香港', '香港', 'Hong Kong', '香港', 'HK'),
    ('Guangzhou', '廣州', '广州', 'China', '中國', 'CN'),
    ('Shanghai', '上海', '上海', 'China', '中國', 'CN'),
    ('Beijing', '北京', '北京', 'China', '中國', 'CN'),
    ('Singapore', '新加坡', '新加坡', 'Singapore', '新加坡', 'SG'),
    ('Sydney', '悉尼', '悉尼', 'Australia', '澳大利亞', 'AU'),
    ('Melbourne', '墨爾本', '墨尔本', 'Australia', '澳大利亞', 'AU'),
    ('Berlin', '柏林', '柏林', 'Germany', '德國', 'DE'),
    ('Munich', '慕尼黑', '慕尼黑', 'Germany', '德國', 'DE'),
    ('Paris', '巴黎', '巴黎', 'France', '法國', 'FR'),
    ('Lyon', '里昂', '里昂', 'France', '法國', 'FR'),
    ('Milan', '米蘭', '米兰', 'Italy', '意大利', 'IT'),
    ('Rome', '羅馬', '罗马', 'Italy', '意大利', 'IT'),
    ('Madrid', '馬德里', '马德里', 'Spain', '西班牙', 'ES'),
    ('Barcelona', '巴塞羅那', '巴塞罗那', 'Spain', '西班牙', 'ES'),
    ('Amsterdam', '阿姆斯特丹', '阿姆斯特丹', 'Netherlands', '荷蘭', 'NL'),
    ('Rotterdam', '鹿特丹', '鹿特丹', 'Netherlands', '荷蘭', 'NL'),
    ('Bangkok', '曼谷', '曼谷', 'Thailand', '泰國', 'TH'),
    ('Chiang Mai', '清邁', '清迈', 'Thailand', '泰國', 'TH'),
    ('Ho Chi Minh City', '胡志明市', '胡志明市', 'Vietnam', '越南', 'VN'),
    ('Hanoi', '河內', '河内', 'Vietnam', '越南', 'VN'),
    ('Kuala Lumpur', '吉隆坡', '吉隆坡', 'Malaysia', '馬來西亞', 'MY'),
    ('Jakarta', '雅加達', '雅加达', 'Indonesia', '印尼', 'ID'),
    ('Seoul', '首爾', '首尔', 'South Korea', '南韓', 'KR'),
    ('Manila', '馬尼拉', '马尼拉', 'Philippines', '菲律賓', 'PH'),
    ('São Paulo', '聖保羅', '圣保罗', 'Brazil', '巴西', 'BR'),
    ('Rio de Janeiro', '里約熱內盧', '里约热内卢', 'Brazil', '巴西', 'BR'),
    ('Buenos Aires', '布宜諾斯艾利斯', '布宜诺斯艾利斯', 'Argentina', '阿根廷', 'AR'),
    ('Vienna', '維也納', '维也纳', 'Austria', '奧地利', 'AT'),
    ('Brussels', '布魯塞爾', '布鲁塞尔', 'Belgium', '比利時', 'BE'),
    ('Copenhagen', '哥本哈根', '哥本哈根', 'Denmark', '丹麥', 'DK'),
    ('Dublin', '都柏林', '都柏林', 'Ireland', '愛爾蘭', 'IE'),
    ('Auckland', '奧克蘭', '奥克兰', 'New Zealand', '新西蘭', 'NZ'),
    ('Oslo', '奧斯陸', '奥斯陆', 'Norway', '挪威', 'NO'),
    ('Stockholm', '斯德哥爾摩', '斯德哥尔摩', 'Sweden', '瑞典', 'SE'),
    ('Zurich', '蘇黎世', '苏黎世', 'Switzerland', '瑞士', 'CH'),
    ('Taipei', '臺北', '台北', 'Taiwan', '台灣', 'TW'),
    ('Kaohsiung', '高雄', '高雄', 'Taiwan', '台灣', 'TW'),
    ('Lisbon', '里斯本', '里斯本', 'Portugal', '葡萄牙', 'PT'),
    ('Athens', '雅典', '雅典', 'Greece', '希臘', 'GR'),
    ('Dili', '帝力', '帝力', 'Timor-Leste', '東帝汶', 'TP'),
    ('Hagåtña', '阿加尼亚', '阿加尼亚', 'Guam', '關島', 'GU'),
    ('San Juan', '聖胡安', '圣胡安', 'Puerto Rico', '波多黎各', 'PR'),
    ('Dubai', '杜拜', '迪拜', 'United Arab Emirates', '阿拉伯聯合酋長國', 'AE'),
]

#
# The street names below are deliberately *evidence free*.
#
# A street name is not scenery: it is a place name the reader would look
# up. "Nanjing Road" carries the name of a Chinese city and "221B Baker
# Street" the name of a London district, so a row built from them would
# measure a second, different workload on top of the one this tool claims
# to measure -- and the row could end up resolving to the street's country
# rather than to the address's.
#
# Every Latin name here is built from address-structure words that the
# reader drops as noise, so it produces no search term at all. Every
# Chinese name was checked against the real gazetteer: none of them, and
# none of the two-character fragments the reader cuts out of a Chinese
# name, resolves to any place. `street_evidence_violations` re-checks that
# against the pack a measurement is taken with, so a later edit cannot
# quietly reintroduce a place name.
STREET_EN = ('Main Street', 'Station Road', 'Central Avenue', 'Front Lane',
             'Upper Road', 'New Terrace', 'Old Square', 'Park View',
             'Bridge Road', 'Royal Court', 'Port Street', 'Tower Block')
STREET_TC = ('櫻花路', '聽雨路', '觀星路', '修身路', '紫薇路', '朝暉路',
             '冬雪路', '碧波路', '松風路', '靜謐街', '秋實路', '夏蔭路')
STREET_SC = ('樱花路', '听雨路', '观星路', '修身路', '紫薇路', '朝晖路',
             '冬雪路', '碧波路', '松风路', '静谧街', '秋实路', '夏荫路')

# The Hongkong Post destination code and the ISO 3166 alpha-2 code of a
# country are the same for almost all of them. East Timor is the
# exception: the catalogue issues TP, the gazetteer knows TL.
HKP_TO_ISO = {'TP': 'TL'}


def synthetic_addresses(index: int, place) -> tuple[str, str, str]:
    """The English, Traditional Chinese and Simplified Chinese forms of a row."""
    city_en, city_tc, city_sc, country_en, country_tc, _code = place
    style = index % 3
    if style == 0:
        street = STREET_EN[index % len(STREET_EN)]
        return f'{street}, {city_en}, {country_en}', '', ''
    if style == 1:
        street = STREET_TC[index % len(STREET_TC)]
        return f'{street} {index % 999 + 1} 號, {city_tc}, {country_tc}', '', ''
    street = STREET_SC[index % len(STREET_SC)]
    return f'{street} {index % 999 + 1} 号, {city_sc}, {country_tc}', ''


def synth_rows(total: int, places=None):
    """Yield (recipient, address, country_hint) triples."""
    pool = places or PLACES
    for index in range(total):
        address = synthetic_addresses(index, pool[index % len(pool)])[0]
        yield f'Recipient {index % 997}', address, ''


def write_source(path: Path, total: int, places=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2', 'Control no'])
        for index, (recipient, address, _hint) in enumerate(synth_rows(total, places), 1):
            writer.writerow([recipient, address, f'{index:09d}'])


def peak_rss_bytes() -> int:
    """Peak resident set size of this process, in bytes.

    The number is the high water mark of *this* process, so a measurement
    that shares a process with an earlier one cannot be attributed to it.
    Every measurement therefore runs in a process of its own.
    """
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(usage) * 1024 if usage < 10_000_000 else int(usage)
    except Exception:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ('cb', wintypes.DWORD),
                ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters),
                                        ctypes.sizeof(counters))
        if ok:
            return int(counters.PeakWorkingSetSize)
    except Exception:
        pass
    raise RuntimeError(
        'the peak resident memory of this process could not be measured; '
        'a measurement without it would report a number it cannot back up')


def tree_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob('*'):
        if item.is_file():
            total += item.stat().st_size
    return total


def _options():
    return {'encoding': 'utf-8-sig',
            'address_columns': ['NAME_ADDRESS_LINE2'],
            'record_id_column': None,
            'sheet_name': None}


def _child_environment() -> dict:
    """The environment a measurement process needs to find the package."""
    environment = dict(os.environ)
    parts = [str(REPO_ROOT / 'src'), str(REPO_ROOT)]
    existing = environment.get('PYTHONPATH')
    if existing:
        parts.append(existing)
    environment['PYTHONPATH'] = os.pathsep.join(parts)
    environment['PYTHONIOENCODING'] = 'utf-8'
    return environment


def _run_in_child(kind: str, options: dict) -> dict:
    """Run one measurement in a fresh process and return its report.

    The peak resident memory is the high water mark of a process. Measuring
    several runs in one process would report the same number for all of
    them, and only the first measurement would be attributable to the run
    it describes. Every measurement therefore gets a process of its own.
    """
    work = Path(options['work'])
    work.mkdir(parents=True, exist_ok=True)
    report_path = work / f'child-{kind}-{os.getpid()}.json'
    command = [sys.executable, str(Path(__file__).resolve()),
               f'--internal-{kind}', '--out', str(report_path)]
    for key, value in options.items():
        if key in ('work', 'out'):
            continue
        command.extend([f'--{key.replace("_", "-")}', str(value)])
    result = subprocess.run(command, capture_output=True, text=True,
                            env=_child_environment(), cwd=str(REPO_ROOT))
    if not report_path.is_file():
        raise SystemExit('the measurement process produced no report:\n'
                         + (result.stderr or result.stdout)[-4000:])
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise SystemExit('the measurement process failed:\n'
                         + (result.stderr or result.stdout)[-4000:])
    return report


def _places_file(work: Path, places) -> Path:
    """Write the place pool the measurement uses, for the child to read."""
    path = Path(work) / 'places.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(places or PLACES, ensure_ascii=False),
                    encoding='utf-8')
    return path


def measure(rows: int, master, pack: Path, work: Path,
            batch_size: int, label: str, places=None) -> dict:
    """Run one full job in a fresh process and measure it.

    The checkpoint is kept on purpose: it is the plaintext customer shard
    the runner normally deletes, and its size is one of the numbers the
    benchmark has to report.
    """
    work = Path(work)
    report = _run_in_child('measure', {
        'rows': rows,
        'pack': str(pack),
        'catalogue': str(master.db_path),
        'approval-manifest': str(master.manifest_path),
        'approval-key': str(master.key_path),
        'batch-size': batch_size,
        'label': label,
        'work': str(work),
        'places-file': str(_places_file(work, places)),
    })
    _require_matched(report)
    return report


def _measure_in_process(rows: int, master, pack: Path, work: Path,
                        batch_size: int, label: str, places=None) -> dict:
    """The measurement itself, in a process that does nothing else."""
    source = work / f'input-{rows}.csv'
    output = work / f'run-{rows}'
    if output.exists():
        shutil.rmtree(output)
    write_source(source, rows, places)
    started = time.perf_counter()
    counts = run_job(
        input_path=source,
        output_dir=output,
        geo_db=pack,
        hkp_db=master.db_path,
        input_options=_options(),
        batch_size=batch_size,
        allow_unverified_reference_data=True,
        keep_checkpoint=True,
        approval_manifest=master.manifest_path,
        approval_key=master.key_path,
    )
    elapsed = time.perf_counter() - started
    state = output / '.job-state'
    rss = peak_rss_bytes()
    checkpoint_bytes = tree_size(state)
    return {
        'label': label,
        'rows': rows,
        'pid': os.getpid(),
        'seconds': round(elapsed, 3),
        'records_per_second': round(rows / elapsed, 1) if elapsed else None,
        'batch_size': batch_size,
        'status_counts': counts,
        'peak_rss_bytes': rss,
        'peak_rss_mib': round(rss / 1024 / 1024, 1),
        'checkpoint_bytes': checkpoint_bytes,
        'checkpoint_mib': round(checkpoint_bytes / 1024 / 1024, 2),
        'export_bytes': tree_size(output) - checkpoint_bytes,
        'pack_bytes': Path(pack).stat().st_size,
        'catalogue_bytes': Path(master.db_path).stat().st_size,
        'output_dir': str(output),
    }


def _require_matched(report: dict) -> None:
    """Refuse a measurement that matched nothing.

    A run in which no record was matched did not exercise the path a
    production run takes, so its throughput describes work that never
    happens. Such a number must never be reported as a measurement.
    """
    counts = report.get('status_counts') or {}
    if not counts.get('MATCHED', 0):
        raise SystemExit(
            'the measured run matched no record, so its throughput describes '
            f'a path a production run never takes: {counts!r}')


def measure_resume(rows: int, master, pack: Path, work: Path,
                   batch_size: int, pause_batches: int, places=None) -> dict:
    """Interrupt a job and resume it, measuring the restart cost."""
    work = Path(work)
    return _run_in_child('resume', {
        'rows': rows,
        'pack': str(pack),
        'catalogue': str(master.db_path),
        'approval-manifest': str(master.manifest_path),
        'approval-key': str(master.key_path),
        'batch-size': batch_size,
        'pause-batches': pause_batches,
        'work': str(work),
        'places-file': str(_places_file(work, places)),
    })


def _measure_resume_in_process(rows: int, master, pack: Path, work: Path,
                               batch_size: int, pause_batches: int,
                               places=None) -> dict:
    """The interrupt and resume measurement, in a process of its own."""
    source = work / f'input-{rows}.csv'
    output = work / f'resume-{rows}'
    if output.exists():
        shutil.rmtree(output)
    if not source.exists():
        write_source(source, rows, places)
    started = time.perf_counter()
    first = run_job(
        input_path=source, output_dir=output, geo_db=pack, hkp_db=master.db_path,
        input_options=_options(), batch_size=batch_size,
        max_batches=pause_batches, allow_unverified_reference_data=True,
        keep_checkpoint=True,
        approval_manifest=master.manifest_path, approval_key=master.key_path,
    )
    first_elapsed = time.perf_counter() - started
    resumed = time.perf_counter()
    counts = resume_job(output, verify_shards=True)
    resume_elapsed = time.perf_counter() - resumed
    total = time.perf_counter() - started
    return {
        'label': 'resume',
        'rows': rows,
        'pid': os.getpid(),
        'batch_size': batch_size,
        'pause_batches': pause_batches,
        'first_phase_seconds': round(first_elapsed, 3),
        'resume_phase_seconds': round(resume_elapsed, 3),
        'total_seconds': round(total, 3),
        'resume_overhead_ratio': round(resume_elapsed / max(total - resume_elapsed, 1e-9), 3),
        'status_counts': counts,
        'first_status': first,
        'checkpoint_bytes': tree_size(output / '.job-state'),
        'peak_rss_bytes': peak_rss_bytes(),
        'peak_rss_mib': round(peak_rss_bytes() / 1024 / 1024, 1),
        'peak_rss_scope': 'the interrupt and resume run, in one process',
        'pack_bytes': Path(pack).stat().st_size,
        'catalogue_bytes': Path(master.db_path).stat().st_size,
    }


def catalogue_codes(catalogue: Path) -> set:
    """The two letter destination codes the catalogue issues."""
    from world_address_engine.sqlite_util import open_db
    with open_db(Path(catalogue)) as conn:
        rows = conn.execute(
            "SELECT code FROM destinations WHERE code_scheme='HKP_DESTINATION_2' "
            "AND profile='HKP_DESTINATION_2' AND approval_status='APPROVED'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def street_evidence_violations(pack: Path, places=None) -> list[dict]:
    """The countries a synthetic street name would wrongly contribute.

    Every synthetic address has to resolve to the country of its own place
    and to nothing else. A street name that carries a place name of its own
    -- "Nanjing Road" carries a city -- would make the row measure a
    different workload, and could even resolve to the street's country.

    The test is comparative: the address is resolved with the street and
    without it, and the street is a problem when it adds a country the
    address on its own does not mention. A place that merely shares a name
    with the country -- the village "Japan" in Indonesia -- is already
    mentioned by the country name and is not the street's doing.
    """
    from world_address_engine.matching.normalize import normalize_address
    from world_address_engine.matching.retrieve import retrieve_candidates

    def countries(address):
        return {c.destination_id for c in
                retrieve_candidates(pack, normalize_address(address), None)}

    violations = []
    for place in (places or PLACES):
        country = HKP_TO_ISO.get(place[5], place[5])
        bare_en = f'{place[0]}, {place[3]}'
        bare_han = f'{place[1]}, {place[4]}'
        for bare in (bare_en, bare_han):
            if country not in countries(bare):
                violations.append({'address': bare, 'countries': [],
                                   'problem': 'the place does not resolve to '
                                              'its own country'})
        for street in STREET_EN:
            address = f'{street}, {bare_en}'
            extra = countries(address) - countries(bare_en)
            if extra:
                violations.append({'address': address, 'countries': sorted(extra),
                                   'problem': 'the street name adds a country'})
        for streets in (STREET_TC, STREET_SC):
            for street in streets:
                address = f'{street} 12 號, {bare_han}'
                extra = countries(address) - countries(bare_han)
                if extra:
                    violations.append({'address': address,
                                       'countries': sorted(extra),
                                       'problem': 'the street name adds a country'})
    return violations


def coherent_places(catalogue: Path):
    """Keep only the places whose destination the catalogue really issues.

    A benchmark row that the catalogue cannot answer would be measured as
    a review case instead of a matched one, so the generated addresses
    stay coherent with the master that is actually in use.
    """
    codes = catalogue_codes(Path(catalogue))
    kept = [row for row in PLACES if row[5] in codes]
    dropped = [row[0] for row in PLACES if row[5] not in codes]
    return kept, dropped


def build_fixture_master(directory: Path):
    """The signed test master, so the run never needs the network.

    The master carries the approval manifest and the key that sign it.
    Without them no destination code may be asserted, and the run would
    measure the review path instead of the matching path.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tests.hkp_master_fixture import build_master
    return build_master(directory)


def _run_internal(args) -> int:
    """The measurement process: one run, one report, one process."""
    master = _master_from_paths(args.catalogue, args.approval_manifest,
                                args.approval_key)
    places = json.loads(Path(args.places_file).read_text(encoding='utf-8'))
    # `--rows` is repeatable in the public interface, so the child always
    # receives exactly one value, in a list.
    rows = args.rows[0] if isinstance(args.rows, list) else args.rows
    if args.internal_resume:
        report = _measure_resume_in_process(
            rows, master, Path(args.pack), Path(args.work_dir),
            args.batch_size, args.pause_batches, places)
    else:
        report = _measure_in_process(
            rows, master, Path(args.pack), Path(args.work_dir),
            args.batch_size, args.label, places)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0


class _Master:
    """A catalogue, the approval that governs it and where they live."""

    def __init__(self, db_path: Path, manifest_path: Path, key_path: Path, approval):
        self.db_path = Path(db_path)
        self.manifest_path = Path(manifest_path)
        self.key_path = Path(key_path)
        self.approval = approval


def _master_from_paths(catalogue: Path, manifest: Path, key: Path) -> _Master:
    """Bind a catalogue to the approval that governs it."""
    from world_address_engine.hkp.approval import load_approval

    catalogue, manifest, key = Path(catalogue), Path(manifest), Path(key)
    for path, label in ((catalogue, 'catalogue'),
                        (manifest, 'approval manifest'),
                        (key, 'approval key')):
        if not path.is_file():
            raise SystemExit(f'{label} not found: {path}')
    approval = load_approval(manifest, key, catalogue)
    return _Master(catalogue, manifest, key, approval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, action='append', default=None,
                        help='row count to measure; repeatable')
    parser.add_argument('--pack', type=Path, default=None,
                        help='installed reference pack (pack.db)')
    parser.add_argument('--catalogue', type=Path, default=None,
                        help='HKP catalogue database (defaults to the fixture master)')
    parser.add_argument('--approval-manifest', type=Path, default=None,
                        help='the signed approval manifest that governs the catalogue')
    parser.add_argument('--approval-key', type=Path, default=None,
                        help='the key that verifies the approval manifest')
    parser.add_argument('--work-dir', type=Path, default=REPO_ROOT / '.tmp' / 'bench')
    parser.add_argument('--batch-size', type=int, default=10_000)
    parser.add_argument('--resume-rows', type=int, default=0,
                        help='also measure interrupt+resume at this row count')
    parser.add_argument('--pause-batches', type=int, default=2)
    parser.add_argument('--out', type=Path, default=None,
                        help='write the measurements to this JSON file')
    parser.add_argument('--keep-inputs', action='store_true')
    parser.add_argument('--internal-measure', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--internal-resume', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--places-file', type=Path, default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument('--label', default='', help=argparse.SUPPRESS)
    parser.add_argument('--skip-street-check', action='store_true',
                        help='do not verify that the synthetic street names carry '
                             'no place evidence')
    args = parser.parse_args(argv)

    if args.internal_measure or args.internal_resume:
        return _run_internal(args)

    sizes = args.rows or [10_000]
    pack = args.pack
    if pack is None:
        raise SystemExit('--pack is required: measure against a real reference pack')
    if not pack.is_file():
        raise SystemExit(f'reference pack not found: {pack}')
    work = args.work_dir
    work.mkdir(parents=True, exist_ok=True)
    if args.catalogue is None and (args.approval_manifest or args.approval_key):
        raise SystemExit('--approval-manifest and --approval-key need --catalogue')
    if args.catalogue is None:
        master = build_fixture_master(work / 'fixture-master')
    else:
        if args.approval_manifest is None or args.approval_key is None:
            raise SystemExit(
                'a catalogue without its signed approval can assert no code, '
                'so supply --approval-manifest and --approval-key')
        master = _master_from_paths(args.catalogue, args.approval_manifest,
                                    args.approval_key)

    places, dropped = coherent_places(master.db_path)
    if dropped:
        print(f'places not issued by this catalogue, excluded: {dropped}',
              file=sys.stderr)
    if not places:
        raise SystemExit('the catalogue issues none of the benchmark places')
    if not args.skip_street_check:
        violations = street_evidence_violations(Path(pack), places)
        if violations:
            for violation in violations[:10]:
                print(f'street name carries place evidence: {violation}',
                      file=sys.stderr)
            raise SystemExit(
                f'{len(violations)} synthetic addresses resolve to a country '
                'other than their own; the street names have to be evidence '
                'free before this tool may measure anything')
        print(f'street names carry no place evidence ({len(places)} places '
              f'x {len(STREET_EN) + len(STREET_TC) + len(STREET_SC)} names)')

    results = []
    for rows in sizes:
        result = measure(rows, master, Path(pack), work,
                         args.batch_size, f'{rows} rows', places)
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)
    if args.resume_rows:
        result = measure_resume(args.resume_rows, master, Path(pack), work,
                                args.batch_size, args.pause_batches, places)
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)

    payload = {
        'pack': str(pack),
        'pack_bytes': Path(pack).stat().st_size,
        'catalogue': str(master.db_path),
        'catalogue_bytes': Path(master.db_path).stat().st_size,
        'approval_manifest': str(master.manifest_path),
        'approval_scope': master.approval.scope,
        'places': len(places),
        'places_excluded': dropped,
        'python': sys.version,
        'platform': sys.platform,
        'results': results,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(f'wrote {args.out}')
    if not args.keep_inputs:
        for rows in sizes:
            stale = work / f'input-{rows}.csv'
            if stale.exists():
                stale.unlink()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
