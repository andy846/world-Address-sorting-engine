import csv,json,subprocess,sys,os
from pathlib import Path


def test_preview_reports_shape_without_printing_address_values(tmp_path):
    source=tmp_path/'mail.csv'
    with source.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f)
        w.writerow([*(f'NAME_ADDRESS_LINE{i}' for i in range(1,6)),'Control no','',''])
        w.writerow(['PRIVATE RECIPIENT NAME','Tokyo','Japan','','','00001','ext',''])
        w.writerow(['MORE PRIVATE DATA','Hong Kong','','','','00002','',''])
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2]/'src')}
    out=subprocess.run([sys.executable,'-m','world_address_engine.cli','preview','--input',str(source)],capture_output=True,text=True,env=env)
    assert out.returncode==0, out.stderr
    result=json.loads(out.stdout)
    assert result['total_records']==2
    assert result['original_columns']==8
    assert result['address_columns']==[f'NAME_ADDRESS_LINE{i}' for i in range(1,6)]
    assert result['records_with_extra_unnamed_data']==1
    assert 'PRIVATE' not in out.stdout
    assert 'Hong Kong' not in out.stdout


def test_preview_wrong_explicit_column_fails_without_partial_report(tmp_path):
    source=tmp_path/'mail.csv';source.write_text('Address,Control no\nJapan,001\n',encoding='utf8')
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2]/'src')}
    out=subprocess.run([sys.executable,'-m','world_address_engine.cli','preview','--input',str(source),'--address-column','unknown'],capture_output=True,text=True,env=env)
    assert out.returncode!=0
    assert 'unknown' in out.stderr.lower()
