"""Stream CSV/TXT addresses preserving original columns and control IDs.

For invalid UTF-8 in a known CSV record, surrogateescape preserves the
record boundary and makes the record INPUT_ERROR. Escaped bytes in fields
allow later UTF-8 exports without silently interpreting corrupt text.
"""
import csv
from pathlib import Path
from collections.abc import Iterator
from world_address_engine.models import AddressRecord


def _header_names(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for h in headers:
        original = h.strip()
        base = original or 'Unnamed'
        seen[base] = seen.get(base, 0) + 1
        candidate = (f'Unnamed_{seen[base]}' if not original else
                     (base if seen[base] == 1 else f'{base}_{seen[base]}'))
        while candidate in result:
            seen[base] += 1
            candidate = f'{base}_{seen[base]}'
        result.append(candidate)
    return result


def _undecodable(text: str) -> bool:
    return any(0xDC80 <= ord(c) <= 0xDCFF for c in text)


def _escaped(text: str) -> str:
    return ''.join(f'\\x{ord(c)-0xDC00:02X}' if 0xDC80 <= ord(c) <= 0xDCFF else c for c in text)


def _record(number: int, path: Path, pairs: dict[str, str], columns: tuple[str, ...],
            record_id_column: str | None = None) -> AddressRecord:
    issue = any(_undecodable(x) for x in pairs.values())
    clean_fields = {k: _escaped(v) for k, v in pairs.items()}
    if not columns:
        columns = tuple(f'NAME_ADDRESS_LINE{i}' for i in range(1, 6) if f'NAME_ADDRESS_LINE{i}' in pairs)
        if not columns:
            raise ValueError('no address columns specified or detected')
    for col in columns:
        if col not in pairs:
            raise ValueError(f'missing address column: {col}')
    address = '\n'.join(clean_fields[c].strip() for c in columns if clean_fields[c].strip())
    rid_key = record_id_column or ('Control no' if 'Control no' in pairs else None)
    if rid_key and rid_key not in pairs:
        raise ValueError(f'missing record ID column: {rid_key}')
    hint = next((clean_fields[c].strip() for c in ('Country', 'COUNTRY', 'Country_Code')
                 if c in pairs and clean_fields[c].strip()), None)
    return AddressRecord(number, str(path), None,
                         clean_fields[rid_key] if rid_key else None, clean_fields,
                         address, hint, 'UNDECODABLE_TEXT' if issue else None)


def iter_csv_records(path: Path, encoding: str, address_columns: tuple[str, ...],
                     record_id_column: str | None = None) -> Iterator[AddressRecord]:
    path = Path(path)
    with path.open('r', encoding=encoding, errors='surrogateescape', newline='') as handle:
        reader = csv.reader(handle, strict=True)
        try:
            headers = _header_names(next(reader))
        except StopIteration:
            raise ValueError('CSV has no header') from None
        for number in __import__('itertools').count(1):
            try:
                values = next(reader)
            except StopIteration:
                break
            except csv.Error as exc:
                raise ValueError(f'CSV structure is invalid near record {number}') from exc
            if len(values) != len(headers):
                raise ValueError(f'CSV structure: row {number} has {len(values)} columns; expected {len(headers)}')
            yield _record(number, path, dict(zip(headers, values)), tuple(address_columns), record_id_column)


def iter_txt_records(path: Path, encoding: str, mode: str, delimiter: str | None = None) -> Iterator[AddressRecord]:
    path = Path(path)
    if mode not in ('line', 'delimited'):
        raise ValueError('TXT mode must be line or delimited')
    if mode == 'delimited' and not delimiter:
        raise ValueError('TXT delimiter required')
    with path.open('r', encoding=encoding, errors='surrogateescape', newline='') as handle:
        for number, line in enumerate(handle, 1):
            line = line.rstrip('\r\n')
            values = line.split(delimiter) if mode == 'delimited' else [line]
            pairs = {f'Text_{index}': text for index, text in enumerate(values, 1)}
            yield _record(number, path, pairs, tuple(pairs))
