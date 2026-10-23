"""Public-safe regressions on the local k2 packs; HKP is TEST_FIXTURE only."""

from pathlib import Path

import pytest

from tests.hkp_master_fixture import COUNTRIES, build_master
from tests.unit.test_classify import classify, rec


@pytest.fixture(scope='module')
def master(tmp_path_factory):
    return build_master(tmp_path_factory.mktemp('nested-real-master'), countries=COUNTRIES + [
        ('papua-new-guinea', 'PG', 'PG', 'Papua New Guinea', '', ''),
        ('guinea', 'GN', 'GN', 'Guinea', '', ''),
        ('georgia', 'GE', 'GE', 'Georgia', '喬治亞', '格鲁吉亚'),
    ])


@pytest.fixture(params=['compact', 'extended'])
def pack(request):
    path = Path(__file__).resolve().parents[2] / 'packs' / (
        f'geonames-{request.param}-global-2026-10-22-k2/pack.db')
    if not path.is_file():
        pytest.skip('local k2 pack is not installed')
    return path


def test_northern_ireland_never_asserts_ireland(pack, master):
    result = classify(rec('Northern Ireland'), pack, master)
    assert result.hkp_code != 'IE'
    assert result.status != 'MATCHED' or result.hkp_code == 'GB'


@pytest.mark.parametrize('text', [
    'Papua New Guinea, Guinea', 'Papua New Guinea Ltd, Guinea',
    'Guinea, Papua New Guinea',
])
def test_explicit_countries_keep_their_independent_occurrences(text, pack, master):
    result = classify(rec(text), pack, master)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


@pytest.mark.parametrize('text', [
    'Italy, Brazil',
    'Italy, United States',
    'China, United States',
])
def test_same_spelled_localities_never_erase_explicit_country_conflicts(
        text, pack, master):
    result = classify(rec(text), pack, master)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


