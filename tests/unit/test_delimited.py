import csv
from pathlib import Path
import pytest
from world_address_engine.io.delimited import iter_csv_records, iter_txt_records


def test_dynamic_five_line_sample_mapping_preserves_unnamed_columns(tmp_path):
    p=tmp_path/'post.csv'
    with p.open('w',encoding='utf-8-sig',newline='') as fp:
        w=csv.writer(fp)
        w.writerow([*(f'NAME_ADDRESS_LINE{i}' for i in range(1,6)), 'Control no','',''])
        w.writerow(['Some Person','Building 4','Tokyo','Japan','', '00123', 'misc','x'])
        w.writerow(['ABC Limited','Postal Road','Singapore','','', '00124','',''])
    rows=list(iter_csv_records(p,'utf-8-sig',()))
    assert len(rows)==2
    assert rows[0].fields['Unnamed_1']=='misc'
    assert rows[0].fields['Unnamed_2']=='x'
    assert rows[0].record_id=='00123'
    assert rows[0].address_text=='Some Person\nBuilding 4\nTokyo\nJapan'
    assert rows[1].address_text.endswith('Singapore')


def test_multiline_csv_is_one_logical_record(tmp_path):
    p=tmp_path/'mail.csv'
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f)
        w.writerow(['Address','Control no'])
        w.writerow(['Two\nLines Singapore', '1'])
        w.writerow(['Tokyo, Japan', '2'])
    assert [r.record_no for r in iter_csv_records(p,'utf-8',('Address',))]==[1,2]


def test_big5_chinese_round_trip(tmp_path):
    p=tmp_path/'big5.csv'
    p.write_bytes('地址,Control no\n香港中環,00010\n'.encode('big5'))
    rows=list(iter_csv_records(p,'big5',('地址',)))
    assert rows[0].address_text=='香港中環'
    assert rows[0].record_id=='00010'


def test_utf8_bom_header(tmp_path):
    p=tmp_path/'bom.csv'
    p.write_bytes('\ufeffAddress,Control no\nSingapore,1\n'.encode('utf8'))
    assert len(list(iter_csv_records(p,'utf-8-sig',('Address',))))==1


def test_bad_bytes_report_input_error_without_drop_when_record_boundary_is_known(tmp_path):
    p=tmp_path/'broken.csv'
    p.write_bytes(b'Address,Control no\nTokyo,1\nBad\xffText,2\n')
    rows=list(iter_csv_records(p,'utf-8',('Address',)))
    assert len(rows)==2
    assert rows[1].input_error=='UNDECODABLE_TEXT'
    assert rows[0].input_error is None


def test_unrecoverable_csv_framing_marks_job_incomplete(tmp_path):
    p=tmp_path/'broken.csv'
    p.write_text('Address,Control no\n"unclosed, 1\n', encoding='utf8')
    with pytest.raises(ValueError,match='CSV structure'):
        list(iter_csv_records(p,'utf-8',('Address',)))


def test_txt_delimiter_defines_record_boundary(tmp_path):
    p=tmp_path/'list.txt'
    p.write_text('Tokyo|Japan\nMacau|China\n',encoding='utf8')
    rows=list(iter_txt_records(p,'utf-8','delimited','|'))
    assert len(rows)==2
    assert rows[0].address_text=='Tokyo\nJapan'
    assert rows[1].fields['Text_2']=='China'
