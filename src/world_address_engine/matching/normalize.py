"""Safe, intentionally conservative normalization of English and Chinese addresses.

Chinese variants here are curated rather than global transliteration. The
GeoNames index may also provide independently sourced Chinese aliases.
"""
import re
import unicodedata

_VARIANTS = (
    ('臺北', '台北'), ('廣州', '广州'), ('廣東', '广东'), ('深圳', '深圳'),
    ('澳門', '澳门'), ('臺灣', '台湾'), ('中國', '中国'), ('香港', '香港'),
    ('東京', '东京'), ('東京都', '东京都'), ('新加坡', '新加坡'),
)


def _key(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).casefold()
    text = re.sub(r'[,，、;；\t\r\n]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_address(value: str) -> tuple[str, ...]:
    base = _key(value)
    variants = [base]
    for traditional, simplified in _VARIANTS:
        for a, b in ((traditional, simplified), (simplified, traditional)):
            if a != b and a in base:
                variants.append(base.replace(a, b))
    return tuple(dict.fromkeys(variants))


def has_unsupported_script(value: str) -> bool:
    for char in value:
        name = unicodedata.name(char, '')
        if name.startswith(('CYRILLIC', 'ARABIC', 'HEBREW', 'HIRAGANA', 'KATAKANA', 'HANGUL', 'THAI', 'DEVANAGARI', 'GREEK')):
            return True
    return False


def contains_name(address: str, place_name: str) -> bool:
    return contains_keyed(_key(address), place_name)


def normalize_key(value: str) -> str:
    """The normalised form used for name containment checks.

    Exposed so a caller that tests many names against one address does not
    re-normalise the address for every name.
    """
    return _key(value)


def contains_keyed(haystack: str, place_name: str) -> bool:
    """Containment against an already normalised address."""
    needle = _key(place_name)
    if not needle or (needle.isascii() and needle.isalpha() and len(needle) <= 2):
        return False
    # Do not treat country-like aliases such as "IN" or "US" occurring
    # inside a longer name as isolated geographic evidence.
    if any('a' <= c <= 'z' for c in needle):
        return re.search(r'(?<![a-z0-9])' + re.escape(needle) + r'(?![a-z0-9])', haystack) is not None
    return needle in haystack
