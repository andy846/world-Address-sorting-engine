"""Count-conserving streaming reports for offline destination classification.

The Run_Manifest is published last; absent manifest means incomplete run.
Default CSV is Excel-safe. Optional machine CSV retains original cell text
and must NOT be opened directly as a spreadsheet with untrusted cell values.
"""
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterator
from world_address_engine.models import AddressRecord, ClassificationResult, STATUSES

RESULT_FIELDS = (
    'Source_File', 'Source_Sheet', 'Source_Record_No', 'Record_ID',
    'HKP_Destination_Code', 'Classification_Status', 'Confidence_Score',
    'Match_Method', 'Match_Evidence', 'Review_Reason',
    'Destination_ID', 'Destination_Name_EN', 'Destination_Name_TC',
    'HKP_Catalogue_Version', 'Geo_Pack_Versions', 'Rules_Version', 'Data_Class',
)

DATA_CLASS_PRODUCTION = 'PRODUCTION_APPROVED'
DATA_CLASS_TEST_ONLY = 'TEST_ONLY_UNVERIFIED'


class CodeApprovalError(ValueError):
    """Raised when a row carries a destination code the catalogue does not issue."""


def _protect(value: object) -> str:
    text = '' if value is None else str(value)
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t','\r','\n')):
        return "'" + text
    return text


def _hash(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def _data_class(run_metadata: dict) -> str:
    """The visible class of the export, so a test file is never mistaken
    for a production mailing list."""
    if run_metadata.get('data_approval') == 'INDEPENDENTLY_AUDITED':
        return DATA_CLASS_PRODUCTION
    return DATA_CLASS_TEST_ONLY


def write_reports(items: Iterator[tuple[AddressRecord, ClassificationResult]],
                  output_dir: Path, run_metadata: dict, *, machine_export: bool = False,
                  code_validator=None, require_validated_codes: bool = False) -> dict[str,int]:
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.run-',dir=output_dir))
    status_counts=Counter({status:0 for status in STATUSES})
    code_counts=Counter()
    data_class=_data_class(run_metadata)
    catalogue_version=str(run_metadata.get('catalogue_version','') or '')
    geo_pack_versions=str(run_metadata.get('geo_pack_versions','') or '')
    rules_version=str(run_metadata.get('rules_version','') or '')
    previous=0
    tracked=[]
    try:
        it=iter(items)
        first=next(it,None)
        columns=list(first[0].fields) if first else []
        duplicate=set(columns).intersection(RESULT_FIELDS)
        if duplicate: raise ValueError(f'original field conflicts with output columns: {duplicate}')
        names=columns+list(RESULT_FIELDS)
        from itertools import chain
        with (stage/'Classified_Addresses.csv').open('w',encoding='utf-8-sig',newline='') as detailed, \
             (stage/'Manual_Review.csv').open('w',encoding='utf-8-sig',newline='') as manual:
            output=csv.DictWriter(detailed,fieldnames=names)
            review=csv.DictWriter(manual,fieldnames=names)
            output.writeheader();review.writeheader()
            machine=None;machine_writer=None
            if machine_export:
                machine=(stage/'Classified_Addresses.machine.csv').open('w',encoding='utf-8-sig',newline='')
                machine_writer=csv.DictWriter(machine,fieldnames=names)
                machine_writer.writeheader()
            try:
                for record, result in chain((first,) if first else (),it):
                    if record.record_no!=previous+1 or result.record_no!=record.record_no:
                        raise ValueError('source rows must be contiguous, ordered and match results')
                    if list(record.fields)!=columns:
                        raise ValueError('source schema changed inside job')
                    previous=record.record_no
                    status_counts[result.status]+=1
                    if result.status=='MATCHED':
                        if require_validated_codes and code_validator is None:
                            raise CodeApprovalError(
                                'a MATCHED row cannot be exported without a code validator')
                        if code_validator is not None and not code_validator(
                                result.destination_id, result.hkp_code):
                            raise CodeApprovalError(
                                f'row {result.record_no} carries a destination code the '
                                'approved catalogue does not issue')
                        code_counts[result.hkp_code]+=1
                    added={
                        'Source_File':Path(record.source_file).name, 'Source_Sheet':record.source_sheet or '',
                        'Source_Record_No':str(record.record_no),'Record_ID':record.record_id or '',
                        'HKP_Destination_Code':result.hkp_code or '',
                        'Classification_Status':result.status,
                        'Confidence_Score':str(result.confidence),
                        'Match_Method':result.reason if result.status=='MATCHED' else '',
                        'Match_Evidence':'; '.join(result.evidence),
                        'Review_Reason':'' if result.status=='MATCHED' else result.reason,
                        'Destination_ID':result.destination_id or '',
                        'Destination_Name_EN':result.destination_name_en,
                        'Destination_Name_TC':result.destination_name_tc,
                        'HKP_Catalogue_Version':catalogue_version,
                        'Geo_Pack_Versions':geo_pack_versions,
                        'Rules_Version':rules_version,
                        'Data_Class':data_class,
                    }
                    original={**record.fields,**added}
                    protected={k:_protect(v) for k,v in original.items()}
                    output.writerow(protected)
                    if result.status!='MATCHED': review.writerow(protected)
                    if machine_writer is not None: machine_writer.writerow(original)
            finally:
                if machine: machine.close()
        with (stage/'Country_Summary.csv').open('w',encoding='utf-8-sig',newline='') as report:
            writer=csv.writer(report)
            writer.writerow(['HKP_Destination_Code','Count','Data_Class'])
            for code,count in sorted(code_counts.items()):
                writer.writerow([_protect(code),count,data_class])
        if sum(status_counts.values())!=previous or sum(code_counts.values())!=status_counts['MATCHED']:
            raise ValueError('statistics reconciliation failed')
        (stage/'DATA_CLASS.txt').write_text(
            f'{data_class}\n\n'
            f'This export is classified as {data_class}.\n'
            'TEST_ONLY_UNVERIFIED output must not be used for real mailings or '
            'for any postal decision.\n',
            encoding='utf-8')
        files=sorted(p for p in stage.iterdir() if p.suffix in ('.csv','.txt'))
        manifest={
            'run_status':'COMPLETE','total_records':previous,
            'status_counts':dict(sorted(status_counts.items())),
            'destination_counts':dict(sorted(code_counts.items())),
            'run_metadata':run_metadata,
            'data_class':data_class,
            'export_mode':'EXCEL_SAFE_WITH_MACHINE_COPY' if machine_export else 'EXCEL_SAFE',
            'sha256':{p.name:_hash(p) for p in files},
        }
        (stage/'Run_Manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        # Publishing manifest LAST ensures incomplete exports cannot be mistaken
        # for completed exports; an existing manifest may not be overwritten.
        if (output_dir/'Run_Manifest.json').exists():
            raise FileExistsError('existing completed run cannot be overwritten')
        for p in files: os.replace(p, output_dir/p.name)
        os.replace(stage/'Run_Manifest.json',output_dir/'Run_Manifest.json')
        return dict(status_counts)
    finally:
        shutil.rmtree(stage,ignore_errors=True)
