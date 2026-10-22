"""A broader *test-only* HKP destination master.

This is a synthetic fixture for automated tests. It is NOT the verified
Hongkong Post master and must never be presented as one: the codes and names
below are placeholders that exercise the mapping and conflict logic.
"""

import csv
import hashlib
import json
from pathlib import Path

from world_address_engine.hkp.catalogue import import_hkp_catalogue

SOURCE_URL = 'https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf'

# destination_id, ISO alpha-2, HKP two-letter code, name_en, name_zh_hant, name_zh_hans
COUNTRIES = [
    ('argentina', 'AR', 'AR', 'Argentina', '阿根廷', '阿根廷'),
    ('australia', 'AU', 'AU', 'Australia', '澳大利亞', '澳大利亚'),
    ('austria', 'AT', 'AT', 'Austria', '奧地利', '奥地利'),
    ('belgium', 'BE', 'BE', 'Belgium', '比利時', '比利时'),
    ('brazil', 'BR', 'BR', 'Brazil', '巴西', '巴西'),
    ('canada', 'CA', 'CA', 'Canada', '加拿大', '加拿大'),
    ('china', 'CN', 'CN', 'China', '中國', '中国'),
    ('denmark', 'DK', 'DK', 'Denmark', '丹麥', '丹麦'),
    ('france', 'FR', 'FR', 'France', '法國', '法国'),
    ('germany', 'DE', 'DE', 'Germany', '德國', '德国'),
    ('guam', 'GU', 'GU', 'Guam', '關島', '关岛'),
    ('hong-kong', 'HK', 'HK', 'Hong Kong', '香港', '香港'),
    ('india', 'IN', 'IN', 'India', '印度', '印度'),
    ('indonesia', 'ID', 'ID', 'Indonesia', '印尼', '印度尼西亚'),
    ('ireland', 'IE', 'IE', 'Ireland', '愛爾蘭', '爱尔兰'),
    ('italy', 'IT', 'IT', 'Italy', '意大利', '意大利'),
    ('japan', 'JP', 'JP', 'Japan', '日本', '日本'),
    ('macau', 'MO', 'MO', 'Macau', '澳門', '澳门'),
    ('malaysia', 'MY', 'MY', 'Malaysia', '馬來西亞', '马来西亚'),
    ('netherlands', 'NL', 'NL', 'Netherlands', '荷蘭', '荷兰'),
    ('new-zealand', 'NZ', 'NZ', 'New Zealand', '新西蘭', '新西兰'),
    ('norway', 'NO', 'NO', 'Norway', '挪威', '挪威'),
    ('philippines', 'PH', 'PH', 'Philippines', '菲律賓', '菲律宾'),
    ('puerto-rico', 'PR', 'PR', 'Puerto Rico', '波多黎各', '波多黎各'),
    ('singapore', 'SG', 'SG', 'Singapore', '新加坡', '新加坡'),
    ('south-korea', 'KR', 'KR', 'South Korea', '南韓', '韩国'),
    ('spain', 'ES', 'ES', 'Spain', '西班牙', '西班牙'),
    ('sweden', 'SE', 'SE', 'Sweden', '瑞典', '瑞典'),
    ('switzerland', 'CH', 'CH', 'Switzerland', '瑞士', '瑞士'),
    ('taiwan', 'TW', 'TW', 'Taiwan', '台灣', '台湾'),
    ('thailand', 'TH', 'TH', 'Thailand', '泰國', '泰国'),
    ('timor-leste', 'TL', 'TP', 'Timor-Leste', '東帝汶', '东帝汶'),
    ('united-arab-emirates', 'AE', 'AE', 'United Arab Emirates', '阿拉伯聯合酋長國', '阿联酋'),
    ('united-kingdom', 'GB', 'GB', 'United Kingdom', '英國', '英国'),
    ('united-states', 'US', 'US', 'United States', '美國', '美国'),
    ('vietnam', 'VN', 'VN', 'Vietnam', '越南', '越南'),
]


def build_master(directory: Path) -> Path:
    """Write and import the test master, returning the SQLite lookup path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / 'hkp_test_master.csv'
    fields = ['destination_id', 'code_scheme', 'code', 'name_en', 'name_zh_hant', 'name_zh_hans',
              'source_url', 'source_doc_version', 'source_section', 'source_checksum',
              'approval_status', 'profile', 'date_verified']
    with csv_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for destination_id, iso, postal, name_en, name_tc, name_sc in COUNTRIES:
            common = dict(destination_id=destination_id, name_en=name_en, name_zh_hant=name_tc,
                          name_zh_hans=name_sc, source_url=SOURCE_URL,
                          source_doc_version='test-fixture-2026-10-23',
                          source_section='test-fixture-not-official',
                          source_checksum='test-fixture-not-official',
                          approval_status='APPROVED', date_verified='2026-10-23')
            writer.writerow(dict(common, code_scheme='HKP_DESTINATION_2',
                                 profile='HKP_DESTINATION_2', code=postal))
            writer.writerow(dict(common, code_scheme='ISO_ALPHA2', profile='ISO', code=iso))
    manifest = directory / 'hkp_test_master.json'
    manifest.write_text(json.dumps({
        'catalogue_version': 'test-fixture-2026-10-23',
        'csv_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }), encoding='utf-8')
    db_path = directory / 'hkp_test_master.db'
    import_hkp_catalogue(csv_path, manifest, db_path)
    return db_path
