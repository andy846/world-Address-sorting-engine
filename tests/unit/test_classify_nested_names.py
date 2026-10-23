"""Country evidence belongs to an occurrence, not every use of its text."""

import pytest

from tests.hkp_master_fixture import build_master
from tests.unit.test_classify import classify, rec
from tests.unit.test_retrieve import geo, _row


@pytest.fixture
def nested(tmp_path):
    master = build_master(tmp_path / 'master', countries=[
        ('ireland', 'IE', 'IE', 'Ireland', '愛爾蘭', '爱尔兰'),
        ('uk', 'GB', 'GB', 'United Kingdom', '', ''),
        ('papua-new-guinea', 'PG', 'PG', 'Papua New Guinea', '', ''),
        ('guinea', 'GN', 'GN', 'Guinea', '', ''),
        ('china', 'CN', 'CN', 'China', '', ''),
        ('us', 'US', 'US', 'United States', '', ''),
        ('um', 'UM', 'UM', 'United States Minor Outlying Islands', '', ''),
        ('india', 'IN', 'IN', 'India', '印度', '印度'),
        ('indonesia', 'ID', 'ID', 'Indonesia', '印度尼西亞', '印度尼西亚'),
    ])
    db = geo(tmp_path, extra_rows=[
        _row(100, 'Ireland', 'IE', 'A', 'PCLI', '00', 5000000),
        _row(101, 'Northern Ireland', 'GB', 'A', 'ADM1', 'NIR', 1900000),
        _row(102, 'Papua New Guinea', 'PG', 'A', 'PCLI', '00', 10000000),
        _row(103, 'Guinea', 'GN', 'A', 'PCLI', '00', 14000000),
        _row(104, 'United States Minor Outlying Islands', 'UM', 'A', 'PCLI', '00', 300),
        _row(105, 'China', 'CN', 'A', 'PCLI', '00', 1406585000),
        _row(106, 'Town of China', 'CN'),
        _row(107, 'Lubok China', 'CN'),
        _row(108, 'La Guinea', 'GN'),
    ], extra_aliases=[
        '100\t101\tzh-Hant\t北愛爾蘭\n',
        '101\t100\tzh-Hant\t愛爾蘭\n', '102\t100\tzh-Hans\t爱尔兰\n',
    ])
    return db, master


def test_subdivision_does_not_assert_the_country_inside_its_name(nested):
    result = classify(rec('Northern Ireland'), *nested)
    assert result.hkp_code != 'IE'
    assert result.status != 'MATCHED' or result.hkp_code == 'GB'


@pytest.mark.parametrize('text', [
    'Papua New Guinea, Guinea',
    'Guinea, Papua New Guinea',
    'Papua New Guinea; Guinea',
    'Recipient\nPapua New Guinea\nGuinea',
    'United States Minor Outlying Islands, United States',
    'Papua New Guinea Ltd, Guinea',
    'Guinea Ltd, Papua New Guinea',
    '印度尼西亞, 印度',
    '印度, 印度尼西亞',
    '印度尼西亚, 印度',
    '印度尼西亞有限公司, 印度',
])
def test_independent_country_occurrences_are_never_subsumed(text, nested):
    result = classify(rec(text), *nested)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


@pytest.mark.parametrize('text,code', [
    ('Papua New Guinea', 'PG'),
    ('United States Minor Outlying Islands', 'UM'),
    ('Guinea', 'GN'),
    ('Papua New Guinea Ltd, Papua New Guinea', 'PG'),
    ('印度尼西亞', 'ID'),
    ('印度尼西亚', 'ID'),
])
def test_nested_country_words_do_not_create_false_conflicts(text, code, nested):
    result = classify(rec(text), *nested)
    assert (result.status, result.hkp_code) == ('MATCHED', code)


def test_nested_company_country_alone_is_not_destination_evidence(nested):
    result = classify(rec('Papua New Guinea Ltd'), *nested)
    assert result.status != 'MATCHED'
    assert result.hkp_code is None


