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


def _remove_staging(stage: Path) -> None:
    """Remove plaintext staging data and prove that it is gone."""
    stage = Path(stage)
    if stage.exists():
        try:
            shutil.rmtree(stage)
        except OSError as exc:
            raise OSError(
                f'staging cleanup failed; plaintext data remains at {stage}: {exc}'
            ) from exc
    if stage.exists():
        raise OSError(f'staging cleanup failed; plaintext data remains at {stage}')


def _write_manifest_atomic(output_dir: Path, manifest: dict) -> None:
    """Publish the COMPLETE marker atomically and never overwrite one."""
    target = output_dir / 'Run_Manifest.json'
    if target.exists():
        raise FileExistsError('existing completed run cannot be overwritten')
    fd, temporary_name = tempfile.mkstemp(prefix='.pending-manifest-', dir=output_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            raise FileExistsError('existing completed run cannot be overwritten')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _data_class(run_metadata: dict) -> str:
    """The visible class of the export, so a test file is never mistaken
    for a production mailing list."""
    if run_metadata.get('data_approval') == 'INDEPENDENTLY_AUDITED':
        return DATA_CLASS_PRODUCTION
    return DATA_CLASS_TEST_ONLY


def write_reports(items: Iterator[tuple[AddressRecord, ClassificationResult]],
                  output_dir: Path, run_metadata: dict, *, machine_export: bool = False,
                  code_validator=None, require_validated_codes: bool = False,
                  before_manifest=None) -> dict[str,int]:
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
        # Publishing manifest LAST ensures incomplete exports cannot be mistaken
        # for completed exports; an existing manifest may not be overwritten.
        if (output_dir/'Run_Manifest.json').exists():
            raise FileExistsError('existing completed run cannot be overwritten')
        for p in files: os.replace(p, output_dir/p.name)
        # Remove the sensitive staging directory before the runner drops its
        # plaintext checkpoint. The COMPLETE marker is published only after
        # both cleanup steps succeed.
        _remove_staging(stage)
        # The runner uses this hook to recheck sources and remove checkpoints
        # after reports are staged but before the COMPLETE marker is published.
        if before_manifest is not None:
            before_manifest()
        _write_manifest_atomic(output_dir, manifest)
        return dict(status_counts)
    finally:
        _remove_staging(stage)


def apply_review_corrections(output_dir: Path, decisions, *,
                             approved_destination=None,
                             require_validated_codes: bool = False) -> dict[str,int]:
    """Apply audited manual corrections to a published export.

    The export is streamed, so a multi-million row job is never held in
    memory. A correction applies to exactly one input record: rows that
    happen to share the same address keep their own result. The counts and
    the manifest are recomputed from the corrected file.

    A manual decision is local, writable data. It may therefore only assert
    a destination code that the approval in force actually issues, and it
    may only do so when an approved lookup is supplied. ``Manual_Review.csv``
    is regenerated from the corrected rows so the export never contradicts
    itself.
    """
    output_dir=Path(output_dir)
    detail=output_dir/'Classified_Addresses.csv'
    if not detail.is_file():
        raise FileNotFoundError(detail)
    latest={}
    for decision in decisions:
        latest[int(decision.record_no)]=decision
    # Validate every decision before a single byte is written, so a rejected
    # correction leaves the published export untouched.
    identities={}
    for record_no, decision in latest.items():
        if not decision.new_code:
            continue
        if require_validated_codes and approved_destination is None:
            raise CodeApprovalError(
                'a manual correction cannot be applied without an approved '
                'catalogue lookup')
        identity=None
        if approved_destination is not None:
            identity=approved_destination(decision.new_code)
        if identity is None:
            raise CodeApprovalError(
                f'record {record_no} carries a destination code the approved '
                'catalogue does not issue')
        identities[record_no]=identity
    manifest_path=output_dir/'Run_Manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) \
        if manifest_path.is_file() else {}
    # The run manifest is the authority for the data class; the summary file
    # may be empty when nothing was matched, and it is local writable data.
    data_class=str(manifest.get('data_class') or 'TEST_ONLY_UNVERIFIED')
    stage=Path(tempfile.mkdtemp(prefix='.review-',dir=output_dir))
    try:
        code_counts=Counter()
        status_counts=Counter()
        total=0
        applied=0
        with detail.open(encoding='utf-8-sig',newline='') as source:
            reader=csv.DictReader(source)
            names=list(reader.fieldnames or [])
            with (stage/'Classified_Addresses.csv').open('w',encoding='utf-8-sig',newline='') as target, \
                 (stage/'Manual_Review.csv').open('w',encoding='utf-8-sig',newline='') as manual:
                writer=csv.DictWriter(target,fieldnames=names)
                review=csv.DictWriter(manual,fieldnames=names)
                writer.writeheader();review.writeheader()
                for row in reader:
                    total+=1
                    decision=latest.get(int(row['Source_Record_No'] or 0))
                    if decision is not None and decision.new_code:
                        identity=identities.get(int(row['Source_Record_No'] or 0))
                        row['HKP_Destination_Code']=decision.new_code
                        row['Classification_Status']=decision.new_status
                        row['Match_Method']='MANUAL_REVIEW'
                        row['Match_Evidence']=_protect(decision.reason)
                        row['Review_Reason']=''
                        if identity:
                            row['Destination_ID']=identity.get('destination_id','')
                            row['Destination_Name_EN']=identity.get('name_en','')
                            row['Destination_Name_TC']=identity.get('name_tc','')
                        row['Confidence_Score']='1.0'
                        applied+=1
                    status_counts[row['Classification_Status']]+=1
                    if row['Classification_Status']=='MATCHED':
                        if row['HKP_Destination_Code']:
                            code_counts[row['HKP_Destination_Code']]+=1
                    writer.writerow(row)
                    if row['Classification_Status']!='MATCHED':
                        review.writerow(row)
        if sum(status_counts.values())!=total:
            raise ValueError('statistics reconciliation failed')
        if sum(code_counts.values())!=status_counts['MATCHED']:
            raise ValueError('destination reconciliation failed')
        with (stage/'Country_Summary.csv').open('w',encoding='utf-8-sig',newline='') as report:
            writer=csv.writer(report)
            writer.writerow(['HKP_Destination_Code','Count','Data_Class'])
            for code,count in sorted(code_counts.items()):
                writer.writerow([_protect(code),count,data_class])
        os.replace(stage/'Classified_Addresses.csv',output_dir/'Classified_Addresses.csv')
        os.replace(stage/'Manual_Review.csv',output_dir/'Manual_Review.csv')
        os.replace(stage/'Country_Summary.csv',output_dir/'Country_Summary.csv')
        if manifest:
            manifest['destination_counts']=dict(sorted(code_counts.items()))
            manifest['status_counts']=dict(sorted(status_counts.items()))
            manifest['total_records']=total
            manifest.setdefault('review_corrections',[]).append({
                'applied':applied,'decisions':len(latest),
                'operators':sorted({d.operator for d in latest.values()}),
            })
            digests=manifest.get('sha256')
            if isinstance(digests,dict):
                for name in ('Classified_Addresses.csv','Manual_Review.csv',
                             'Country_Summary.csv','Review_Corrections.csv'):
                    candidate=output_dir/name
                    if candidate.is_file():
                        digests[name]=_hash(candidate)
            manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        return dict(code_counts)
    finally:
        _remove_staging(stage)
