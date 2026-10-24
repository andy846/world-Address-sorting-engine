"""Offline country-code estimates for list statistics, not postal approval."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
import re
import sqlite3
import unicodedata

from world_address_engine.matching.normalize import normalize_address, normalize_key
from world_address_engine.matching.retrieve import retrieve_candidates, OccurrenceLimitExceeded
from world_address_engine.data.geonames_builder import normalize_search_key
from world_address_engine.models import AddressRecord

COUNTRY_RULES_VERSION = '2026-10-24.country.4'
RIVAL_RATIO = 0.55
MAX_ADDRESS_CHARS = 10_000


@dataclass(frozen=True, slots=True)
class CountryInference:
    record_no: int
    country_code: str | None
    status: str
    reason: str
    evidence: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()

    def __post_init__(self):
        if self.record_no < 1 or self.status not in {'DETERMINED', 'INFERRED', 'UNRESOLVED'}:
            raise ValueError('invalid country inference')
        if (self.status == 'UNRESOLVED') != (self.country_code is None):
            raise ValueError('country inference status and code disagree')
        if self.country_code is not None and not re.fullmatch('[A-Z]{2}', self.country_code):
            raise ValueError('invalid geographic country code')


# These are geographic spellings, not a conversion of arbitrary ISO tokens.
COUNTRY_ALIASES = {
    'HK': ('Hongkong', 'Hong Kong SAR', '香港特别行政区', '香港特別行政區',
           '中华人民共和国香港特别行政区', '中華人民共和國香港特別行政區'),
    'CN': ('China', 'Mainland China', '中国', '中國', '中华人民共和国',
           '中華人民共和國', 'PR China', 'P.R. China', "People's Republic of China"),
    'GB': ('United Kingdom', 'Great Britain', 'Britain', 'England', 'Scotland',
           'Wales', 'Northern Ireland'),
    'US': ('United States', 'United States of America', 'USA', 'U.S.A.'),
    'MO': ('Macao', 'Macau', '澳门', '澳門', '澳门特别行政区', '澳門特別行政區'),
    'TW': ('Taiwan', '台灣', '臺灣', '台湾', 'Republic of China'),
    'KR': ('South Korea', 'Korea South'), 'KP': ('North Korea', 'Korea North'),
    'TP': ('Timor Leste', 'East Timor'), 'VN': ('Vietnam',),
}
SHORT_TAIL_CODES = {'hk': 'HK', 'h k': 'HK', 'kln': 'HK', 'uk': 'GB',
                    'u k': 'GB', 'us': 'US', 'u s': 'US', 'prc': 'CN',
                    'p r c': 'CN'}
HK_AREAS = (
    'kowloon', 'new territories', 'tuen mun', 'yuen long', 'sha tin', 'shatin',
    'tsuen wan', 'kwai chung', 'kwai tsing', 'sai kung', 'tai po', 'taipo',
    'fanling', 'fan ling', 'sheung shui', 'tseung kwan o', 'ma on shan',
    'tin shui wai', 'lantau', 'cheung chau', 'peng chau', 'tung chung',
    'tai wai', 'fo tan', 'tsing yi', 'lam tin', 'kwun tong', 'wong tai sin',
    'kowloon bay', 'san po kong', 'mong kok', 'mongkok', 'yau ma tei',
    'tsim sha tsui', 'sham shui po', 'lai chi kok', 'cheung sha wan',
    'hung hom', 'ho man tin', 'to kwa wan', 'tai kok tsui', 'yau tong',
    'causeway bay', 'wan chai', 'wanchai', 'north point', 'quarry bay',
    'chai wan', 'sai wan ho', 'shau kei wan', 'kennedy town', 'pok fu lam',
    'repulse bay', 'ap lei chau', 'sai ying pun', 'happy valley',
    'chuk yuen', 'lok fu', 'diamond hill', 'sham tseng', 'discovery bay',
    '九龍', '九龙', '新界', '屯門', '屯门', '元朗', '沙田', '荃灣', '荃湾',
    '葵涌', '葵青', '西貢', '西贡', '大埔', '粉嶺', '粉岭', '上水', '將軍澳',
    '将军澳', '馬鞍山', '马鞍山', '天水圍', '天水围', '大嶼山', '大屿山',
    '長洲', '长洲', '坪洲', '東涌', '东涌', '大圍', '大围', '火炭', '青衣',
    '藍田', '蓝田', '觀塘', '观塘', '黃大仙', '黄大仙', '九龍灣', '九龙湾',
    '新蒲崗', '新蒲岗', '旺角', '油麻地', '尖沙咀', '深水埗', '荔枝角',
    '長沙灣', '长沙湾', '紅磡', '红磡', '何文田', '土瓜灣', '土瓜湾', '大角咀',
    '油塘', '銅鑼灣', '铜锣湾', '灣仔', '湾仔', '北角', '鰂魚涌', '鲗鱼涌',
    '柴灣', '柴湾', '西灣河', '西湾河', '筲箕灣', '筲箕湾', '堅尼地城',
    '坚尼地城', '薄扶林', '鴨脷洲', '鸭脷洲', '西營盤', '西营盘', '跑馬地',
    '跑马地', '竹園', '竹园', '樂富', '乐富', '鑽石山', '钻石山',
    '深井', '愉景灣', '愉景湾', '中環', '中环', '半山',
    'sheung wan', 'ngau tau kok', 'ngau chi wan', 'shek kip mei',
    'shek tong tsui', 'wong chuk hang', 'siu sai wan', 'sau mau ping',
    'kam tin', 'pat heung', 'lau fau shan', 'sha tau kok', 'taikoo',
    'tai koo', 'tai hang', 'san tin', 'lok ma chau', 'sai ying pun',
    '上環', '上环', '牛頭角', '牛头角', '牛池灣', '牛池湾', '石硤尾',
    '石塘咀', '黃竹坑', '黄竹坑', '小西灣', '小西湾', '秀茂坪', '錦田',
    '锦田', '八鄉', '八乡', '流浮山', '沙頭角', '沙头角', '太古',
    '大坑', '新田', '落馬洲', '落马洲',
    'shek mun', 'lai king', '石門', '石门', '荔景',
    'tin hau', 'kwai fong', 'kwai hing', 'kwai shing', 'tiu keng leng',
    'so kwun wat', 'ma wan', 'mei foo sun chuen', 'on lok tsuen',
    'clearwater bay', 'clear water bay', 'kln bay', 'symphony bay',
    '天后', '葵芳', '葵興', '葵兴', '葵盛', '調景嶺', '调景岭',
    '掃管笏', '扫管笏', '馬灣', '马湾', '美孚新邨', '安樂村', '安乐村',
    '清水灣', '清水湾',
)
HK_AREAS = tuple(dict.fromkeys((*HK_AREAS, *(name.replace(' ', '')
                            for name in HK_AREAS if ' ' in name))))
CN_REGIONS = (
    '北京', '上海', '天津', '重慶', '重庆', '廣東', '广东', '廣西', '广西',
    '福建', '浙江', '江蘇', '江苏', '山東', '山东', '河北', '河南', '湖北',
    '湖南', '安徽', '江西', '海南', '四川', '貴州', '贵州', '雲南', '云南',
    '陝西', '陕西', '山西', '遼寧', '辽宁', '吉林', '黑龍江', '黑龙江',
    '甘肅', '甘肃', '青海', '寧夏', '宁夏', '新疆', '西藏', '內蒙古', '内蒙古',
    'beijing', 'shanghai', 'tianjin', 'chongqing', 'guangdong', 'guangxi',
    'fujian', 'zhejiang', 'jiangsu', 'shandong', 'hebei', 'henan', 'hubei',
    'hunan', 'anhui', 'jiangxi', 'hainan', 'sichuan', 'guizhou', 'yunnan',
    'shaanxi', 'shanxi', 'liaoning', 'jilin', 'heilongjiang', 'gansu',
    'qinghai', 'ningxia', 'xinjiang', 'tibet', 'inner mongolia',
    '深圳', '廣州', '广州', '杭州', 'shenzhen', 'guangzhou', 'hangzhou',
    '西安', '中山市', '合肥市', '惠東縣', '惠东县', '陽江市', '阳江市', '南山區', '南山区',
    '广洲市天河区', '廣洲市天河區',
)
_COMPANY = re.compile(
    r'\b(?:ltd|limited|inc|llc|corp|corporation|company|bank|holdings|trading|logistics)\b'
    r'|有限公司|公司|集團|集团|銀行|银行|china\s+(?:mobile|eastern|southern)', re.I)
_ADDRESS = re.compile(r'\d|\b(?:road|street|avenue|lane|flat|floor|block|room)\b|[路街巷弄號号樓楼]', re.I)
_RECIPIENT = re.compile(r'^(?:mr|mrs|ms|miss|dr|prof|attn|attention)\.?\s|^(?:收件人|聯絡人|联系人)', re.I)
_STREET_AFTER = re.compile(r'^\s*(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)\b|^\s*[東东西南北中]?\s*[街路巷弄]', re.I)
_STREET_TERM = re.compile(r'\b(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)$|[街路巷弄]$', re.I)
_STREET_ADDRESS = re.compile(
    r'^\s*\d+[a-z]?\s+.+\b(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)\b', re.I)
_BUILDING_AFTER = re.compile(
    r'^\s*(?:centre|center|building|tower|plaza|house|bank|university|hospital|industrial\s+park)\b'
    r'|^\s*(?:中心|大廈|大厦|大樓|大楼|廣場|广场|銀行|银行|大學|大学|橋|桥)'
    r'|^\s*(?:國際|国际)?(?:商務|商务|商業|商业)(?:大廈|大厦|中心|樓|楼)'
    r'|^\s*(?:工業園|工业园|工業區|工业区)', re.I)
_HK_SHARED_LOCALITIES = frozenset({'sha tau kok', 'shataukok', '沙頭角', '沙头角',
                              'lok ma chau', 'lokmachau', '落馬洲', '落马洲',
                              '沙田', '半山', '中環', '中环'})
_HK_CENTRAL_STREETS = re.compile(
    r'\b(?:des\s+voeux\s+(?:road|rd)|connaught\s+(?:road|rd|place)|'
    r'wing\s+kut\s+(?:street|st)|ice\s+house\s+(?:street|st)|'
    r'wellington\s+(?:street|st)|queen\s+victoria\s+(?:street|st))\b')
_HK_JORDAN_STREETS = re.compile(
    r'\b(?:tak\s+hing|nanking|woosung|woo\s+sung|nathan|canton)\s+(?:street|st|road|rd)\b')
_HK_TST_TAIL = re.compile(r'(?<![a-z])t\.?\s*s\.?\s*t\.?(?![a-z])'
                          r'(?:\s+east)?(?:[\s,]+kl[n]?)?\s*[,.;]*$')
_HK_KL_STREETS = re.compile(
    r'\b(?:nathan\s+(?:road|rd)|argyle\s+(?:street|st)|'
    r'nanking\s+(?:street|st)|granville\s+(?:road|rd)|'
    r'fa\s+yuen\s+(?:street|st)|shing\s+yip\s+(?:street|st)|'
    r'lam\s+hing\s+(?:street|st)|castle\s+peak\s+(?:road|rd)|kwong\s+wa\s+(?:street|st)|'
    r'kwong\s+cheung\s+(?:street|st)|lock\s+(?:road|rd)|'
    r'prince\s+edward\s+(?:road|rd)\s+east)\b')
_HK_NT_STREETS = re.compile(
    r'\b(?:tai\s+lin\s+pai|kwai\s+cheong|cheung\s+tat|kwai\s+fat)\s+(?:road|rd)\b'
    r'|\bkwai\s+fung\s+crescent\b')
_NT_TAIL = re.compile(r'(?<![a-z])n\.?\s*t\.?\s*[,.;]*$')
_UK_POSTCODE_TAIL = re.compile(r'\b(?:gir\s*0aa|[a-z]{1,2}\d[a-z\d]?\s*\d[a-z]{2})\s*[,.;]*$')


def _location_lines(lines):
    result = []
    for index, line in enumerate(lines):
        if _RECIPIENT.search(line):
            continue
        fragments = [part.strip() for part in re.split(r'[,;，；]', line)]
        kept = [part for part in fragments if part and (
            not _COMPANY.search(part) or _STREET_ADDRESS.search(part))]
        if kept:
            result.append((index, ', '.join(kept)))
    return result


def _regional_names(scope, names):
    for name in names:
        for match in re.finditer(_pattern(name), scope):
            suffix = scope[match.end():].split('\n', 1)[0]
            if not (_STREET_AFTER.match(suffix) or _BUILDING_AFTER.match(suffix)):
                yield name
                break


def _regional_match(scope, names):
    return next(_regional_names(scope, names), None) is not None


def _pattern(name):
    name = normalize_key(name)
    if re.search('[a-z]', name):
        return r'(?<![a-z0-9])' + r'[\s.,_-]+'.join(map(re.escape, name.split())) + r'(?![a-z0-9])'
    return re.escape(name)


def _contains(text, name):
    return any(not (_STREET_AFTER.match(line[match.end():]) or
                    _BUILDING_AFTER.match(line[match.end():]))
               for line in text.splitlines() for match in re.finditer(_pattern(name), line))


def _hk_context(lines):
    scope = '\n'.join(line for _i, line in lines)
    if not _ADDRESS.search(scope):
        return False
    if any(_HK_TST_TAIL.search(line) for _i, line in lines[-2:]):
        return True
    if _contains(scope, 'jordan') and _HK_JORDAN_STREETS.search(scope):
        return True
    if _contains(scope, 'central') and _HK_CENTRAL_STREETS.search(scope):
        return True
    if re.search(r"\bqueen['’]?s\s+(?:road|rd)\s+central\b", scope):
        return True
    if re.search(r'\bdes\s+voeux\s+(?:road|rd)\s+centralhong\s+kong\b', scope):
        return True
    if (_HK_KL_STREETS.search(scope) and
            re.search(r'(?<![a-z])(?:hk\s+)?kl\s*[,.;]*$', lines[-1][1])):
        return True
    if _NT_TAIL.search(scope) and (_HK_NT_STREETS.search(scope) or
                                   _contains(scope, 'kwai chng')):
        return True
    if (_contains(scope, 'aberdeen') and
            re.search(r'\bwong\s+chuk\s+hang\s+(?:road|rd)\b', scope)):
        return True
    if (_contains(scope, 'admiralty') and re.search(r'\bqueenway\b', scope)):
        return True
    if (_contains(scope, 'lippo centre') and re.search(r'\bqueensway\b', scope)):
        return True
    if (_contains(scope, 'the arch') and
            re.search(r'\baustin\s+(?:road|rd)\s+west\b', scope)):
        return True
    if (_contains(scope, 'tsim sha tsui centre') and
            re.search(r'\bmody\s+(?:road|rd)\b', scope)):
        return True
    if (_contains(scope, 'tai po plaza') and lines and
            re.fullmatch(r'n\.?\s*t\.?,?', lines[-1][1])):
        return True
    if (_contains(scope, 'sai wan') and
            re.search(r'\bconnaught\s+(?:road|rd)\s+west\b', scope)):
        return True
    return bool(_contains(scope, 'admiralty') and
                re.search(r'\bqueensway\b', scope))


_WHOLE_REGION = re.compile('(?:' + '|'.join(_pattern(name) for name in (*CN_REGIONS, *HK_AREAS))
                           + r')(?:\s+province|省|市|自治區|自治区)?')


class CountryClassifier:
    """Reusable, bounded estimator; catalogue codes have their own namespace."""
    rules_version = COUNTRY_RULES_VERSION

    def __init__(self, geo_db: Path, catalogue=None):
        if catalogue is None:
            from world_address_engine.data.country_codes import load_country_codes
            catalogue = load_country_codes()
        self.geo_db = Path(geo_db)
        if not self.geo_db.is_file():
            raise FileNotFoundError(self.geo_db)
        self.catalogue = catalogue
        self._cache = OrderedDict()
        self._db = None
        self._names = []
        for code, entry in catalogue.entries.items():
            aliases = (entry.name_en, entry.name_tc, *entry.aliases, *COUNTRY_ALIASES.get(code, ()))
            seen = set()
            for name in aliases:
                for variant in normalize_address(name):
                    if len(variant) >= 2 and variant not in seen:
                        self._names.append((code, variant, re.compile(_pattern(variant))))
                        seen.add(variant)
        self._names.sort(key=lambda item: -len(item[1]))
        self._whole_aliases = frozenset(alias for _code, alias, _pattern in self._names)

    def _eligible_lines(self, lines):
        locations = _location_lines(lines)
        if len(lines) == 1:
            return locations
        start = next((i for i, line in locations if _ADDRESS.search(line)), len(lines))
        result = []
        for i, line in locations:
            plain = line.strip(' ,.;:/()-')
            whole_region = _WHOLE_REGION.fullmatch(plain)
            # A leading name block can contain untitled recipients after a
            # company header. Only whole geographic headings survive it.
            if i < start and plain not in self._whole_aliases and not whole_region:
                short = re.sub(r'[\s.,-]+', ' ', plain).strip()
                if short not in SHORT_TAIL_CODES:
                    latin_name = bool(re.fullmatch(r'[a-z]+(?:\s+[a-z]+){1,2}', plain))
                    ends_in_country = any(plain.endswith(' ' + alias)
                                          for alias in self._whole_aliases)
                    if i == 0 or (latin_name and ends_in_country):
                        continue
            result.append((i, line))
        return result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None
        self._cache.clear()

    def classify(self, record: AddressRecord) -> CountryInference:
        if record.input_error:
            return CountryInference(record.record_no, None, 'UNRESOLVED', record.input_error)
        if len(record.address_text) + len(record.country_hint or '') > MAX_ADDRESS_CHARS:
            return CountryInference(record.record_no, None, 'UNRESOLVED', 'ADDRESS_TOO_LONG')
        key = (record.address_text, record.country_hint)
        value = self._cache.get(key)
        if value is None:
            value = self._infer(*key)
            self._cache[key] = value
            if len(self._cache) > 8192:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)
        return CountryInference(record.record_no, *value)

    def _explicit(self, lines, cleaned=None):
        found = set()
        eligible_lines = self._eligible_lines(lines)
        eligible = {i for i, _line in eligible_lines}
        hk_jordan = (_hk_context(eligible_lines) or
                     any(_contains(line, 'hong kong') or _contains(line, '香港') or
                         re.search(r'(?<![a-z])(?:h\.?\s?k\.?|kln)\s*[,.;]*$', line)
                         for _i, line in eligible_lines))
        jordan_destination = False
        if hk_jordan and any(_contains(line, 'jordan') for _i, line in eligible_lines):
            scope = '\n'.join(line for _i, line in eligible_lines)
            try:
                candidates = self._substantial_candidates(
                    retrieve_candidates(self.geo_db, normalize_address(scope)), scope)
                jordan_destination = any(
                    c.destination_id == 'JO' and any(term not in c.entity_terms
                                                     for term, _weight, _id in c.place_support)
                    for c in candidates)
            except OccurrenceLimitExceeded:
                # Do not withdraw explicit country evidence on an incomplete scan.
                jordan_destination = True
        for index, line in _location_lines(lines):
            territory = re.search(
                r'(?<![a-z])(hong[\s-]*kong|macau|macao|香港|澳門|澳门)(?:\s+sar)?'
                r'[\s,]*(?:china|中国|中國)\s*$', line)
            if territory:
                key = re.sub(r'[\s-]', '', territory[1])
                found.add('HK' if key in {'hongkong', '香港'} else 'MO')
                continue
            if index not in eligible:
                continue
            short = re.sub(r'[\s.,-]+', ' ', line).strip()
            code = SHORT_TAIL_CODES.get(short)
            if code in self.catalogue.entries and index >= max(0, len(lines) - 2):
                found.add(code)
            if index >= max(0, len(lines) - 2):
                tail = re.search(r'(?<![a-z])(?:h\.?\s?k\.?|kln|u\.?\s?k\.?)'
                                 r'(?:\s+[0-9][0-9 -]*)?\s*[,.]*$', line)
                if tail:
                    code = 'GB' if tail[0].startswith('u') else 'HK'
                    if code in self.catalogue.entries:
                        found.add(code)
            spans = []
            blocked = []
            for code, alias, pattern in self._names:
                for match in pattern.finditer(line):
                    if any(left <= match.start() and right >= match.end() for left, right in spans):
                        continue
                    # Inner Mongolia is an administrative name, not Mongolia.
                    if code == 'MN' and (
                        (alias == '蒙古' and line[max(0, match.start() - 1):match.start()] in {'內', '内'}) or
                        (alias == 'mongolia' and re.search(r'\binner\s+$', line[:match.start()]))
                    ):
                        spans.append(match.span())
                        continue
                    suffix = line[match.end():]
                    jordan_local = code == 'JO' and alias == 'jordan' and hk_jordan and not jordan_destination
                    # Lexical names are not separate country occurrences:
                    # New South Wales; 泰国际/德国际; China Hong Kong City.
                    embedded_name = (
                        (alias.endswith(('国', '國')) and suffix.startswith(('际', '際'))) or
                        (code == 'GB' and alias == 'wales' and
                         re.search(r'\bnew\s+south\s+$', line[:match.start()])) or
                        (code == 'CN' and index + 1 < len(lines) and not suffix.strip(' ,.;') and
                         line.strip(' ,.;') != alias and
                         re.search(r'\b(?:tower|building|centre|center|plaza|house)\b', line[:match.start()]) and
                         re.match(r'hong\s+kong\s+city\b', lines[index + 1])) or
                        (code == 'HK' and re.search(r'\bshenzhen\s*-\s*$', line[:match.start()]) and
                         index + 1 < len(lines) and
                         re.search(r'\b(?:workshop|industrial\s+park|centre|center)\b', lines[index + 1]))
                    )
                    # Parent-country prefixes in a single territory expression
                    # must not erase independent country lines elsewhere.
                    territory_suffix = re.match(r'(?:香港|澳門|澳门)', suffix)
                    parent_prefix = (code == 'CN' and territory_suffix and
                                     not (_STREET_AFTER.match(suffix[territory_suffix.end():]) or
                                          _BUILDING_AFTER.match(suffix[territory_suffix.end():])))
                    if parent_prefix:
                        spans.append(match.span())
                        continue
                    if (_STREET_AFTER.match(suffix) or _BUILDING_AFTER.match(suffix) or
                            jordan_local or embedded_name):
                        spans.append(match.span())
                        blocked.append(match.span())
                        continue
                    remainder = line[match.end():].strip(' ,.;:/()-')
                    han = any('\u3400' <= char <= '\u9fff' for char in alias)
                    if index == 0 and len(lines) > 1 and not _ADDRESS.search(line):
                        if line.strip(' ,.;:/()-') != alias:
                            continue
                    if not han and remainder and not re.fullmatch(r'[0-9\s-]+', remainder):
                        continue
                    found.add(code)
                    spans.append(match.span())
            if cleaned is not None and blocked:
                chars = list(line)
                for left, right in blocked:
                    chars[left:right] = ' ' * (right - left)
                cleaned[index] = ''.join(chars)
        return found

    def _infer(self, text, hint):
        lines = [unicodedata.normalize('NFKC', value).casefold().strip()
                 for value in text.splitlines() if value.strip()]
        if not lines and not hint:
            return (None, 'UNRESOLVED', 'EMPTY_ADDRESS', (), ())
        cleaned = {}
        explicit = self._explicit(lines, cleaned)
        if hint:
            hint_key = normalize_key(hint)
            if hint_key.upper() in self.catalogue.entries:
                explicit.add(hint_key.upper())
            else:
                explicit.update(self._explicit([hint_key]))
        if len(explicit) > 1:
            return (None, 'UNRESOLVED', 'CONFLICTING_COUNTRIES', (), tuple(sorted(explicit)))
        if explicit:
            return (next(iter(explicit)), 'DETERMINED', 'EXPLICIT_COUNTRY', (), ())
        if ('returned mail unknown address' in lines and not hint and
                not any(_ADDRESS.search(line) for line in lines)):
            return (None, 'UNRESOLVED', 'RETURNED_MAIL_NO_ADDRESS', (), ())

        # The first line remains available when it is geographic; a recipient
        # or business name is not allowed to supply regional evidence alone.
        eligible_lines = self._eligible_lines(lines)
        address_lines = [cleaned.get(i, line) for i, line in eligible_lines]
        scope = '\n'.join(address_lines)
        cn = _regional_match(scope, CN_REGIONS)
        hk_names = set(_regional_names(scope, HK_AREAS))
        hk = bool(hk_names) or _hk_context(eligible_lines)
        if cn and hk:
            mainland_admin = re.search(r'(?:深圳|廣州|广州|杭州)市|[省市].{0,12}[區区縣县]', scope)
            separate_hk = any(re.fullmatch(_pattern(name), line.strip(' ,.;'))
                              for name in hk_names for line in address_lines)
            if not (mainland_admin and hk_names and hk_names <= _HK_SHARED_LOCALITIES and not separate_hk):
                return (None, 'UNRESOLVED', 'CONFLICTING_ADMINISTRATIVE_REGIONS', (), ('CN', 'HK'))
        if cn and 'CN' in self.catalogue.entries:
            return self._context_result('CN', 'MAINLAND_ADMINISTRATIVE_REGION', address_lines)
        if hk and 'HK' in self.catalogue.entries:
            return self._context_result('HK', 'HONG_KONG_LOCALITY', address_lines)
        if ('GB' in self.catalogue.entries and _contains(scope, 'london') and
                _UK_POSTCODE_TAIL.search(scope)):
            return self._context_result('GB', 'LONDON_POSTCODE_CONTEXT', address_lines)
        if ('KR' in self.catalogue.entries and _contains(scope, 'seoul') and
                re.search(r'\bkorea\s*[,.;]*$', scope)):
            return self._context_result('KR', 'KOREAN_CAPITAL_CONTEXT', address_lines)
        if not scope or not (_ADDRESS.search(scope) or len(lines) > 1):
            return (None, 'UNRESOLVED', 'NO_ADDRESS_CONTEXT', (), ())
        try:
            candidates = retrieve_candidates(self.geo_db, normalize_address(scope))
        except OccurrenceLimitExceeded:
            return (None, 'UNRESOLVED', 'GEOGRAPHIC_OCCURRENCE_LIMIT', (), ())
        candidates = self._substantial_candidates(candidates, scope)
        grouped = {}
        for candidate in candidates:
            code = self.catalogue.geo_to_code.get(candidate.destination_id)
            if code not in self.catalogue.entries:
                continue
            if code not in grouped or candidate.support > grouped[code].support:
                grouped[code] = candidate
        ordered = sorted(grouped, key=lambda code: (-grouped[code].support, code))
        if not ordered:
            return (None, 'UNRESOLVED', 'NO_GEOGRAPHIC_MATCH', (), ())
        leader = ordered[0]
        if len(ordered) > 1 and grouped[ordered[1]].support >= grouped[leader].support * RIVAL_RATIO:
            return (None, 'UNRESOLVED', 'MULTIPLE_PLAUSIBLE_COUNTRIES', (), tuple(ordered[:5]))
        return (leader, 'INFERRED', 'GEOGRAPHIC_LEADER', (), tuple(ordered[:5]))

    def _context_result(self, code, reason, lines):
        """Do not discard an independent, whole-line foreign metropolis.

        Exact indexed keys avoid treating apartment letters, street substrings
        and incidental tiny homonyms as rival city destinations. This only
        withdraws a contextual estimate; it never overrides explicit countries.
        """
        keys = sorted({normalize_search_key(form) for line in lines
                       if not _ADDRESS.search(line)
                       for form in normalize_address(line.strip(' ,.;'))
                       if (len(re.findall(r'[a-z]', form)) >= 4 or
                           len(re.findall(r'[\u3400-\u9fff]', form)) >= 2)})
        rivals = set()
        if keys:
            if self._db is None:
                self._db = sqlite3.connect(self.geo_db.resolve().as_uri() + '?mode=ro', uri=True)
                self._db.execute('PRAGMA query_only=ON')
            for start in range(0, len(keys), 200):
                chunk = keys[start:start + 200]
                rows = self._db.execute(
                    'SELECT DISTINCT p.country_code FROM geo_aliases a '
                    'JOIN geo_places p ON p.place_id=a.place_id '
                    'WHERE a.search_key IN (' + ','.join('?' * len(chunk)) + ') '
                    "AND p.feature_class='P' AND (p.feature_code='PPLC' OR p.population>=1000000)", chunk)
                rivals.update(mapped for country, in rows
                              if (mapped := self.catalogue.geo_to_code.get(country)) in self.catalogue.entries
                              and mapped != code)
        if rivals:
            return (None, 'UNRESOLVED', 'CONFLICTING_GEOGRAPHIC_CONTEXT', (), tuple(sorted({code, *rivals})))
        return (code, 'INFERRED', reason, (), ())

    def _substantial_candidates(self, candidates, scope):
        if not candidates:
            return []
        ids = {place_id for c in candidates for _term, _weight, place_id in c.place_support}
        if not ids:
            return []
        if self._db is None:
            self._db = sqlite3.connect(self.geo_db.resolve().as_uri() + '?mode=ro', uri=True)
            self._db.execute('PRAGMA query_only=ON')
        qualified = {}
        values = sorted(ids)
        for start in range(0, len(values), 200):
            chunk = values[start:start + 200]
            rows = self._db.execute(
                'SELECT place_id,country_code,feature_code,population FROM geo_places '
                'WHERE place_id IN (' + ','.join('?' * len(chunk)) + ')', chunk)
            for place_id, country, feature, population in rows:
                if feature in {'PCLI', 'PCLX', 'PCLS', 'PCLD', 'ADM1', 'ADM2', 'PPLC', 'PPLA'} or (population or 0) >= 100_000:
                    qualified[place_id] = country
        forms = tuple(form for line in scope.splitlines() for form in normalize_address(line))
        roles = {}
        for candidate in candidates:
            for term, _weight, _place_id in candidate.place_support:
                if term not in roles:
                    roles[term] = not _STREET_TERM.search(term) and any(
                        not (_STREET_AFTER.match(line[match.end():]) or
                             _BUILDING_AFTER.match(line[match.end():]))
                        for form in forms for line in form.splitlines()
                        for match in re.finditer(_pattern(term), line))
        results = []
        for candidate in candidates:
            kept = tuple((term, weight, place_id)
                         for term, weight, place_id in candidate.place_support
                         if qualified.get(place_id) == candidate.destination_id and roles[term])
            support = sum(weight for _term, weight, _id in kept)
            if support < 0.15:
                continue
            terms = {term for term, _weight, _id in kept}
            kept_ids = {place_id for _term, _weight, place_id in kept}
            results.append(replace(
                candidate, support=support, score=min(0.99, support),
                token_count=len(kept), place_support=kept,
                term_support=tuple((term, weight) for term, weight, _id in kept),
                entity_terms=tuple(term for term in candidate.entity_terms if term in terms),
                entity_feature_codes=tuple((term, code) for term, code in candidate.entity_feature_codes
                                           if term in terms),
                country_entity=any(weight >= 0.60 for _term, weight, _id in kept),
                evidence=tuple(entry for entry in candidate.evidence
                               if entry.startswith('PLACE:') and int(entry.split(':', 2)[1]) in kept_ids)))
        return results
