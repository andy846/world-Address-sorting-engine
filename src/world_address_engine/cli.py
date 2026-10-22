"""Read-only privacy-safe preview of production postal address files.

This command does NOT classify or modify addresses and needs no data packs.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from world_address_engine.io.delimited import iter_csv_records, iter_txt_records


def preview(path: Path, encoding: str = 'utf-8-sig', address_columns: tuple[str,...] = (),
            sheet_name: str | None = None, txt_mode: str = 'line',
            delimiter: str | None = None) -> dict:
    kind=path.suffix.lower()
    if kind=='.csv':
        rows=iter_csv_records(path,encoding,address_columns)
    elif kind=='.txt':
        rows=iter_txt_records(path,encoding,txt_mode,delimiter)
    elif kind=='.xlsx':
        from openpyxl import load_workbook
        from world_address_engine.io.xlsx import iter_xlsx_records
        if not sheet_name:
            wb=load_workbook(path,read_only=True)
            try:sheet_name=wb.sheetnames[0]
            finally:wb.close()
        rows=iter_xlsx_records(path,sheet_name,address_columns)
    else:
        raise ValueError('Unsupported input format: use .csv, .xlsx or .txt')
    total=0;issues=0; extras=0; empty=0; lines=Counter()
    headers=[]; used=[]
    for record in rows:
        total+=1
        if total==1:
            headers=list(record.fields)
            used=list(address_columns) if address_columns else [x for x in headers if x.startswith('NAME_ADDRESS_LINE')]
            if not used and kind=='.txt': used=[x for x in headers if x.startswith('Text_')]
        issues+=bool(record.input_error)
        extras+=any(v for k,v in record.fields.items() if k.startswith('Unnamed_'))
        empty+=not bool(record.address_text.strip())
        lines[len([v for v in record.address_text.splitlines() if v.strip()])]+=1
    return {
        'input_file':path.name, 'format':kind.lstrip('.'), 'total_records':total,
        'original_columns':len(headers), 'address_columns':used,
        'records_with_extra_unnamed_data':extras,
        'records_with_decoding_errors':issues, 'empty_addresses':empty,
        'nonempty_address_line_distribution':dict(sorted(lines.items())),
        'classifications_run':False,
    }


def main(argv: list[str] | None=None) -> int:
    parser=argparse.ArgumentParser(description='Fully offline global postal address tooling')
    sub=parser.add_subparsers(dest='command',required=True)
    scan=sub.add_parser('preview',help='Show input shape and counts without printing addresses')
    scan.add_argument('--input',type=Path,required=True)
    scan.add_argument('--encoding',default='utf-8-sig')
    scan.add_argument('--address-column',action='append',default=[])
    scan.add_argument('--sheet')
    scan.add_argument('--txt-mode',choices=['line','delimited'],default='line')
    scan.add_argument('--delimiter')
    args=parser.parse_args(argv)
    try:
        report=preview(args.input,args.encoding,tuple(args.address_column),args.sheet,args.txt_mode,args.delimiter)
    except (ValueError,OSError,LookupError) as exc:
        print(f'Input preview failed: {exc}',file=sys.stderr)
        return 1
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
