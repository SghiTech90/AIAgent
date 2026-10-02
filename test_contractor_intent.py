"""Regression tests: count vs named lookup, existence phrasing, query chaining."""
import contractor_names as cn
from agent import _rule_based_plan, build_sql_chain


def test_count_vs_name():
    cases = [
        ("एकूण कॉन्ट्रॅक्टर ची संख्या किती", True, False, ""),
        ("ठेकेदारांची एकूण संख्या किती आहे", True, False, ""),
        ("How many contractors are there?", True, False, ""),
        ("thekedar kiti ahet", True, False, ""),
        ("contractor count in database", True, False, ""),
        ("कोठारी ठेकेदार कोणते काम करतात", False, True, None),
        ("कोठारीच्या कामांची तरतूद किती", True, True, None),
        ("मे.ए.एम.कोठारी", False, True, "मे.ए.एम.कोठारी"),
    ]
    for question, want_agg, want_name, want_fragment in cases:
        assert cn.is_aggregate_count_question(question) == want_agg, question
        assert cn.looks_like_name_mention(question) == want_name, question
        frag = cn.extract_name_query(question)
        if want_fragment is not None:
            assert frag == want_fragment, (question, frag)
        assert cn.resolve_contractor(question, ["मे.ए.एम.कोठारी"])["action"] != "clarify" or want_agg, question


def test_mentions_contractors():
    assert cn.mentions_contractors("ठेकेदार किती")
    assert cn.mentions_contractors("contractor list")
    assert cn.mentions_contractors("thekedar works in Akola")
    assert cn.mentions_contractors("mixed contractor आणि ठेकेदार")
    assert not cn.mentions_contractors("how many roads")


def test_kothari_existence_phrasing():
    questions = [
        "कोठारी नावाने कोणी कॉन्ट्रॅक्टर आहे का",
        "Question: कोठारी नावाने कोणी कॉन्ट्रॅक्टर आहे का",
        "kothari contractor",
        "कोठारी ठेकेदार",
    ]
    catalog = ["मे.ए.एम.कोठारी", "बी.टी. देशमुख", "पी.ऐ.देशमुख"]
    for question in questions:
        assert cn.is_existence_question(question) or "kothari" in question.lower() or question.endswith("ठेकेदार"), question
        assert cn.looks_like_name_mention(question), question
        assert "कोठारी" in cn.harvest_name_tokens(question) or cn.extract_name_query(question).lower() in {"kothari", "कोठारी"}, question
        resolved = cn.resolve_contractor(question, catalog)
        assert resolved["action"] == "match", (question, resolved)
        assert "मे.ए.एम.कोठारी" in resolved["values"], (question, resolved)

    q = "कोठारी नावाने कोणी कॉन्ट्रॅक्टर आहे का"
    assert cn.is_existence_question(q)
    assert cn.extract_name_query(q) == "कोठारी"
    plan = _rule_based_plan(q)
    assert plan and plan["intent"] == "exists_entity", plan
    assert len(plan["tables"]) > 1
    chain = build_sql_chain(q, plan)
    assert len(chain) == 1
    assert chain[0]["intent"] == "exists_entity"


def test_deshmukh_existence_lists_all():
    q = "देशमुख नावाने कोणता कॉन्ट्रॅक्टर आहे का"
    catalog = ["पी.ऐ.देशमुख", "बी.टी. देशमुख", "बी.टी.देशमुख", "सुधीर पी.देशमुख", "मे.ए.एम.कोठारी"]
    assert cn.is_existence_question(q)
    resolved = cn.resolve_contractor(q, catalog)
    assert resolved["action"] == "clarify"
    assert resolved["reason"] == "ambiguous"
    assert len(resolved.get("candidates") or []) >= 2
    plan = _rule_based_plan(q)
    assert plan["intent"] == "exists_entity"


def test_finance_chain_holds_work_ids():
    q = "कोठारीच्या कामांची तरतूद किती"
    plan = _rule_based_plan(q)
    assert plan and plan["intent"] == "finance", plan
    chain = build_sql_chain(q, plan)
    assert len(chain) == 2, chain
    assert chain[0]["hold_as"] == "works"
    assert chain[1]["action"] == "provision_by_work_ids"
    assert chain[1]["bind_from"] == "works"


def test_types_of_works_means_count_per_scheme():
    q = "how many types of works are there like building Nabard CRF etc"
    import meaning
    slots = meaning.parse_question(q)
    assert slots["breakdown"] is True, slots
    assert slots["all_schemes"] is True
    plan = _rule_based_plan(q)
    assert plan["intent"] == "count_works_by_scheme", plan
    assert "Building" in plan["schemes"] and "NABARD" in plan["schemes"] and "CRF" in plan["schemes"]
    assert len(plan["schemes"]) >= 10
    chain = build_sql_chain(q, plan)
    assert len(chain) == len(plan["schemes"])


def test_pratyek_means_each_not_a_name():
    q = "Question: मला प्रत्येक कामाची संख्या जाणून घ्यायची आहे बिल्डिंग रोड नाबार्ड"
    import meaning
    slots = meaning.parse_question(q)
    assert slots["each"] is True
    assert slots["schemes"] == ["Building", "Road", "NABARD"], slots["schemes"]
    assert not slots["name_tokens"], slots["name_tokens"]
    assert cn.looks_like_name_mention(q) is False
    plan = _rule_based_plan(q)
    assert plan["intent"] == "count_works_by_scheme", plan
    assert plan["schemes"] == ["Building", "Road", "NABARD"]
    chain = build_sql_chain(q, plan)
    assert len(chain) == 3
    assert [s["hold_as"] for s in chain] == ["count:Building", "count:Road", "count:NABARD"]


if __name__ == "__main__":
    test_count_vs_name()
    test_mentions_contractors()
    test_kothari_existence_phrasing()
    test_deshmukh_existence_lists_all()
    test_finance_chain_holds_work_ids()
    test_types_of_works_means_count_per_scheme()
    test_pratyek_means_each_not_a_name()
    print("OK: contractor intent, existence phrasing, and query chaining")