@pytest.mark.parametrize('text,code', [
    ('Town of China', 'CN'),
    ('Lubok China', 'CN'),
    ('La Guinea', 'GN'),
])
def test_low_weight_longer_place_names_never_assert_the_country_inside_them(
        text, code, nested):
    result = classify(rec(text), *nested)
    assert result.status != 'MATCHED'
    assert result.hkp_code != code


@pytest.mark.parametrize('text', ['PapuaNewGuinea', 'UnitedStates'])
def test_occurrence_matching_preserves_country_word_boundaries(text, nested):
    result = classify(rec(text), *nested)
    assert result.status == 'UNKNOWN'
    assert result.hkp_code is None


@pytest.fixture
def brunswick(tmp_path):
    master = build_master(tmp_path / 'master', countries=[
        ('canada', 'CA', 'CA', 'Canada', '', ''),
        ('us', 'US', 'US', 'United States', '', ''),
    ])
    db = geo(tmp_path, extra_rows=[
        _row(100, 'New Brunswick', 'CA', 'A', 'ADM1', '04', 800000),
        _row(101, 'New Brunswick', 'US', pop=55000),
        _row(102, 'Brunswick', 'US', pop=45000),
        _row(103, 'New Jersey', 'US', 'A', 'ADM1', 'NJ', 9000000),
        _row(104, 'Canada', 'CA', 'A', 'PCLI', '00', 40000000),
    ])
    return db, master


def test_one_admin_phrase_cannot_manufacture_independent_place_signals(brunswick):
    result = classify(rec('New Brunswick'), *brunswick)
    assert result.status in ('UNKNOWN', 'REVIEW_AMBIGUOUS')
    assert result.hkp_code is None


@pytest.mark.parametrize('text,code', [
    ('New Brunswick, Canada', 'CA'),
    ('New Brunswick, New Jersey, United States', 'US'),
])
def test_explicit_context_disambiguates_an_overlapping_place_phrase(text, code, brunswick):
    result = classify(rec(text), *brunswick)
    assert (result.status, result.hkp_code) == ('MATCHED', code)


def test_place_overlap_does_not_remove_separate_country_conflicts(brunswick):
    result = classify(rec('New Brunswick, Canada, United States'), *brunswick)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


@pytest.fixture
def same_spelled_localities(tmp_path):
    master = build_master(tmp_path / 'master', countries=[
        ('macau', 'MO', 'MO', 'Macau', '', ''),
        ('brazil', 'BR', 'BR', 'Brazil', '', ''),
        ('france', 'FR', 'FR', 'France', '', ''),
        ('italy', 'IT', 'IT', 'Italy', '', ''),
        ('us', 'US', 'US', 'United States', '', ''),
    ])
    db = geo(tmp_path, extra_rows=[
        _row(100, 'Macau Special Administrative Region', 'MO', 'A', 'PCLS', '00', 685900),
        _row(101, 'Macau', 'BR', pop=50000),
        _row(102, 'Macau', 'FR', pop=20000),
        _row(103, 'Brazil', 'BR', 'A', 'PCLI', '00', 214000000),
        _row(104, 'Italy', 'IT', 'A', 'PCLI', '00', 59000000),
        _row(105, 'Italy', 'US', pop=1200),
        _row(106, 'Milano', 'IT', pop=1370000),
        _row(107, 'Milano', 'US', pop=1200),
        _row(108, 'Roma', 'IT', pop=2800000),
    ])
    return db, master


def test_same_spelled_localities_without_independent_context_do_not_withdraw_country(
        same_spelled_localities):
    result = classify(rec('Macau'), *same_spelled_localities)
    assert (result.status, result.hkp_code) == ('MATCHED', 'MO')


def test_same_spelled_locality_with_explicit_parent_country_is_assertable(
        same_spelled_localities):
    result = classify(rec('Macau, Brazil'), *same_spelled_localities)
    assert (result.status, result.hkp_code) == ('MATCHED', 'BR')


def test_shared_local_terms_do_not_withdraw_an_explicit_country(
        same_spelled_localities):
    result = classify(rec('Via Roma 1, Milano, Italy'), *same_spelled_localities)
    assert (result.status, result.hkp_code) == ('MATCHED', 'IT')