@pytest.mark.parametrize('text,code', [
    ('Town of China', 'CN'),
    ('Lubok China', 'CN'),
    ('La Guinea', 'GN'),
])
def test_real_pack_never_asserts_a_country_inside_a_longer_place(
        text, code, pack, master):
    result = classify(rec(text), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code != code


@pytest.mark.parametrize('text,code', [
    ('Air China', 'CN'),
    ('Air India', 'IN'),
    ('Made in China', 'CN'),
    ('Huawei China', 'CN'),
    ('Samsung India', 'IN'),
    ('Designed in China', 'CN'),
    ('Apple China', 'CN'),
])
def test_real_pack_does_not_treat_company_or_brand_text_as_a_destination(
        text, code, pack, master):
    result = classify(rec(text), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code is None


@pytest.mark.parametrize('text', [
    '华为中国', '華為中國', 'Apple中国', '中国移动', '中國移動', '中国银行',
])
def test_real_pack_does_not_treat_han_or_mixed_brand_text_as_a_destination(
        text, pack, master):
    result = classify(rec(text), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code is None


@pytest.mark.parametrize('text,code', [
    ('India香港', 'IN'),
    ('香港India', 'IN'),
])
def test_real_pack_does_not_break_words_at_a_script_boundary(
        text, code, pack, master):
    result = classify(rec(text), pack, master)
    assert result.hkp_code != code


def test_real_pack_rejects_an_unlisted_letter_system(pack, master):
    result = classify(rec('Indiaთ'), pack, master)
    assert result.status == 'UNKNOWN'
    assert result.reason == 'UNSUPPORTED_LANGUAGE'
    assert result.hkp_code is None


@pytest.mark.parametrize('text', [
    'India\u064e', 'India\u0902', 'India\u200d',
])
def test_real_pack_rejects_combining_marks_and_format_controls(text, pack, master):
    result = classify(rec(text), pack, master)
    assert (result.status, result.reason) == ('UNKNOWN', 'UNSUPPORTED_LANGUAGE')
    assert result.hkp_code is None


@pytest.mark.parametrize('text', [
    '\uff29\uff4e\uff44\uff49\uff41',
    '\U0001d43c\U0001d45b\U0001d451\U0001d456\U0001d44e',
])
def test_real_pack_accepts_nfkc_latin(text, pack, master):
    result = classify(rec(text), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', 'IN')


def test_real_pack_state_of_georgia_is_not_the_country(pack, master):
    result = classify(rec('State of Georgia'), pack, master)
    assert result.hkp_code != 'GE'
    assert result.status != 'MATCHED' or result.hkp_code == 'US'


def test_real_pack_state_of_georgia_with_parent_is_the_parent(pack, master):
    result = classify(rec('State of Georgia, United States'), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', 'US')


@pytest.mark.parametrize('text,code', [
    ('觀星路 38 號, 聖保羅, 巴西', 'BR'),
    ('聽雨路 110 號, 杜拜, 阿拉伯聯合酋長國', 'AE'),
])
def test_long_han_names_do_not_add_foreign_fragment_evidence(text, code, pack, master):
    result = classify(rec(text), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', code)


def test_bare_admin_phrase_never_asserts_a_country_from_its_fragments(pack, master):
    result = classify(rec('New Brunswick'), pack, master)
    assert result.status in ('UNKNOWN', 'REVIEW_AMBIGUOUS')
    assert result.hkp_code is None


@pytest.mark.parametrize('text,code', [
    ('New Brunswick, Canada', 'CA'),
    ('New Brunswick, New Jersey, United States', 'US'),
])
def test_explicit_context_disambiguates_new_brunswick(text, code, pack, master):
    result = classify(rec(text), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', code)


@pytest.mark.parametrize('text,code', [
    ('Mumbai India', 'IN'),
    ('Tokyo Japan', 'JP'),
    ('London United Kingdom', 'GB'),
    ('New Delhi India', 'IN'),
    ('NY United States', 'US'),
])
def test_common_comma_less_city_country_addresses_are_matched(
        text, code, pack, master):
    result = classify(rec(text), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', code)


def test_comma_less_country_pair_remains_an_explicit_conflict(pack, master):
    result = classify(rec('India China'), pack, master)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


@pytest.mark.parametrize('separator', ['/', ' (', '、', ', '])
def test_city_country_punctuation_is_context_equivalent(separator, pack, master):
    closing = ')' if separator == ' (' else ''
    result = classify(rec('Mumbai' + separator + 'India' + closing), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', 'IN')


@pytest.mark.parametrize('text', ['中国北京', '北京中国'])
def test_han_country_and_recognized_city_form_an_address_chain(text, pack, master):
    result = classify(rec(text), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', 'CN')


@pytest.mark.parametrize('text', ['中国上海', '中国北京', '北京中国', '上海中国'])
def test_han_country_and_city_are_matched_in_either_order(text, pack, master):
    """A combined Han alias must not hide the country and city it contains."""
    result = classify(rec(text), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', 'CN')


@pytest.mark.parametrize('text', [
    'China Mobile', 'Mobile China', 'China Southern', 'China Eastern',
])
def test_real_pack_never_asserts_a_country_from_brand_text(text, pack, master):
    """A country name that modifies a foreign place is a brand, not a destination."""
    result = classify(rec(text), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code is None


@pytest.mark.parametrize('text', [
    'China, Mobile', 'Mobile, China', 'China; Mobile',
])
def test_real_pack_never_erases_a_country_for_a_village_of_the_same_name(
        text, pack, master):
    """A village that shares a country name does not erase the country."""
    result = classify(rec(text), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code != 'US'


def test_real_pack_never_asserts_a_village_country_from_official_name_text(
        pack, master):
    result = classify(rec('Republic of China'), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code != 'US'


@pytest.mark.parametrize('text', ['France Target', 'Target France'])
def test_real_pack_does_not_assert_a_country_from_a_subdivision_brand(
        text, pack, master):
    """A sub-division of a country is not evidence that the text names it."""
    result = classify(rec(text), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code != 'FR'


@pytest.mark.parametrize('text', ['中国東京', '東京中国', '日本上海', '上海日本'])
def test_real_pack_does_not_assert_a_country_next_to_a_foreign_han_city(
        text, pack, master):
    result = classify(rec(text), pack, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code is None


@pytest.mark.xfail(reason='the pack has no Simplified Chinese alias for the '
                   'Hong Kong SAR, only the Traditional one', strict=False)
def test_real_pack_matches_the_hong_kong_sar_in_simplified_chinese(pack, master):
    """Records the gap that the pack keeps the alias in Traditional Chinese."""
    result = classify(rec('中华人民共和国香港特别行政区'), pack, master)
    assert result.hkp_code == 'HK'


@pytest.mark.parametrize('text', [
    'Bearna Ireland', 'Castlerea Ireland', 'Tobercurry Ireland',
    'Bunclody Ireland', 'Bundoran Ireland',
])
def test_real_pack_matches_a_small_town_and_its_country_without_punctuation(
        text, pack, master):
    """A small locality and its own country are an address chain without a comma."""
    result = classify(rec(text), pack, master)
    assert (result.status, result.hkp_code) == ('MATCHED', 'IE')


@pytest.mark.parametrize('name', ['United States of America', 'Republic of India'])
@pytest.mark.parametrize('company', ['', ' Ltd'])
def test_longer_country_names_keep_explicit_and_withdrawn_conflicts(
        name, company, pack, master):
    result = classify(rec(name + company + ', Canada'), pack, master)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


@pytest.mark.parametrize('text', ['Northern、Ireland', '北爱尔兰', '北愛爾蘭'])
def test_ideographic_comma_cannot_turn_northern_ireland_into_ireland(text, pack, master):
    result = classify(rec(text), pack, master)
    assert result.hkp_code != 'IE'
    assert result.status != 'MATCHED' or result.hkp_code == 'GB'


def test_repeated_country_input_has_a_bounded_review_path(pack, master):
    record = rec(', '.join(['India'] * 4000))
    result = classify(record, pack, master)
    assert (result.status, result.reason) == ('REVIEW_AMBIGUOUS', 'ADDRESS_TOO_LONG')
    assert result.hkp_code is None
