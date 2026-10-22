from world_address_engine.matching.normalize import normalize_address, has_unsupported_script, contains_name


def test_english_case_and_whitespace_normalization():
    assert '10 bayfront avenue singapore' in normalize_address('  10   BAYFRONT   Avenue, Singapore  ')


def test_traditional_simplified_city_variants():
    assert '广州' in normalize_address('廣州')
    assert '廣州' in normalize_address('广州')
    assert '台北' in normalize_address('臺北')
    assert '臺北' in normalize_address('台北')


def test_han_romanization_alias_retained():
    assert 'shinjuku, tokyo' in normalize_address('Shinjuku, Tokyo') or 'shinjuku tokyo' in normalize_address('Shinjuku, Tokyo')


def test_russian_script_is_not_silently_accepted():
    assert has_unsupported_script('Москва')
    assert has_unsupported_script('東京都 とうきょう')
    assert not has_unsupported_script('台北市, Taiwan')


def test_in_substring_does_not_match_india_country_code():
    assert not contains_name('International Limited', 'IN')
    assert contains_name('Main Street, India', 'India')
    assert contains_name('London Road', 'London')  # lexical match, not sufficient for country classification


def test_substring_is_not_country_proof():
    assert not contains_name('Chinatown Plaza', 'China')
    assert not contains_name('Made In Japan', 'IN')
