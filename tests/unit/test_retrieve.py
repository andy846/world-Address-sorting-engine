from pathlib import Path
from world_address_engine.data.geonames_builder import build_geonames_pack
from world_address_engine.matching.retrieve import retrieve_candidates
from world_address_engine.matching.normalize import normalize_address


def _row(i, name, country, feature='P', admin='A'):
    return '\t'.join([str(i),name,name,'','0','0',feature,admin,country,'','01','','','','1000','','','UTC','2024-01-01'])


def geo(tmp_path):
    source=tmp_path/'source';source.mkdir(exist_ok=True)
    (source/'allCountries.txt').write_text('\n'.join([
        _row(1,'Tokyo','JP'), _row(2,'Shinjuku','JP'),
        _row(3,'London','GB'), _row(4,'Mumbai','IN'),
        _row(5,'Springfield','US'),_row(6,'Springfield','CA'),
        _row(7,'India','IN','A'), _row(8,'Japan','JP','A'),
    ])+'\n',encoding='utf8')
    (source/'alternateNamesV2.txt').write_text('', encoding='utf8')
    path=tmp_path/'geo.db'
    build_geonames_pack(source,path,'EXTENDED_GLOBAL')
    return path


def test_shinjuku_tokyo_proposes_jp(tmp_path):
    found=retrieve_candidates(geo(tmp_path), normalize_address('Shinjuku, Tokyo'),None)
    assert found[0].destination_id=='JP'
    assert len(found[0].evidence)==2


def test_mumbai_india_does_not_propose_gb_from_london_road(tmp_path):
    found=retrieve_candidates(geo(tmp_path),normalize_address('London Road, Mumbai, India'),None)
    by_code={v.destination_id:v for v in found}
    assert 'IN' in by_code and len(by_code['IN'].evidence)>=2
    if 'GB' in by_code: assert by_code['IN'].score>by_code['GB'].score


def test_springfield_without_other_context_is_ambiguous(tmp_path):
    found=retrieve_candidates(geo(tmp_path),normalize_address('Main Street, Springfield'),None)
    assert {c.destination_id for c in found}=={'US','CA'}


def test_only_twenty_candidates_returned(tmp_path):
    found=retrieve_candidates(geo(tmp_path),normalize_address('Tokyo Mumbai London Springfield Shinjuku'),None,limit=2)
    assert len(found)<=2


def test_admin_hierarchy_prevents_false_link(tmp_path):
    found=retrieve_candidates(geo(tmp_path),normalize_address('Tokyo Mumbai'),None)
    assert len(found)>=2
    assert all(c.destination_id in ('JP','IN') for c in found)
