import sqlite3
from pathlib import Path
from world_address_engine.models import AddressRecord
from world_address_engine.matching.classify import classify_record
from tests.hkp_master_fixture import build_master
from tests.unit.test_retrieve import geo

HKP_SOURCE = 'https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf'

FIXTURE_COUNTRIES = [
    ('india', 'IN', 'IN', 'India', '印度', '印度'),
    ('japan', 'JP', 'JP', 'Japan', '日本', '日本'),
    ('uk', 'GB', 'GB', 'United Kingdom', '英國', '英国'),
    ('us', 'US', 'US', 'United States', '美國', '美国'),
    ('canada', 'CA', 'CA', 'Canada', '加拿大', '加拿大'),
    ('macau', 'MO', 'MO', 'Macau', '澳門', '澳门'),
    ('china', 'CN', 'CN', 'China', '中國', '中国'),
    ('timor-leste', 'TL', 'TP', 'Timor-Leste', '東帝汶', '东帝汶'),
    ('singapore', 'SG', 'SG', 'Singapore', '新加坡', '新加坡'),
]


def hkp(tmp_path):
    """A signed test master. The approval is a TEST_FIXTURE scope."""
    return build_master(tmp_path, countries=FIXTURE_COUNTRIES)


def classify(record, geo_db, master):
    return classify_record(record, geo_db, master.db_path, master.approval)


def _insert_row(db, destination_id, code, scheme, profile):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO destinations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (destination_id, scheme, code, 'Extra', '額外', '额外', HKP_SOURCE,
                  'fixture', 'fixture-only', 'fixture-only', 'APPROVED', profile, '2026-10-23'))
    conn.commit()
    conn.close()


def _set_code(db, destination_id, code):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE destinations SET code=? WHERE code_scheme='HKP_DESTINATION_2' AND destination_id=?",
                 (code, destination_id))
    conn.commit()
    conn.close()


def rec(text, hint=None):
    return AddressRecord(1, 'sample.csv', None, '0001', {'Address': text}, text, hint)


def test_london_road_mumbai_india_is_in(tmp_path):
    result = classify(rec('London Road, Mumbai, India'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'IN'


def test_springfield_does_not_guess(tmp_path):
    result = classify(rec('Main Street, Springfield'), geo(tmp_path), hkp(tmp_path))
    assert result.status in ('REVIEW_AMBIGUOUS', 'UNKNOWN') and result.hkp_code is None


def test_conflicting_explicit_countries_review(tmp_path):
    result = classify(rec('Tokyo\nJapan\nUnited Kingdom'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'REVIEW_CONFLICT' and result.hkp_code is None


def test_verified_macau_is_mo_not_cn(tmp_path):
    result = classify(rec('Macau'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'MO'


def test_timor_leste_is_tp_not_tl(tmp_path):
    result = classify(rec('Timor-Leste'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'TP'


def test_unapproved_hkp_code_never_asserted(tmp_path):
    result = classify(rec('Utopia'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'UNKNOWN' and result.hkp_code is None


def test_unsupported_script_has_review_reason(tmp_path):
    result = classify(rec('Москва'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'UNKNOWN' and 'UNSUPPORTED_LANGUAGE' in result.reason


def test_bad_input_record_returns_input_error(tmp_path):
    r = AddressRecord(1, 'bad.csv', None, '001', {}, 'x', None, 'UNDECODABLE_TEXT')
    result = classify(r, geo(tmp_path), hkp(tmp_path))
    assert result.status == 'INPUT_ERROR' and result.hkp_code is None


def test_structured_iso_two_letter_hint_is_explicit(tmp_path):
    result = classify(rec('Unknown Recipient\nUnknown Street', hint='JP'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'JP'


def test_country_entity_name_is_matched(tmp_path):
    result = classify(rec('India'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'IN'


def test_city_and_state_are_matched(tmp_path):
    result = classify(rec('Springfield, Illinois'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'US'


def test_lone_city_token_is_not_asserted(tmp_path):
    result = classify(rec('Tokyo'), geo(tmp_path), hkp(tmp_path))
    assert result.status in ('UNKNOWN', 'REVIEW_AMBIGUOUS') and result.hkp_code is None


def test_country_hint_conflicting_with_geography_is_review(tmp_path):
    result = classify(rec('Tokyo', 'US'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'REVIEW_CONFLICT' and result.hkp_code is None


def test_country_hint_agreeing_with_geography_is_matched(tmp_path):
    result = classify(rec('Springfield, Illinois', 'US'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'US'


def test_company_name_is_not_country_evidence(tmp_path):
    result = classify(rec('Jane Doe\nCHINA CONSTRUCTION LTD\n1 Main St, Springfield, US'),
                      geo(tmp_path), hkp(tmp_path))
    assert result.hkp_code != 'CN'
    assert result.status != 'MATCHED'


def test_company_name_does_not_hide_a_real_country_statement(tmp_path):
    result = classify(rec('Jane Doe\nCHINA CONSTRUCTION LTD\nShanghai, China'),
                      geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'CN'


def test_han_company_name_is_not_country_evidence(tmp_path):
    result = classify(rec('北京市\n中国银行'), geo(tmp_path), hkp(tmp_path))
    assert result.hkp_code != 'CN'


def test_han_country_statement_is_matched(tmp_path):
    result = classify(rec('中国北京市朝阳区建国路88号'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'CN'


def test_state_code_next_to_country_name_is_not_a_company_marker(tmp_path):
    result = classify(rec('Denver, CO 80202, United States'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'MATCHED' and result.hkp_code == 'US'


def test_geography_without_approved_hkp_row_is_review_code_mapping(tmp_path):
    result = classify(rec('France'), geo(tmp_path), hkp(tmp_path))
    assert result.status == 'REVIEW_CODE_MAPPING' and result.hkp_code is None


def test_iso_row_without_hkp_row_is_review_code_mapping(tmp_path):
    master = hkp(tmp_path)
    _insert_row(master.db_path, 'france', 'FR', 'ISO_ALPHA2', 'ISO')
    result = classify(rec('France'), geo(tmp_path), master)
    assert result.status == 'REVIEW_CODE_MAPPING' and result.hkp_code is None


def test_three_letter_hkp_code_is_never_emitted(tmp_path):
    master = hkp(tmp_path)
    _set_code(master.db_path, 'us', 'USA')
    result = classify(rec('United States'), geo(tmp_path), master)
    assert result.status == 'REVIEW_CODE_MAPPING' and result.hkp_code is None


def test_ambiguous_iso_crosswalk_is_not_used(tmp_path):
    master = hkp(tmp_path)
    # A second destination claims the same ISO code.
    _insert_row(master.db_path, 'china-alt', 'MO', 'ISO_ALPHA2', 'ISO')
    result = classify(rec('Macau'), geo(tmp_path), master)
    assert result.status == 'REVIEW_CODE_MAPPING' and result.hkp_code is None


def test_catalogue_without_an_approval_asserts_no_code(tmp_path):
    """The catalogue file alone can never authorise a destination code."""
    master = hkp(tmp_path)
    result = classify_record(rec('India'), geo(tmp_path), master.db_path)
    assert result.status == 'REVIEW_CODE_MAPPING' and result.hkp_code is None
