"""CLI keeps optional HK selection separate from trusted input hints."""
import csv
import json

from tests.unit.test_retrieve import geo
from tests.unit.test_hk_regional_pack import fixture_pack
from world_address_engine.cli import main


def test_cli_records_optional_hk_pack_and_resume_cannot_override_it(tmp_path, capsys):
    data=tmp_path/'input.csv'
    with data.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['NAME_ADDRESS_LINE1']);writer.writerows([['Japan'],['Hong Kong']])
    global_pack=geo(tmp_path);hk,_=fixture_pack(tmp_path/'hk');out=tmp_path/'out'
    assert main(['analyze','--input',str(data),'--output',str(out),'--geo-db',str(global_pack),
                 '--hk-regional-db',str(hk),'--batch-size','1','--max-batches','1'])==0
    capsys.readouterr()
    assert main(['resume','--job-dir',str(out)])==0
    payload=json.loads(capsys.readouterr().out)
    assert payload['run_metadata']['hk_regional']['path']==str(hk.resolve())
    assert payload['destination_counts']=={'HK':1,'JP':1}
