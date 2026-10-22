from openpyxl import Workbook
from world_address_engine.io.xlsx import iter_xlsx_records


def _save(path, rows):
    wb = Workbook(); ws = wb.active; ws.title='Letters'
    for row in rows:ws.append(row)
    wb.create_sheet('Other').append(['not','for','this'])
    wb.save(path)


def test_sheet_selection_and_column_mapping(tmp_path):
    p=tmp_path/'sample.xlsx'
    _save(p,[['Address','Control no','Note'],['Tokyo, Japan','00001','hold'],['Macau','00002','ok']])
    values=list(iter_xlsx_records(p,'Letters',('Address',)))
    assert [r.record_id for r in values]==['00001','00002']
    assert values[0].address_text=='Tokyo, Japan'
    assert values[0].source_sheet=='Letters'
    assert values[0].fields['Note']=='hold'


def test_blank_rows_do_not_shift_record_ids(tmp_path):
    p=tmp_path/'sample.xlsx'
    _save(p,[['Address','Control no'],['Tokyo','00001'],[None,None],['Macau','00002']])
    rows=list(iter_xlsx_records(p,'Letters',('Address',)))
    assert len(rows)==2
    assert [r.record_no for r in rows]==[1,2]
    assert rows[-1].record_id=='00002'


def test_formula_without_cached_value_is_input_error_using_readonly_formula_check(tmp_path):
    p=tmp_path/'sample.xlsx'
    _save(p,[['Address','Control no'],['=UPPER("Japan")','00001']])
    rows=list(iter_xlsx_records(p,'Letters',('Address',)))
    assert rows[0].input_error=='FORMULA_WITHOUT_CACHED_VALUE'


def test_xlsx_reader_is_iterator_not_materialized_list(tmp_path):
    p=tmp_path/'sample.xlsx'; _save(p,[['Address','Control no'],['Tokyo','1']])
    stream=iter_xlsx_records(p,'Letters',('Address',))
    assert iter(stream) is stream
    assert next(stream).address_text=='Tokyo'
