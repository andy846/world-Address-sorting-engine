"""Classification behaviour against the REAL worldwide GeoNames packs.

These expectations were measured against the packs produced by GitHub Actions
run 39827512415, not against a synthetic fixture. The tests are skipped when
the packs are absent because the artefacts are far too large to commit.

The HKP master used here is the *test* fixture in ``tests/hkp_master_fixture``
and is explicitly not the verified Hongkong Post master.
"""

import os
from pathlib import Path

import pytest

from world_address_engine.models import AddressRecord
from world_address_engine.matching.classify import classify_record
from tests.hkp_master_fixture import build_master

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = Path(os.environ.get("WASE_REAL_PACK_DIR",
                                REPO_ROOT / "builds" / "real-2026-10-22"))
PACKS = {
    "COMPACT_GLOBAL": PACK_ROOT / "compact" / "compact_global.sqlite",
    "EXTENDED_GLOBAL": PACK_ROOT / "extended" / "extended_global.sqlite",
}


@pytest.fixture(scope="module")
def hkp_db(tmp_path_factory):
    return build_master(tmp_path_factory.mktemp("hkp"))


def _pack(name):
    path = PACKS[name]
    if not path.is_file():
        pytest.skip(f"real {name} pack not present at {path}")
    return path


def _classify(address, hint, geo, hkp):
    record = AddressRecord(1, 'sample.csv', None, '0001', {'Address': address}, address, hint)
    return classify_record(record, geo, hkp)


MATCHED = [
    ('London Road, Mumbai, India', 'IN'),
    ('10 Bayfront Avenue, Singapore', 'SG'),
    ('Shinjuku-ku, Tokyo 160-0022', 'JP'),
    ('Macau', 'MO'),
    ('Macao', 'MO'),
    ('Timor-Leste', 'TP'),
    ('Springfield, Illinois', 'US'),
    ('India', 'IN'),
    ('Japan', 'JP'),
    ('Tokyo, Japan', 'JP'),
    ('Berlin, Germany', 'DE'),
    ('Paris, France', 'FR'),
    ('Hong Kong', 'HK'),
    ('香港', 'HK'),
    ('Guam', 'GU'),
    ('Puerto Rico', 'PR'),
    ('中国北京市朝阳区', 'CN'),
    ('上海浦东新区', 'CN'),
    ('St. Louis, Missouri, United States', 'US'),
    ('Sao Paulo, Brazil', 'BR'),
    ('Zürich, Switzerland', 'CH'),
    ('Via Roma 1, Milano, Italy', 'IT'),
]

REVIEWED = [
    ('Main Street, Springfield', None),
    ('Springfield', None),
    ('Berlin', None),
    ('Paris', None),
    ('Tokyo', None),
    ('Frankfurt', None),
    ('CHINA CONSTRUCTION LTD', None),
    ('Jane Doe\nCHINA CONSTRUCTION LTD\n1 Main St, Springfield, US', None),
    ('北京市\n中国银行', None),
    ('Jane Doe\nHONG KONG HOLDINGS LTD\n1 Main St, Springfield, US', None),
]


@pytest.mark.parametrize("profile", sorted(PACKS))
@pytest.mark.parametrize("address,expected", MATCHED)
def test_real_pack_matches_the_expected_destination(profile, address, expected, hkp_db):
    geo = _pack(profile)
    result = _classify(address, None, geo, hkp_db)
    assert result.status == 'MATCHED', result.reason
    assert result.hkp_code == expected


@pytest.mark.parametrize("profile", sorted(PACKS))
@pytest.mark.parametrize("address", sorted({case[0] for case in REVIEWED}))
def test_real_pack_never_guesses_an_ambiguous_or_company_address(profile, address, hkp_db):
    geo = _pack(profile)
    result = _classify(address, None, geo, hkp_db)
    assert result.status in ('UNKNOWN', 'REVIEW_AMBIGUOUS', 'REVIEW_CONFLICT'), result.reason
    assert result.hkp_code is None


def test_real_pack_country_hint_conflicting_with_geography_is_review(hkp_db):
    geo = _pack("EXTENDED_GLOBAL")
    result = _classify('Tokyo', 'US', geo, hkp_db)
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


def test_real_pack_country_hint_agreeing_with_geography_is_matched(hkp_db):
    geo = _pack("EXTENDED_GLOBAL")
    result = _classify('London Road, Mumbai, India', 'IN', geo, hkp_db)
    assert result.status == 'MATCHED' and result.hkp_code == 'IN'


def test_real_pack_evidence_mass_does_not_saturate(hkp_db):
    """'springfield' matches dozens of places; the evidence must stay small."""
    from world_address_engine.matching.retrieve import retrieve_candidates
    from world_address_engine.matching.normalize import normalize_address
    geo = _pack("EXTENDED_GLOBAL")
    found = retrieve_candidates(geo, normalize_address('Springfield'), None)
    assert found
    for candidate in found:
        assert candidate.support < 0.6, candidate
        assert candidate.score <= 0.99
    assert len({c.destination_id for c in found}) >= 5
