"""
Word meanings for PWD questions (Marathi / English / mixed).

Function words like प्रत्येक are NOT contractor names. They tell the planner
how to group or search: each/every, count, works, schemes, districts.
"""
from __future__ import annotations

import re

import contractor_names as cn

# Sense tags used by the planner
EACH = "each"
COUNT = "count"
WORKS = "works"
CONTRACTOR = "contractor"
FINANCE = "finance"
EXIST = "exist"
TYPES = "types"
ALL_SCHEMES = "all_schemes"

FUNCTION_LEXICON = {
    "प्रत्येक": EACH,
    "प्रत्येकी": EACH,
    "प्रत्येकाने": EACH,
    "वेगवेगळ": EACH,
    "वेगवेगळ्या": EACH,
    "each": EACH,
    "every": EACH,
    "per": EACH,
    "separately": EACH,
    "किती": COUNT,
    "संख्या": COUNT,
    "एकूण": COUNT,
    "एकुण": COUNT,
    "count": COUNT,
    "number": COUNT,
    "how many": COUNT,
    "काम": WORKS,
    "कामे": WORKS,
    "कामाची": WORKS,
    "कामाचे": WORKS,
    "कामाचा": WORKS,
    "कामांची": WORKS,
    "work": WORKS,
    "works": WORKS,
    "ठेकेदार": CONTRACTOR,
    "कॉन्ट्रॅक्टर": CONTRACTOR,
    "contractor": CONTRACTOR,
    "thekedar": CONTRACTOR,
    "तरतूद": FINANCE,
    "खर्च": FINANCE,
    "आहे का": EXIST,
    "नावाने": EXIST,
    "जाणून": COUNT,
    "घ्यायची": COUNT,
    "पाहिजे": COUNT,
    "हवी": COUNT,
    "मला": None,
    "type": TYPES,
    "types": TYPES,
    "प्रकार": TYPES,
    "योजना": TYPES,
    "schemes": TYPES,
    "scheme": TYPES,
    "category": TYPES,
    "categories": TYPES,
    "etc": ALL_SCHEMES,
    "इत्यादी": ALL_SCHEMES,
    "वगैरे": ALL_SCHEMES,
}

FUNCTION_WORDS = {word for word, sense in FUNCTION_LEXICON.items() if word}

SCHEME_HINTS = (
    (("building", "buildings", "इमारत", "इमारती", "बांधकाम", "बिल्डिंग"), "Building"),
    (("road", "roads", "रोड", "रस्ता", "रस्ते", "रस्त्या", "मार्ग", "sh & dor", "sh and dor"), "Road"),
    (("annuity", "aunty", "अॅन्युइटी", "ॲन्युइटी"), "Annuity"),
    (("nabard", "नाबार्ड"), "NABARD"),
    (("crf", "सीआरएफ"), "CRF"),
    (("nonplan", "gat_a", "नॉन प्लॅन", "नॉनप्लॅन", "गट अ"), "GAT_A"),
    (("gat_d", "गट ड"), "GAT_D"),
    (("gat_fbc", "गट एफ"), "GAT_FBC"),
    (("mla", "amdar", "एमएलए", "आमदार"), "MLA"),
    (("mp", "khasdar", "एमपी", "खासदार"), "MP"),
    (("2515", "gram vikas", "ग्रामविकास"), "2515"),
    (("deposit", "deposite", "ठेव"), "Deposit"),
    (("dpdc", "डीपीडीसी"), "DPDC"),
    (("2059", "nonres", "अनिवासी"), "NonResBuilding"),
    (("2216", "resbuilding", "निवासी इमारत"), "ResBuilding"),
)

SCHEME_LABELS = set()
for hints, _name in SCHEME_HINTS:
    for hint in hints:
        SCHEME_LABELS.add(hint)
        SCHEME_LABELS.add(hint.lower())

NAME_NOISE = FUNCTION_WORDS | SCHEME_LABELS | {
    "जाणून", "घ्यायची", "घ्यायचे", "पाहिजे", "हवी", "हवे", "माहिती",
    "बिल्डिंग", "रोड", "नाबार्ड", "प्रत्येक",
    "types", "type", "प्रकार", "etc", "इत्यादी", "वगैरे", "like",
    "crf", "nabard",
}


def _has(text, needle):
    if not text or not needle:
        return False
    if re.search(r"[\u0900-\u097F]", needle):
        return needle in text
    return needle.lower() in text.lower()


