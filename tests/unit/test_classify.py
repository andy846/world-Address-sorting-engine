import csv, hashlib, json
from pathlib import Path
from world_address_engine.models import AddressRecord
from world_address_engine.hkp.catalogue import import_hkp_catalogue
from world_address_engine.matching.classify import classify_record
from tests.unit.test_retrieve import geo


def hkp(tmp_path):
    h=tmp_path/'codes.csv'
    heads=['destination_id','code_scheme','code','name_en','name_zh_hant','name_zh_hans','source_url','source_doc_version','source_section','source_checksum','approval_status','profile','date_verified']
    data=[('india','IN','IN','India','印度','印度'),('japan','JP','JP','Japan','日本','日本'),('uk','GB','GB','United Kingdom','英國','英国'),('us','US','US','United States','美國','美国'),('canada','CA','CA','Canada','加拿大','加拿大'),('macau','MO','MO','Macau','澳門','澳门'),('china','CN','CN','China','中國','中国'),('timor-leste','TL','TP','Timor-Leste','東帝汶','东帝汶'),('singapore','SG','SG','Singapore','新加坡','新加坡')]
    with h.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=heads);w.writeheader()
        for did,iso,postal,en,tc,sc in data:
            common=dict(destination_id=did,name_en=en,name_zh_hant=tc,name_zh_hans=sc,source_url='https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf',source_doc_version='fixture',source_section='fixture-only',source_checksum='fixture-only',approval_status='APPROVED',date_verified='2026-10-23')
            w.writerow(dict(common,code_scheme='HKP_DESTINATION_2',profile='HKP_DESTINATION_2',code=postal))
            w.writerow(dict(common,code_scheme='ISO_ALPHA2',profile='ISO',code=iso))
    mf=tmp_path/'codes.json';mf.write_text(json.dumps({'catalogue_version':'test-fixture','csv_sha256':hashlib.sha256(h.read_bytes()).hexdigest()}),encoding='utf8')
    db=tmp_path/'hkp.db';import_hkp_catalogue(h,mf,db);return db


def rec(text, hint=None):
    return AddressRecord(1,'sample.csv',None,'0001',{'Address':text},text,hint)


def test_london_road_mumbai_india_is_in(tmp_path):
    result=classify_record(rec('London Road, Mumbai, India'),geo(tmp_path),hkp(tmp_path))
    assert result.status=='MATCHED' and result.hkp_code=='IN'


def test_springfield_does_not_guess(tmp_path):
    result=classify_record(rec('Main Street, Springfield'),geo(tmp_path),hkp(tmp_path))
    assert result.status in ('REVIEW_AMBIGUOUS','UNKNOWN') and result.hkp_code is None


def test_conflicting_explicit_countries_review(tmp_path):
    result=classify_record(rec('Tokyo\nJapan\nUnited Kingdom'),geo(tmp_path),hkp(tmp_path))
    assert result.status=='REVIEW_CONFLICT' and result.hkp_code is None


def test_verified_macau_is_mo_not_cn(tmp_path):
    result=classify_record(rec('Macau'),geo(tmp_path),hkp(tmp_path))
    assert result.status=='MATCHED' and result.hkp_code=='MO'


def test_timor_leste_is_tp_not_tl(tmp_path):
    result=classify_record(rec('Timor-Leste'),geo(tmp_path),hkp(tmp_path))
    assert result.status=='MATCHED' and result.hkp_code=='TP'


def test_unapproved_hkp_code_never_asserted(tmp_path):
    # No extra unverified country may be inferred from the test master.
    result=classify_record(rec('Utopia'),geo(tmp_path),hkp(tmp_path))
    assert result.status=='UNKNOWN' and result.hkp_code is None


def test_unsupported_script_has_review_reason(tmp_path):
    result=classify_record(rec('Москва'),geo(tmp_path),hkp(tmp_path))
    assert result.status=='UNKNOWN' and 'UNSUPPORTED_LANGUAGE' in result.reason


def test_bad_input_record_returns_input_error(tmp_path):
    r=AddressRecord(1,'bad.csv',None,'001',{},'x',None,'UNDECODABLE_TEXT')
    result=classify_record(r,geo(tmp_path),hkp(tmp_path))
    assert result.status=='INPUT_ERROR' and result.hkp_code is None


def test_structured_iso_two_letter_hint_is_explicit(tmp_path):
    result=classify_record(rec('Unknown Recipient\nUnknown Street',hint='JP'),geo(tmp_path),hkp(tmp_path))
    assert result.status=='MATCHED' and result.hkp_code=='JP'
