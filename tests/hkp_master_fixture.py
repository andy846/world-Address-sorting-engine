"""A broader *test-only* HKP destination master.

This is a synthetic fixture for automated tests. It is NOT the verified
Hongkong Post master and must never be presented as one: the codes and names
below are placeholders that exercise the mapping and conflict logic.

The fixture is signed with a `TEST_FIXTURE` scope key, so it can exercise the
code-resolution path but can never authorise a production run.
"""

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from world_address_engine.hkp.approval import (
    SCOPE_TEST_FIXTURE,
    CatalogueApproval,
    load_approval,
    sign_manifest,
)
from world_address_engine.hkp.catalogue import import_hkp_catalogue

SOURCE_URL = 'https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf'
SOURCE_DOC_VERSION = 'test-fixture-2026-10-23'
SOURCE_SECTION = 'test-fixture-not-official'
# Stand-in bytes for the official document. A real master must carry the
# SHA-256 of the genuine Hongkong Post document it was taken from.
FIXTURE_SOURCE_DOCUMENT = b'test fixture stand-in; not an official Hongkong Post document'
SOURCE_SHA256 = hashlib.sha256(FIXTURE_SOURCE_DOCUMENT).hexdigest()
FIXTURE_KEY = b'test-fixture-approval-key-0123456789abcdef'

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


@dataclass(frozen=True)
class ApprovedMaster:
    """A built, signed test master and the approval that unlocks it."""

    db_path: Path
    csv_path: Path
    manifest_path: Path
    key_path: Path
    approval: CatalogueApproval


def build_master(directory: Path, *, scope: str = SCOPE_TEST_FIXTURE,
                 key: bytes = FIXTURE_KEY, countries=None) -> ApprovedMaster:
    """Write, import and sign the test master."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / 'hkp_test_master.csv'
    fields = ['destination_id', 'code_scheme', 'code', 'name_en', 'name_zh_hant', 'name_zh_hans',
              'source_url', 'source_doc_version', 'source_section', 'source_checksum',
              'approval_status', 'profile', 'date_verified']
    with csv_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for destination_id, iso, postal, name_en, name_tc, name_sc in (countries or COUNTRIES):
            common = dict(destination_id=destination_id, name_en=name_en, name_zh_hant=name_tc,
                          name_zh_hans=name_sc, source_url=SOURCE_URL,
                          source_doc_version=SOURCE_DOC_VERSION,
                          source_section=SOURCE_SECTION,
                          source_checksum=SOURCE_SHA256,
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
    approval_payload = {
        'approval_id': 'test-fixture-approval-2026-10-23',
        'scope': scope,
        'catalogue_version': 'test-fixture-2026-10-23',
        'csv_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        'row_count': len(countries or COUNTRIES) * 2,
        'catalogue_db_sha256': hashlib.sha256(db_path.read_bytes()).hexdigest(),
        'approved_destinations': [row[0] for row in (countries or COUNTRIES)],
        'approved_sources': [{
            'source_url': SOURCE_URL,
            'source_doc_version': SOURCE_DOC_VERSION,
            'source_section': SOURCE_SECTION,
            'source_sha256': SOURCE_SHA256,
        }],
    }
    signed = sign_manifest(approval_payload, key)
    manifest_path = directory / 'hkp_test_master.approval.json'
    manifest_path.write_text(json.dumps(signed, ensure_ascii=False, indent=2), encoding='utf-8')
    key_path = directory / 'hkp_test_master.approval.key'
    key_path.write_bytes(key)
    approval = load_approval(manifest_path, key_path, db_path)
    return ApprovedMaster(db_path=db_path, csv_path=csv_path,
                          manifest_path=manifest_path, key_path=key_path,
                          approval=approval)