@pytest.fixture
def country_expansions(tmp_path):
    master = build_master(tmp_path / 'master', countries=[
        ('canada', 'CA', 'CA', 'Canada', '', ''),
        ('us', 'US', 'US', 'United States', '', ''),
        ('india', 'IN', 'IN', 'India', '', ''),
    ])
    db = geo(tmp_path, extra_rows=[
        _row(100, 'Canada', 'CA', 'A', 'PCLI', '00', 40000000),
    ], extra_aliases=[
        '100\t20\ten\tUnited States of America\n',
        '101\t7\ten\tRepublic of India\n',
    ])
    return db, master


@pytest.mark.parametrize('name', ['United States of America', 'Republic of India'])
@pytest.mark.parametrize('company', ['', ' Ltd'])
def test_longer_country_entities_preserve_the_catalogue_country_identity(
        name, company, country_expansions):
    result = classify(rec(name + company + ', Canada'), *country_expansions)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


@pytest.mark.parametrize('name,code', [
    ('United States of America', 'US'), ('Republic of India', 'IN'),
])
def test_longer_country_entities_work_without_a_rival(name, code, country_expansions):
    result = classify(rec(name), *country_expansions)
    assert (result.status, result.hkp_code) == ('MATCHED', code)
    withdrawn = classify(rec(name + ' Ltd'), *country_expansions)
    assert withdrawn.status != 'MATCHED'
    assert withdrawn.hkp_code is None


@pytest.mark.parametrize('separator', ['、', '/', '／', ' (', '\t'])
def test_retrieval_and_occurrence_punctuation_agree(separator, nested):
    result = classify(rec('Northern' + separator + 'Ireland'), *nested)
    assert result.hkp_code != 'IE'
    assert result.status != 'MATCHED' or result.hkp_code == 'GB'


def test_unlocatable_cross_script_geography_never_asserts_inner_country(nested):
    result = classify(rec('Northern香港Ireland'), *nested)
    assert result.status == 'REVIEW_AMBIGUOUS'
    assert result.reason == 'UNLOCATABLE_GEOGRAPHIC_TERM'
    assert result.hkp_code is None


@pytest.mark.parametrize('text', ['北爱尔兰', '北愛爾蘭'])
def test_variant_matches_use_the_original_occurrence_coordinates(text, nested):
    result = classify(rec(text), *nested)
    assert result.hkp_code != 'IE'
    assert result.status != 'MATCHED' or result.hkp_code == 'GB'


@pytest.mark.parametrize('count,reason', [
    (4000, 'ADDRESS_TOO_LONG'), (1200, 'GEOGRAPHIC_OCCURRENCE_LIMIT'),
])
def test_repeated_country_work_is_bounded_and_preserves_the_record(
        count, reason, country_expansions):
    record = rec(', '.join(['India'] * count))
    original = (record.address_text, dict(record.fields))
    result = classify(record, *country_expansions)
    assert (result.status, result.reason) == ('REVIEW_AMBIGUOUS', reason)
    assert result.hkp_code is None
    assert (record.address_text, dict(record.fields)) == original


def test_repeated_country_below_the_budget_still_classifies(country_expansions):
    result = classify(rec(', '.join(['India'] * 1000)), *country_expansions)
    assert (result.status, result.hkp_code) == ('MATCHED', 'IN')


@pytest.mark.parametrize('prefix_size,status,code', [
    (9993, 'MATCHED', 'IN'), (9994, 'REVIEW_AMBIGUOUS', None),
])
def test_address_length_boundary_does_not_silently_truncate_country_evidence(
        prefix_size, status, code, country_expansions):
    result = classify(rec('x' * prefix_size + ', India'), *country_expansions)
    assert (result.status, result.hkp_code) == (status, code)
    if code is None:
        assert result.reason == 'ADDRESS_TOO_LONG'


def test_normalization_expansion_is_also_length_bounded(country_expansions):
    result = classify(rec('\ufb03' * 3334), *country_expansions)
    assert (result.status, result.reason) == ('REVIEW_AMBIGUOUS', 'ADDRESS_TOO_LONG')
