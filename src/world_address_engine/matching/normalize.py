"""Safe, intentionally conservative normalization of English and Chinese addresses.

Chinese variants here come from a small curated list and, when the optional
pinned OpenCC package is installed, from a deterministic Traditional/Simplified
conversion of the whole address. The conversion is a *variant of the same
text*, never independent corroboration, and it never rewrites the input
fields. The GeoNames index may also provide independently sourced Chinese
aliases.
"""
import re
import unicodedata

_VARIANTS = (
    ('臺北', '台北'), ('廣州', '广州'), ('廣東', '广东'), ('深圳', '深圳'),
    ('澳門', '澳门'), ('臺灣', '台湾'), ('中國', '中国'), ('香港', '香港'),
    ('東京', '东京'), ('東京都', '东京都'), ('新加坡', '新加坡'),
)

# The optional converter is loaded once and never reaches the network.
_CONVERTERS: dict[str, object] = {}


def _converter(kind: str):
    """Load one pinned OpenCC converter, or ``None`` when it is absent."""
    if kind in _CONVERTERS:
        return _CONVERTERS[kind]
    converter = None
    try:
        from opencc import OpenCC
        converter = OpenCC(kind)
    except Exception:
        converter = None
    _CONVERTERS[kind] = converter
    return converter


def _han_forms(base: str) -> list[str]:
    """The Traditional and Simplified counterparts of a Han address."""
    if not any('㐀' <= char <= '鿿' for char in base):
        return []
    forms: list[str] = []
    for kind in ('t2s', 's2t'):
        converter = _converter(kind)
        if converter is None:
            continue
        try:
            variant = converter.convert(base)
        except Exception:
            continue
        if variant and variant != base:
            forms.append(variant)
    return forms


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
    variants.extend(_han_forms(base))
    return tuple(dict.fromkeys(variants))


def has_unsupported_script(value: str) -> bool:
    """Reject unsupported writing systems without skipping their marks.

    NFKC runs first so compatibility forms of supported Latin text are not
    rejected. Combining marks and format controls are rejected after that
    step: a mark must never become an invisible word boundary.
    """
    value = unicodedata.normalize('NFKC', value)
    for char in value:
        category = unicodedata.category(char)
        if category.startswith('M') or category == 'Cf':
            return True
        if not char.isalpha():
            continue
        name = unicodedata.name(char, '')
        if name.startswith('LATIN'):
            continue
        if name.startswith(('CJK UNIFIED IDEOGRAPH', 'CJK COMPATIBILITY IDEOGRAPH')):
            continue
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
