"""Indexed, bounded retrieval of geographic destination hypotheses.

Retrieval is *evidence*, not postal delivery verification. A city name
alone must not become an asserted country in the classification layer.
"""
import re
from collections import defaultdict
from pathlib import Path
from world_address_engine.models import DestinationCandidate
from world_address_engine.sqlite_util import open_db


_LATIN = re.compile(r'[a-z0-9]+')
_HAN = re.compile(r'[\u3400-\u9fff]+')


def _search_terms(forms: tuple[str, ...]) -> list[str]:
    terms: set[str] = set()
    for address in forms:
        tokens = _LATIN.findall(address.casefold())
        for i in range(min(len(tokens), 200)):
            for n in range(1, min(4, len(tokens)-i)+1):
                term = ' '.join(tokens[i:i+n])
                if len(term)>=3: terms.add(term)
        for match in _HAN.findall(address):
            # Chinese compound place names usually do not use whitespace.
            run = match[:150]
            for i in range(len(run)):
                for n in range(2, min(12, len(run)-i)+1):
                    terms.add(run[i:i+n])
    return sorted(terms)


def retrieve_candidates(geo_db: Path, address_forms: tuple[str,...], country_hint: str | None,
                        limit: int = 20) -> list[DestinationCandidate]:
    if limit < 1:
        return []
    terms = _search_terms(address_forms)
    ids: dict[str, set[int]] = defaultdict(set)
    descriptions: dict[str, list[str]] = defaultdict(list)
    with open_db(geo_db) as db:
        for i in range(0,len(terms),400):
            group = terms[i:i+400]
            marks=','.join('?' for _ in group)
            for pid, name, code, cls in db.execute(
                f'''SELECT p.place_id,p.name,p.country_code,p.feature_class
                    FROM geo_aliases a JOIN geo_places p ON p.place_id=a.place_id
                    WHERE a.search_key IN ({marks})''',group
            ):
                if pid not in ids[code]:
                    ids[code].add(pid)
                    descriptions[code].append(f'PLACE:{pid}:{name}:{cls}')
    if country_hint and re.fullmatch(r'[A-Za-z]{2}', country_hint.strip()):
        code=country_hint.strip().upper()
        descriptions[code].append('STRUCTURED_COUNTRY_HINT')
    result = []
    for code, evidence in descriptions.items():
        score = 1.0 if 'STRUCTURED_COUNTRY_HINT' in evidence else min(.99, .35 + .26*len(ids[code]))
        result.append(DestinationCandidate(code,tuple(evidence),score))
    result.sort(key=lambda c:(-c.score,-len(c.evidence),c.destination_id))
    return result[:limit]
