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
import shutil
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

STREET_EN = ['Main Street', 'Nanjing Road', '221B Baker Street', 'Park Avenue',
             'Rue de la Paix', 'Alexanderplatz', '5th Avenue', 'Kingsway',
             'Harbour Road', 'Station Road']
STREET_TC = ['中山北路', '南京東路', '解放大道', '人民路', '河堤路']
STREET_SC = ['中山北路', '南京东路', '解放大道', '人民路', '河堤路']


def synth_rows(total: int, places=None):
    """Yield (recipient, address, country_hint) triples."""
    pool = places or PLACES
    for index in range(total):
        city_en, city_tc, city_sc, country_en, country_tc, _code = \
            pool[index % len(pool)]
        style = index % 3
        if style == 0:
            street = STREET_EN[index % len(STREET_EN)]
            address = f'{street}, {city_en}, {country_en}'
        elif style == 1:
            street = STREET_TC[index % len(STREET_TC)]
            address = f'{city_tc}{street} {index % 999 + 1} 號, {city_tc}, {country_tc}'
        else:
            street = STREET_SC[index % len(STREET_SC)]
            address = f'{city_sc}{street} {index % 999 + 1} 号, {city_sc}, {country_tc}'
        yield f'Recipient {index % 997}', address, ''


def write_source(path: Path, total: int, places=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['NAME_ADDRESS_LINE1', 'NAME_ADDRESS_LINE2', 'Control no'])
        for index, (recipient, address, _hint) in enumerate(synth_rows(total, places), 1):
            writer.writerow([recipient, address, f'{index:09d}'])


def peak_rss_bytes() -> int:
    """Peak resident set size of this process, in bytes."""
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
    return 0


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


def measure(rows: int, pack: Path, catalogue: Path, work: Path,
            batch_size: int, label: str, places=None) -> dict:
    """Run one full job and measure it.

    The checkpoint is kept on purpose: it is the plaintext customer shard
    the runner normally deletes, and its size is one of the numbers the
    benchmark has to report.
    """
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
        hkp_db=catalogue,
        input_options=_options(),
        batch_size=batch_size,
        allow_unverified_reference_data=True,
        keep_checkpoint=True,
    )
    elapsed = time.perf_counter() - started
    state = output / '.job-state'
    rss = peak_rss_bytes()
    checkpoint_bytes = tree_size(state)
    return {
        'label': label,
        'rows': rows,
        'seconds': round(elapsed, 3),
        'records_per_second': round(rows / elapsed, 1) if elapsed else None,
        'batch_size': batch_size,
        'status_counts': counts,
        'peak_rss_bytes': rss,
        'peak_rss_mib': round(rss / 1024 / 1024, 1),
        'checkpoint_bytes': checkpoint_bytes,
        'checkpoint_mib': round(checkpoint_bytes / 1024 / 1024, 2),
        'export_bytes': tree_size(output) - checkpoint_bytes,
        'output_dir': str(output),
    }


def measure_resume(rows: int, pack: Path, catalogue: Path, work: Path,
                   batch_size: int, pause_batches: int, places=None) -> dict:
    """Interrupt a job and resume it, measuring the restart cost."""
    source = work / f'input-{rows}.csv'
    output = work / f'resume-{rows}'
    if output.exists():
        shutil.rmtree(output)
    if not source.exists():
        write_source(source, rows, places)
    started = time.perf_counter()
    first = run_job(
        input_path=source, output_dir=output, geo_db=pack, hkp_db=catalogue,
        input_options=_options(), batch_size=batch_size,
        max_batches=pause_batches, allow_unverified_reference_data=True,
        keep_checkpoint=True,
    )
    first_elapsed = time.perf_counter() - started
    resumed = time.perf_counter()
    counts = resume_job(output, verify_shards=True)
    resume_elapsed = time.perf_counter() - resumed
    total = time.perf_counter() - started
    return {
        'label': 'resume',
        'rows': rows,
        'batch_size': batch_size,
        'pause_batches': pause_batches,
        'first_phase_seconds': round(first_elapsed, 3),
        'resume_phase_seconds': round(resume_elapsed, 3),
        'total_seconds': round(total, 3),
        'resume_overhead_ratio': round(resume_elapsed / max(total - resume_elapsed, 1e-9), 3),
        'status_counts': counts,
        'first_status': first,
        'checkpoint_bytes': tree_size(output / '.job-state'),
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


def build_fixture_catalogue(directory: Path) -> Path:
    """The signed test master, so the run never needs the network."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tests.hkp_master_fixture import build_master
    master = build_master(directory)
    return master.db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, action='append', default=None,
                        help='row count to measure; repeatable')
    parser.add_argument('--pack', type=Path, default=None,
                        help='installed reference pack (pack.db)')
    parser.add_argument('--catalogue', type=Path, default=None,
                        help='HKP catalogue database (defaults to the fixture master)')
    parser.add_argument('--work-dir', type=Path, default=REPO_ROOT / '.tmp' / 'bench')
    parser.add_argument('--batch-size', type=int, default=10_000)
    parser.add_argument('--resume-rows', type=int, default=0,
                        help='also measure interrupt+resume at this row count')
    parser.add_argument('--pause-batches', type=int, default=2)
    parser.add_argument('--out', type=Path, default=None,
                        help='write the measurements to this JSON file')
    parser.add_argument('--keep-inputs', action='store_true')
    args = parser.parse_args(argv)

    sizes = args.rows or [10_000]
    pack = args.pack
    if pack is None:
        raise SystemExit('--pack is required: measure against a real reference pack')
    if not pack.is_file():
        raise SystemExit(f'reference pack not found: {pack}')
    work = args.work_dir
    work.mkdir(parents=True, exist_ok=True)
    catalogue = args.catalogue
    if catalogue is None:
        catalogue = build_fixture_catalogue(work / 'fixture-master')
    if not Path(catalogue).is_file():
        raise SystemExit(f'catalogue not found: {catalogue}')

    places, dropped = coherent_places(catalogue)
    if dropped:
        print(f'places not issued by this catalogue, excluded: {dropped}',
              file=sys.stderr)
    if not places:
        raise SystemExit('the catalogue issues none of the benchmark places')

    results = []
    for rows in sizes:
        result = measure(rows, Path(pack), Path(catalogue), work,
                         args.batch_size, f'{rows} rows', places)
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)
    if args.resume_rows:
        result = measure_resume(args.resume_rows, Path(pack), Path(catalogue),
                                work, args.batch_size, args.pause_batches,
                                places)
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)

    payload = {
        'pack': str(pack),
        'pack_bytes': Path(pack).stat().st_size,
        'catalogue': str(catalogue),
        'catalogue_bytes': Path(catalogue).stat().st_size,
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
