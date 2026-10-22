"""Verify official GeoNames ZIP layout is parsed directly without unpacking."""
import sqlite3
import zipfile
from pathlib import Path
from world_address_engine.data.geonames_builder import build_geonames_pack


def row(i, name, latin, cls, country):
    return "\t".join([str(i),name,latin,"","0","0",cls,"PPL",country,"","01","","","","1200","","","UTC","2026-10-22"])


def make_zip(path, basename, text):
    with zipfile.ZipFile(path/f"{basename}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{basename}.txt", text)


def sources(path):
    make_zip(path,"allCountries","\n".join([
        row(1,"Tokyo","Tokyo","P","JP"),
        row(2,"Shinjuku","Shinjuku","P","JP"),
        row(3,"村莊","Cun Zhuang","P","CN"),
        row(4,"Kowloon","Kowloon","A","HK"),
        row(5,"Mount Fuji","Mount Fuji","T","JP")])+"\n")
    make_zip(path,"cities1000",row(1,"Tokyo","Tokyo","P","JP")+"\n"+row(2,"Shinjuku","Shinjuku","P","JP")+"\n")
    make_zip(path,"alternateNamesV2","\n".join([
        "10\t1\ten\tTokyo","11\t1\tzh-TW\t東京",
        "12\t1\tzh-CN\t东京","13\t1\tja\tとうきょう",
        "14\t2\ten\tShinjuku"])+"\n")


def test_zipped_compact_and_extended_are_measured_and_valid(tmp_path):
    sources(tmp_path)
    compact = tmp_path/"compact.db"
    extended = tmp_path/"extended.db"
    c = build_geonames_pack(tmp_path,compact,"COMPACT_GLOBAL")
    e = build_geonames_pack(tmp_path,extended,"EXTENDED_GLOBAL")
    assert c["place_count"]==3
    assert e["place_count"]==4
    assert c["sqlite_bytes"]==compact.stat().st_size
    assert e["sqlite_bytes"]==extended.stat().st_size
    assert e["alias_count"]>=c["alias_count"]
    with sqlite3.connect(compact) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        aliases={x[0] for x in db.execute("SELECT alias FROM geo_aliases")}
    assert "東京" in aliases and "东京" in aliases and "とうきょう" not in aliases


def test_zip_missing_fails_without_publishing_empty_db(tmp_path):
    from pytest import raises
    with raises(FileNotFoundError):
        build_geonames_pack(tmp_path,tmp_path/"global.db","EXTENDED_GLOBAL")
    assert not (tmp_path/"global.db").exists()
