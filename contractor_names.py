"""
Resolve spoken/typed contractor names to the messy ThekedaarName strings in PWD.

The catalog is whatever ThekedaarName values exist in the scheme master(s) —
Building, Road, CRF, etc. New firms do not need to be added to TOKEN_MAP:
every DB name is romanized, then English/short queries fuzzy-match that index.
TOKEN_MAP only boosts known aliases (oberoi/oberoy). Ambiguous hits still ask
a fallback question.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

PLACEHOLDERS = {"", "0", "null", "none", "कृपया नाव निवडा", "कृपया नाव निवडा."}

_SCOPED_QUESTION_RE = re.compile(r"(?i)\bQuestion:\s*")
_DEVANAGARI_TOKEN_RE = re.compile(r"[\u0900-\u097F]+")

PREFIX_RE = re.compile(
    r"^(मे\.?|श्री\.?|श्रीमती\.?|मेसर्स\.?|messrs\.?|m/?s\.?)\s*",
    re.IGNORECASE,
)


def unwrap_scoped_question(text):
    """Drop 'Office: ... Question:' wrappers so name extraction sees the real ask."""
    if not text:
        return ""
    match = _SCOPED_QUESTION_RE.search(text)
    if match:
        return text[match.end():].strip()
    return text.strip()

# English / initials → Devanagari tokens that actually appear in ThekedaarName
TOKEN_MAP = {
    "kothari": "कोठारी",
    "oberoi": "ओबेरॉय",
    "oberoy": "ओबेरॉय",
    "sharma": "शर्मा",
    "mangalam": "मंगलम",
    "infra": "इन्फ्रा",
    "infrastructure": "इन्फ्रास्ट्रक्चर",
    "construction": "कंन्स्ट्रक्शन",
    "constructon": "कंन्स्ट्रक्शन",
    "engineers": "इंजिनिअर्स",
    "engineer": "इंजिनिअर्स",
    "prabh": "प्रभ",
    "prabha": "प्रभ",
    "hanuman": "हनुमान",
    "hanumanji": "हनुमानजी",
    "gurukul": "गुरुकुल",
    "jyoti": "ज्योती",
    "deshmukh": "देशमुख",
    "bajaj": "बजाज",
    "jadhav": "जाधव",
    "khandelwal": "खंडेलवाल",
    "agrawal": "अग्रवाल",
    "agarwal": "अग्रवाल",
    "thokale": "ठोकळ",
    "thokal": "ठोकळ",
    "bindra": "विंद्रा",
    "vindra": "विंद्रा",
    "sadguru": "सदगुरु",
    "swami": "स्वामी",
    "samarth": "समर्थ",
    "chaitanya": "चैतन्य",
    "brahma": "ब्रम्ह",
    "bramha": "ब्रम्ह",
    "tale": "ताले",
    "thakur": "ठाकुर",
    "malani": "मालाणी",
    "malpani": "मालपाणी",
    "dube": "दुबे",
    "dubey": "दुबे",
    "gulabchand": "गुलाबचंद",
    "vivek": "विवेक",
    "khanderao": "खंडेराव",
    "gitesh": "गितेश",
    "swapnil": "स्वप्निल",
    "mukesh": "मुकेश",
    "kambe": "कांबे",
    "sharda": "शारदा",
    "nanded": "नांदेड",
    "weva": "वेव्हा",
    "veva": "वेव्हा",
    "infratech": "इंन्फ्राटेक",
    "yogiraj": "योगीराज",
    "rajrajeshwar": "राजराजेश्वर",
    "rajeswar": "राजराजेश्वर",
    "kashelani": "काशेलानी",
    "thotange": "थोटांगे",
    "chandak": "चांडक",
    "shubham": "शुभम",
    "juneid": "जुनेद",
    "javed": "जुनेद",
    "ashutosh": "आशुतोष",
    "vindra": "विंद्रा",
    "pnc": "पी.एन.सी",
    "kashlani": "काशेलानी",
    "a.m": "ए.एम",
    "a.m.": "ए.एम",
    "y.d": "वाय.डी",
    "y.d.": "वाय.डी",
    "c.r": "सी.आर",
    "c.r.": "सी.आर",
    "g.h": "जि.एच",
    "g.h.": "जि.एच",
    "b.t": "बी.टी",
    "b.t.": "बी.टी",
    "n.s": "एन.एस",
    "n.s.": "एन.एस",
    "b.b": "बि.बि",
    "b.b.": "बि.बि",
    "v.b": "व्ही.बी",
    "s.d": "एस.डी",
    "s.l": "एस.एल",
    "g.s": "जी.एस",
    "jv": "जे.व्ही",
    "j.v": "जे.व्ही",
}

# Short Latin initials — only used when a surname/firm token is also present
INITIAL_MAP = {
    "am": "ए.एम",
    "yd": "वाय.डी",
    "cr": "सी.आर",
    "gh": "जि.एच",
    "bt": "बी.टी",
    "ns": "एन.एस",
    "bb": "बि.बि",
    "vb": "व्ही.बी",
    "sd": "एस.डी",
    "sl": "एस.एल",
    "gs": "जी.एस",
}

STOPWORDS = {
    "which", "who", "are", "is", "the", "on", "in", "of", "for", "a", "an", "and",
    "working", "work", "works", "contractor", "contractors", "building", "buildings",
    "road", "roads", "district", "akola", "washim", "buldhana", "khamgaon", "list",
    "tell", "me", "i", "looking", "find", "search", "about", "show", "give", "names",
    "name", "please", "how", "many", "all", "does", "do", "did", "have", "has", "had",
    "name", "please", "how", "many", "all", "category", "budget", "office", "question",
    "with", "from", "under", "completed", "progress", "tender", "stage", "annuity",
    "nabard", "nonplan", "residential", "details", "info", "information",
    "total", "count", "number", "records", "record", "rows", "row", "there", "their",
    "कोणते", "कोणता", "कोणती", "कोण", "काम", "कामे", "करत", "करतात", "आहेत", "आहे", "इमारत",
    "इमारती", "इमारतींवर", "जिल्हा", "जिल्ह्यातील", "ठेकेदार", "ठेकेदारांची",
    "ठेकेदारांचे", "ठेकेदारांचा", "कंत्राटदार", "कॉन्ट्रॅक्टर", "कॉन्ट्रेक्टर",
    "नावे", "सांगा", "रस्ता", "रस्ते", "रस्त्यांच्या", "कामांसाठी", "वरील",
    "कामांची", "कामांचे", "कामांचा", "कामांच्या", "कामाचे", "कामाचा", "कामां",
    "ठेकेदाराची", "ठेकेदाराचे", "ठेकेदाराचा", "ठेकेदाराच्या", "ठेकेदाराने",
    "पूर्ण", "प्रगतीत", "अकोला", "वाशिम", "बुलढाणा",
    "एकूण", "एकुण", "संख्या", "किती", "ची", "चे", "चा", "च्या", "नोंदी", "नोंद",
    "माहिती", "डेटाबेस", "database", "db",
    "thekedar", "thekedaar", "thekedars", "tekedar", "tekedaar",
    "dya", "de", "mala", "मला", "द्या", "दे", "sanga", "count",
    "kiti", "ahet", "aahet", "ahe", "aahe", "aheta", "aaheta",
    "नावाने", "नावाचे", "नावाचा", "नावाची", "नावाच्या", "नाव",
    "कोणी", "कुणी", "का", "असेल", "असतील", "असतात", "नसलेला",
    "named", "anyone", "someone", "somebody", "called", "exist", "exists",
    "existing", "any", "please", "whether",
    "प्रत्येक", "प्रत्येकी", "प्रत्येकाने", "each", "every", "per", "separately",
    "वेगवेगळ", "वेगवेगळ्या", "जाणून", "घ्यायची", "घ्यायचे", "पाहिजे", "हवी", "हवे",
    "कामाची", "बिल्डिंग", "रोड", "नाबार्ड", "इमारतींची",
    "types", "type", "प्रकार", "etc", "इत्यादी", "वगैरे", "like", "scheme", "schemes",
}

# Same DB field (ThekedaarName): English "contractor", Roman "thekedar", Marathi "ठेकेदार".
CONTRACTOR_TERM_HINTS = (
    "contractor", "contractors", "thekedar", "thekedaar", "thekedars", "tekedar", "tekedaar",
    "ठेकेदार", "ठेकेदारां", "ठेकेदारांची", "ठेकेदारांचे", "ठेकेदारांचा", "ठेकेदारांच्या",
    "कंत्राटदार", "कॉन्ट्रॅक्टर", "कॉन्ट्रेक्टर",
)

_COUNT_PHRASES = (
    "how many", "number of", "count of", "total number", "total contractors",
    "count contractors", "how many contractors", "give me the number", "give number",
    "thekedar kiti", "contractor kiti", "kiti ahet", "kiti aahet",
    "किती", "संख्या", "एकूण", "एकुण", "गणना", "मोजा",
    "ची संख्या", "चे एकूण", "चा एकूण", "किती आहेत", "किती नावे", "किती नोंद",
    "एकूण किती", "एकूण कॉन्ट्रॅक्टर", "एकूण ठेकेदार", "एकूण कंत्राटदार",
    "ठेकेदारांची संख्या", "ठेकेदार किती", "कॉन्ट्रॅक्टरची संख्या", "contractor count",
)

_ENTITY_COUNT_HINTS = (
    "table", "record", "records", "rows", "works", "work",
    "टेबल", "नोंद", "नोंदी", "काम", "कामे",
)

_EXISTENCE_PHRASES = (
    "आहे का", "आहेत का", "कोणी आहे", "कोणता आहे", "कोणते आहे", "कोणी कॉन्ट्रॅक्टर",
    "नावाने कोणी", "नावाने कोणता", "नावाने कोणते",
    "is there", "are there", "anyone named", "anybody named", "any contractor",
    "do we have", "does anyone", "does there", "exist", "exists",
)


def mentions_contractors(text):
    """True if the question refers to contractors in English, Roman, or Marathi."""
    if not text:
        return False
    ql = text.lower()
    for term in CONTRACTOR_TERM_HINTS:
        if _DEVANAGARI_RE.search(term):
            if term in text:
                return True
        elif term.lower() in ql:
            return True
    return False


def is_existence_question(question):
    """True for 'is there a contractor named X' / 'नावाने कोणी आहे का'."""
    q = unwrap_scoped_question(question)
    if not q or is_aggregate_count_question(q):
        return False
    ql = q.lower()
    return any(phrase in q or phrase in ql for phrase in _EXISTENCE_PHRASES)


_NAME_CASE_SUFFIXES = ("च्या", "ची", "चे", "चा", "ने", "ना", "ला")


def stem_marathi_token(token):
    """कोठारीच्या / कोठारीची → कोठारी so genitive questions still match the catalog."""
    if not token or not _DEVANAGARI_RE.search(token):
        return token
    for suffix in _NAME_CASE_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _is_noise_token(token):
    if not token:
        return True
    if token in STOPWORDS or token.lower() in STOPWORDS:
        return True
    if token in WEAK_TOKENS:
        return True
    for term in CONTRACTOR_TERM_HINTS:
        if token == term or token.lower() == term.lower():
            return True
    return False


def harvest_name_tokens(question):
    """Distinctive surname/firm tokens from a spoken question (Marathi or English)."""
    q = unwrap_scoped_question(question)
    tokens = []
    for raw in _DEVANAGARI_TOKEN_RE.findall(q or ""):
        tok = stem_marathi_token(raw)
        if len(tok) >= 3 and not _is_noise_token(tok) and not _is_noise_token(raw):
            tokens.append(tok)
    fragment = extract_name_query(q)
    if fragment:
        for raw in _DEVANAGARI_TOKEN_RE.findall(fragment):
            tok = stem_marathi_token(raw)
            if len(tok) >= 3 and not _is_noise_token(tok):
                tokens.append(tok)
    for mapped in transliterate_query(q):
        if mapped and not _is_noise_token(mapped) and len(mapped) >= 3:
            tokens.append(mapped)
    return list(dict.fromkeys(tokens))

WEAK_TOKENS = {
    "कंन्स्ट्रक्शन",
    "कंस्ट्रक्शन",
    "इन्फ्रा",
    "कंपनी",
    "प्रा.लि",
    "जे.व्ही",
    "अकोला",
    "अमरावती",
}


def is_placeholder(name):
    if name is None:
        return True
    stripped = str(name).strip()
    return stripped.lower() in PLACEHOLDERS or stripped in PLACEHOLDERS


def strip_prefixes(name):
    text = (name or "").strip()
    previous = None
    while previous != text:
        previous = text
        text = PREFIX_RE.sub("", text).strip()
    return text


def normalize_key(name):
    text = strip_prefixes(name)
    text = text.replace("कंन्स्ट्रक्शन", "कंस्ट्रक्शन")
    text = text.replace("कपंनी", "कंपनी")
    text = text.replace("बींद्रा", "विंद्रा")
    text = text.replace("बी.बी", "बि.बि")
    text = text.replace("जे.व्हि", "जे.व्ही")
    text = text.replace("जेव्ही", "जेव्ही")
    text = re.sub(r"[\s,.\-()]+", "", text)
    return text


_CONSONANTS = {
    "क्ष": "ksh", "ज्ञ": "dny", "श्र": "shr",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ॲ": "e", "ऑ": "o",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "i", "ु": "u", "ू": "u",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o",
}
_NASALS = {"ं": "n", "ँ": "n", "ः": "h"}
_VIRAMA = "्"
_LATIN_WEAK = {
    "construction", "constructon", "infra", "infrastructure", "company",
    "engineers", "engineer", "akola", "amravati", "nanded", "jv", "and",
}


def fold_latin(text):
    s = re.sub(r"[^a-z]", "", (text or "").lower())
    s = s.replace("aa", "a").replace("ee", "i").replace("oo", "u")
    s = s.replace("w", "v").replace("oi", "oy").replace("ph", "f")
    return s


def romanize(name):
    """Devanagari (and mixed) ThekedaarName → latin so English queries can hit new firms."""
    text = strip_prefixes(name)
    out = []
    i = 0
    length = len(text)
    while i < length:
        if text[i] in " \t,.-()/'\"&+":
            i += 1
            continue
        two = text[i:i + 2]
        cons = _CONSONANTS.get(two) if len(two) == 2 else None
        consumed = 2 if cons else 1
        if not cons:
            cons = _CONSONANTS.get(text[i])
            consumed = 1
        if cons:
            i += consumed
            if i < length and text[i] == _VIRAMA:
                out.append(cons)
                i += 1
                continue
            if i < length and text[i] in _MATRAS:
                out.append(cons + _MATRAS[text[i]])
                i += 1
            else:
                out.append(cons + "a")
            if i < length and text[i] in _NASALS:
                out.append(_NASALS[text[i]])
                i += 1
            continue
        if text[i] in _INDEPENDENT_VOWELS:
            out.append(_INDEPENDENT_VOWELS[text[i]])
            i += 1
            if i < length and text[i] in _NASALS:
                out.append(_NASALS[text[i]])
                i += 1
            continue
        if text[i] in _MATRAS:
            out.append(_MATRAS[text[i]])
            i += 1
            continue
        if text[i] in _NASALS:
            out.append(_NASALS[text[i]])
            i += 1
            continue
        if text[i].isascii() and text[i].isalnum():
            out.append(text[i].lower())
        i += 1
    roman = "".join(out)
    if roman.endswith("a") and len(roman) > 4:
        roman = roman[:-1]
    return fold_latin(roman)


def _latin_tokens(question):
    return re.findall(r"[A-Za-z.]+", question or "")


def is_aggregate_count_question(question):
    """True for how-many / total-count questions in any language — not a named contractor lookup."""
    if not question:
        return False
    q = unwrap_scoped_question(question).strip()
    ql = q.lower()
    if not any(phrase in q or phrase in ql for phrase in _COUNT_PHRASES):
        return False
    if mentions_contractors(q) or any(h in q or h in ql for h in _ENTITY_COUNT_HINTS):
        return True
    # Bare "किती" / "how many" with no entity still counts as aggregate, not a firm name.
    if "किती" in q or "how many" in ql or "count" in ql:
        return True
    return False


def extract_name_query(question):
    """Leftover tokens after stripping question boilerplate — the likely contractor mention."""
    if not question:
        return ""
    q = unwrap_scoped_question(question)
    leftover = []
    for raw in re.split(r"[\s,]+", q):
        token = raw.strip(" ?.,;:\"'")
        if not token or token.isdigit():
            continue
        if token.lower() in STOPWORDS or token in STOPWORDS:
            continue
        leftover.append(stem_marathi_token(token))
    return " ".join(leftover).strip()


def transliterate_query(question):
    """Turn English tokens into Devanagari fragments that exist in ThekedaarName."""
    pieces = []
    lower = (question or "").lower()
    # longer keys first so "a.m." wins over "am"
    for english, marathi in sorted(TOKEN_MAP.items(), key=lambda item: -len(item[0])):
        if re.search(r"(?<![a-z])" + re.escape(english) + r"(?![a-z])", lower):
            if marathi not in pieces:
                pieces.append(marathi)
    for token in _latin_tokens(question):
        mapped = TOKEN_MAP.get(token.lower().rstrip("."))
        if mapped and mapped not in pieces:
            pieces.append(mapped)
    has_firm_token = any(tok not in WEAK_TOKENS and len(tok) >= 3 for tok in pieces)
    has_weak_firm = any(tok in WEAK_TOKENS for tok in pieces)
    if has_firm_token or has_weak_firm:
        for token in _latin_tokens(question):
            mapped = INITIAL_MAP.get(token.lower().rstrip("."))
            if mapped and mapped not in pieces:
                pieces.append(mapped)
    return pieces


def looks_like_name_mention(question):
    """True when the user named a firm/person, not just 'which contractors in Akola'."""
    q = unwrap_scoped_question(question)
    if harvest_name_tokens(q):
        return True
    fragment = extract_name_query(q)
    if is_aggregate_count_question(q):
        return False
    if not fragment:
        return False
    if fragment.lower() in _LATIN_WEAK:
        return False
    tokens = transliterate_query(q)
    if any(tok not in WEAK_TOKENS and len(tok) >= 3 for tok in tokens):
        return True
    if _DEVANAGARI_RE.search(fragment):
        return True
    leftover = [
        tok for tok in _latin_tokens(fragment)
        if fold_latin(tok) and fold_latin(tok) not in _LATIN_WEAK and len(fold_latin(tok)) >= 3
    ]
    return bool(leftover)


def cluster_names(names):
    groups = {}
    for name in names:
        if is_placeholder(name):
            continue
        key = normalize_key(name) or name
        groups.setdefault(key, []).append(name)
    return groups


def _score_name(search_text, distinctive_tokens, weak_tokens, latin_tokens, latin_hay, name):
    if is_placeholder(name):
        return 0.0
    hay = name
    hay_key = normalize_key(name)
    needle_key = normalize_key(search_text)
    score = 0.0
    hits = list(dict.fromkeys(token for token in distinctive_tokens if token and token in hay))
    if hits:
        score = max(score, 0.86 + 0.08 * min(len(hits) - 1, 3))
    if needle_key and needle_key in hay_key and len(needle_key) >= 4:
        score = max(score, 0.9)
    if search_text and search_text in hay:
        score = max(score, 0.95)
    if needle_key and hay_key and _DEVANAGARI_RE.search(search_text or ""):
        score = max(score, SequenceMatcher(None, needle_key, hay_key).ratio())
    latin_needle = fold_latin(search_text)
    if latin_hay:
        latin_hits = [tok for tok in latin_tokens if len(tok) >= 4 and tok in latin_hay]
        if latin_hits:
            score = max(score, 0.86 + 0.08 * min(len(latin_hits) - 1, 3))
        if latin_needle and len(latin_needle) >= 4 and latin_needle in latin_hay:
            score = max(score, 0.92)
        elif latin_needle and len(latin_needle) >= 4:
            ratio = SequenceMatcher(None, latin_needle, latin_hay).ratio()
            if ratio >= 0.78:
                score = max(score, ratio * 0.95)
    if score:
        for token in weak_tokens:
            if token and token in hay:
                score = min(1.0, score + 0.08)
        for tok in latin_tokens:
            if tok in _LATIN_WEAK and tok and tok in (latin_hay or ""):
                score = min(1.0, score + 0.06)
    return score


def resolve_contractor(question, names):
    """
    Return:
      action: none | match | clarify
      values: exact ThekedaarName strings to put in SQL IN (...)
      candidates: close name variants (existence questions can use all of these)
      options: unique display names when the user must pick
      fragment: what we searched for
    """
    q = unwrap_scoped_question(question)
    if is_aggregate_count_question(q) and not harvest_name_tokens(q):
        return {"action": "none", "values": [], "candidates": [], "options": [], "fragment": ""}
    names = [n for n in (names or []) if not is_placeholder(n)]
    fragment = extract_name_query(q)
    harvested = harvest_name_tokens(q)
    mr_tokens = transliterate_query(q)
    if fragment:
        mr_tokens.extend(transliterate_query(fragment))
        if _DEVANAGARI_RE.search(fragment):
            mr_tokens.extend(_DEVANAGARI_TOKEN_RE.findall(strip_prefixes(fragment)))
    mr_tokens.extend(harvested)
    mr_tokens = list(dict.fromkeys(
        tok for tok in mr_tokens if tok and not _is_noise_token(tok)
    ))
    distinctive = list(dict.fromkeys(
        tok for tok in mr_tokens if tok not in WEAK_TOKENS and len(tok) >= 3
    ))
    if not distinctive and fragment and not _DEVANAGARI_RE.search(fragment):
        # "construction" alone is too generic
        if not fragment or fragment.lower() in {"construction", "infra", "company"}:
            return {"action": "none", "values": [], "candidates": [], "options": [], "fragment": ""}
    if not fragment and not distinctive:
        return {"action": "none", "values": [], "candidates": [], "options": [], "fragment": ""}

    search_tokens = distinctive or mr_tokens
    weak_tokens = [tok for tok in mr_tokens if tok in WEAK_TOKENS]
    search_blob = " ".join(harvested) if harvested else (fragment or " ".join(search_tokens))
    latin_tokens = [
        fold_latin(tok) for tok in _latin_tokens(fragment or q)
        if fold_latin(tok) and fold_latin(tok) not in _LATIN_WEAK and len(fold_latin(tok)) >= 3
    ]
    latin_index = {name: romanize(name) for name in names}
    scored = []
    seen = set()
    for name in names:
        score = 0.0
        for token in search_tokens:
            score = max(
                score,
                _score_name(
                    token, [token], weak_tokens, latin_tokens, latin_index.get(name, ""), name
                ),
            )
        score = max(
            score,
            _score_name(
                search_blob, search_tokens, weak_tokens, latin_tokens, latin_index.get(name, ""), name
            ),
        )
        if score < 0.55:
            continue
        key = normalize_key(name)
        if key in seen:
            continue
        seen.add(key)
        scored.append((score, key, name))
    scored.sort(key=lambda item: item[0], reverse=True)

    empty = {
        "action": "clarify",
        "values": [],
        "candidates": [],
        "options": [],
        "fragment": fragment or search_blob,
        "reason": "no_match",
    }
    if not scored:
        return empty

    best_score, best_key, best_name = scored[0]
    close = [item for item in scored if best_score - item[0] <= 0.12][:8]
    groups = cluster_names(names)
    similar = [
        item for item in close
        if SequenceMatcher(None, best_key, item[1]).ratio() >= 0.78
    ]
    rivals = [
        item for item in close
        if SequenceMatcher(None, best_key, item[1]).ratio() < 0.78
    ]
    can_match = False
    if not rivals and similar and similar[0][0] >= 0.72:
        can_match = True
    elif similar and rivals and similar[0][0] >= 0.85 and (similar[0][0] - rivals[0][0] >= 0.07):
        can_match = True

    def _variants_for(items):
        variants = []
        for score, key, name in items:
            for raw in groups.get(key) or [name]:
                if raw not in variants:
                    variants.append(raw)
        return variants

    candidate_values = _variants_for(close)
    if can_match:
        variants = _variants_for(similar)
        for token in search_tokens:
            if len(token) < 4 or token in WEAK_TOKENS:
                continue
            for name in names:
                if token in name and name not in variants:
                    other_key = normalize_key(name)
                    if SequenceMatcher(None, best_key, other_key).ratio() >= 0.78:
                        variants.append(name)
                        if name not in candidate_values:
                            candidate_values.append(name)
        return {
            "action": "match",
            "values": variants,
            "candidates": candidate_values or variants,
            "options": [],
            "fragment": fragment or search_blob,
            "canonical": best_name,
        }

    options = []
    for score, key, name in close:
        label = strip_prefixes(name) or name
        if label not in options:
            options.append(label)
    return {
        "action": "clarify",
        "values": [],
        "candidates": candidate_values,
        "options": options[:6],
        "fragment": fragment or search_blob,
        "reason": "ambiguous",
    }


def clarification_message(resolution, language="en"):
    fragment = resolution.get("fragment") or "that name"
    options = resolution.get("options") or []
    if language == "mr":
        if not options:
            return (
                f"डेटाबेसमध्ये «{fragment}» या नावाने ठेकेदार सापडला नाही. "
                "कृपया मराठीत नाव सांगा (उदा. कोठारी, ओबेरॉय, मंगलम) किंवा मे.ए.एम.कोठारी सारखे पूर्ण नाव लिहा."
            )
        lines = "\n".join(f"{i}. {name}" for i, name in enumerate(options, 1))
        return (
            f"«{fragment}» शी जुळणारे एकापेक्षा जास्त ठेकेदार आहेत. कोणता हवा?\n{lines}"
        )
    if not options:
        return (
            f"I could not find a contractor matching “{fragment}” in the database. "
            "Names are stored in Marathi (e.g. मे.ए.एम.कोठारी). Try Kothari, Oberoi, Mangalam, "
            "or paste the Marathi name."
        )
    lines = "\n".join(f"{i}. {name}" for i, name in enumerate(options, 1))
    return (
        f"I found more than one contractor matching “{fragment}”. Which one should I use?\n{lines}"
    )