def schemes_mentioned(question):
    """All PWD schemes named in the question, in the order they appear."""
    q = cn.unwrap_scoped_question(question)
    ql = q.lower()
    found = []
    spans = []
    for hints, name in SCHEME_HINTS:
        best = None
        for hint in hints:
            idx = ql.find(hint.lower()) if not re.search(r"[\u0900-\u097F]", hint) else q.find(hint)
            if idx < 0 and hint.lower() in ql:
                idx = ql.find(hint.lower())
            if idx >= 0 and (best is None or idx < best):
                best = idx
        if best is not None and name not in found:
            spans.append((best, name))
    spans.sort()
    for _idx, name in spans:
        if name not in found:
            found.append(name)
    return found


def parse_question(question):
    """Turn a spoken question into slots the planner can act on."""
    q = cn.unwrap_scoped_question(question or "")
    ql = q.lower()
    senses = []
    for word, sense in FUNCTION_LEXICON.items():
        if sense and _has(q, word):
            senses.append((word, sense))

    has_each = any(sense == EACH for _w, sense in senses) or any(
        phrase in q or phrase in ql for phrase in ("प्रत्येक", "each ", "every ", " separately")
    )
    has_types = any(sense == TYPES for _w, sense in senses) or any(
        phrase in ql or phrase in q
        for phrase in ("types of", "type of", "कामांचे प्रकार", "कामाचे प्रकार", "योजनेनुसार")
    )
    has_etc = any(sense == ALL_SCHEMES for _w, sense in senses) or any(
        phrase in ql or phrase in q
        for phrase in (" etc", "etc.", "इत्यादी", "वगैरे", "and so on")
    )
    has_like = " like " in f" {ql} " or "उदा" in q or "जसे" in q
    has_count = any(sense == COUNT for _w, sense in senses) or cn.is_aggregate_count_question(q)
    has_works = any(sense == WORKS for _w, sense in senses) or "कामे" in q or "काम" in q
    has_contractor = any(sense == CONTRACTOR for _w, sense in senses) or cn.mentions_contractors(q)
    has_finance = any(sense == FINANCE for _w, sense in senses)
    has_exist = cn.is_existence_question(q)

    schemes = schemes_mentioned(q)
    name_tokens = [
        tok for tok in cn.harvest_name_tokens(q)
        if tok not in NAME_NOISE and tok.lower() not in NAME_NOISE
    ]

    # "how many types of works like Building, NABARD, CRF etc"
    # = work count for each scheme, not "there are N types".
    breakdown = bool(
        has_each
        or (has_types and (has_works or has_count))
        or (has_etc and (has_works or has_count))
    )
    all_schemes = bool(has_etc or (has_types and (has_like or not schemes)))

    metric = None
    if has_finance:
        metric = "finance"
    elif has_works and not (has_contractor and not has_each and not breakdown):
        metric = "works"
    elif has_contractor:
        metric = "contractors"
    elif has_count and has_works:
        metric = "works"
    elif has_count:
        metric = "contractors" if has_contractor else "works"

    if (has_each or breakdown) and has_count:
        metric = "works" if has_works or has_types or not has_contractor else "contractors"

    return {
        "text": q,
        "each": has_each,
        "breakdown": breakdown,
        "all_schemes": all_schemes,
        "count": has_count,
        "metric": metric,
        "existence": has_exist,
        "schemes": schemes,
        "name_tokens": name_tokens,
        "senses": senses,
    }


def describe(slots, language="en"):
    """Short log line: what each important word meant."""
    bits = []
    for word, sense in slots.get("senses") or []:
        if sense == EACH:
            meaning = "each/every" if language != "mr" else "प्रत्येक (गटाने)"
            bits.append(f"{word} = {meaning}")
        elif sense == COUNT:
            bits.append(f"{word} = count")
        elif sense == WORKS:
            bits.append(f"{word} = works")
        elif sense == TYPES:
            bits.append(f"{word} = scheme type")
        elif sense == ALL_SCHEMES:
            bits.append(f"{word} = all schemes")
    schemes = slots.get("schemes") or []
    if slots.get("all_schemes"):
        bits.append("schemes = all types, with count each")
    elif schemes:
        bits.append("schemes = " + ", ".join(schemes))
    names = slots.get("name_tokens") or []
    if names:
        bits.append("name = " + ", ".join(names))
    if not bits:
        return None
    prefix = "Understood meanings: " if language != "mr" else "शब्दांचा अर्थ: "
    return prefix + "; ".join(bits)
