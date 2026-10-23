import csv,json
from world_address_engine.models import AddressRecord,ClassificationResult
from world_address_engine.io.reports import write_reports


def pair(n, address, status, code=None):
    row=AddressRecord(n,'test.csv',None,f'{n:05d}',{'Address':address,'Control no':f'{n:05d}'},address,None)
    result=ClassificationResult(n,status,code,1.0 if code else 0.,'test',code)
    return row,result


def read(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def test_summary_counts_equal_matched_rows(tmp_path):
    items=[pair(1,'Japan','MATCHED','JP'),pair(2,'India','MATCHED','IN'),pair(3,'Unknown','UNKNOWN')]
    counts=write_reports(iter(items),tmp_path,{'catalogue_version':'fixture'})
    summary=read(tmp_path/'Country_Summary.csv')
    assert counts['MATCHED']==2
    assert {r['HKP_Destination_Code']:int(r['Count']) for r in summary}=={'JP':1,'IN':1}
    manifest=json.loads((tmp_path/'Run_Manifest.json').read_text())
    assert manifest['total_records']==3 and manifest['run_status']=='COMPLETE'


def test_review_rows_not_assigned_codes(tmp_path):
    write_reports(iter([pair(1,'Unknown','UNKNOWN')]),tmp_path,{})
    assert len(read(tmp_path/'Manual_Review.csv'))==1
    assert read(tmp_path/'Classified_Addresses.csv')[0]['HKP_Destination_Code']==''


def test_duplicate_address_rows_count_twice(tmp_path):
    write_reports(iter([pair(1,'Japan','MATCHED','JP'),pair(2,'Japan','MATCHED','JP')]),tmp_path,{})
    assert read(tmp_path/'Country_Summary.csv')[0]['Count']=='2'
    assert len(read(tmp_path/'Classified_Addresses.csv'))==2


def test_spreadsheet_formula_injection_is_neutralized_in_excel_view(tmp_path):
    write_reports(iter([pair(1,'=2+2','UNKNOWN')]),tmp_path,{})
    assert read(tmp_path/'Classified_Addresses.csv')[0]['Address']=="'=2+2"


def test_machine_mode_keeps_exact_original_string(tmp_path):
    write_reports(iter([pair(1,'=2+2','UNKNOWN')]),tmp_path,{},machine_export=True)
    assert read(tmp_path/'Classified_Addresses.machine.csv')[0]['Address']=='=2+2'


def test_original_columns_and_order_preserved(tmp_path):
    write_reports(iter([pair(1,'Japan','MATCHED','JP'),pair(2,'China','UNKNOWN')]),tmp_path,{})
    rows=read(tmp_path/'Classified_Addresses.csv')
    assert list(rows[0])[:2]==['Address','Control no']
    assert [r['Control no'] for r in rows]==['00001','00002']
