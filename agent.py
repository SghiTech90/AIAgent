import copy
import json
import os
import re
import traceback
from openai import OpenAI
import database
import contractor_names
import meaning

DEFAULT_MODEL = "gpt-4o-mini"


_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def clean_sql(sql_text):
    """
    Extract the raw SQL query from potential markdown formatting or XML tags.
    """
    if not sql_text:
        return ""

    sql_text = re.sub(r'```sql\s*(.*?)\s*```', r'\1', sql_text, flags=re.DOTALL | re.IGNORECASE)
    sql_text = re.sub(r'```\s*(.*?)\s*```', r'\1', sql_text, flags=re.DOTALL)
    sql_text = re.sub(r'<sql>\s*(.*?)\s*</sql>', r'\1', sql_text, flags=re.DOTALL | re.IGNORECASE)
    return sql_text.strip()


def normalize_mssql_unicode_literals(sql_text):
    """
    SQL Server nvarchar + Marathi breaks with LIKE LOWER('पूर्ण').
    Rewrite to equality with a Unicode literal: = N'पूर्ण'.
    """
    if not sql_text:
        return sql_text

    def has_devanagari(text):
        return bool(_DEVANAGARI_RE.search(text))

    sql_text = re.sub(
        r"LIKE\s+LOWER\s*\(\s*N?'([^']*)'\s*\)",
        lambda m: f"= N'{m.group(1)}'" if has_devanagari(m.group(1)) else m.group(0),
        sql_text,
        flags=re.IGNORECASE,
    )
    sql_text = re.sub(
        r"=\s*LOWER\s*\(\s*N?'([^']*)'\s*\)",
        lambda m: f"= N'{m.group(1)}'" if has_devanagari(m.group(1)) else m.group(0),
        sql_text,
        flags=re.IGNORECASE,
    )
    sql_text = re.sub(
        r"LOWER\s*\(\s*N?'([^']*)'\s*\)",
        lambda m: f"N'{m.group(1)}'" if has_devanagari(m.group(1)) else m.group(0),
        sql_text,
        flags=re.IGNORECASE,
    )
    sql_text = re.sub(
        r"LIKE\s+N?'([^'%_]*)'",
        lambda m: f"= N'{m.group(1)}'" if has_devanagari(m.group(1)) else m.group(0),
        sql_text,
        flags=re.IGNORECASE,
    )
    sql_text = re.sub(
        r"(?<![Nn])'([^']*)'",
        lambda m: f"N'{m.group(1)}'" if has_devanagari(m.group(1)) else m.group(0),
        sql_text,
    )
    return sql_text


def call_llm(prompt, system_instruction, model_name, api_key):
    """Call OpenAI with the given prompt."""
    if not api_key:
        raise ValueError("OpenAI API key is required")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def _language_sql_rules(language):
    return (
        "The user question may be in Marathi (मराठी), English, or mixed in one sentence. Understand the intent in any language.\n"
        "contractor / contractors / thekedar (Roman) / ठेकेदार / कंत्राटदार / कॉन्ट्रॅक्टर (spoken) all mean column ThekedaarName — same meaning, different words.\n"
        "SQL identifiers (table/column names) stay English as in the schema; only the user's words vary.\n"
        "Marathi/Hindi nvarchar literals MUST use Unicode equality: Dist = N'अकोला', Sadyasthiti = N'पूर्ण'. Never LIKE LOWER() on Devanagari."
    )


def _language_answer_rules(language):
    if language == "mr":
        return (
            "Write the entire answer in clear administrative Marathi (मराठी).\n"
            "Keep contractor names, work names, Dist, and numbers exactly as in the results.\n"
            "Do not translate proper nouns like ThekedaarName values."
        )
    return "Write the answer in English unless the user clearly used Marathi — then reply in Marathi."


def detect_language(question, requested="en"):
    """Marathi if the user wrote Devanagari, even when the client sent language=en."""
    if requested == "mr":
        return "mr"
    if question and _DEVANAGARI_RE.search(question):
        return "mr"
    return requested or "en"


_SCHEME_HINTS = (
    (("building", "buildings", "इमारत", "इमारती", "बांधकाम", "बिल्डिंग"), "Building"),
    (("road", "roads", "रोड", "रस्ता", "रस्ते", "रस्त्या", "मार्ग", "sh & dor", "sh and dor"), "Road"),
    (("annuity", "aunty", "अॅन्युइटी", "ॲन्युइटी", "अॅन्युइटी"), "Annuity"),
    (("nabard", "नाबार्ड"), "NABARD"),
    (("crf", "सीआरएफ", "सी आर एफ"), "CRF"),
    (("nonplan", "gat_a", "gat a", "नॉन प्लॅन", "नॉनप्लॅन", "गट अ"), "GAT_A"),
    (("gat_d", "gat d", "गट ड"), "GAT_D"),
    (("gat_fbc", "gat fbc", "gat_b", "गट एफ"), "GAT_FBC"),
    (("mla", "amdar", "एमएलए", "आमदार"), "MLA"),
    (("mp", "khasdar", "एमपी", "खासदार"), "MP"),
    (("2515", "gram vikas", "ग्रामविकास", "ग्रामीण विकास"), "2515"),
    (("deposit", "deposite", "ठेव निधी", "ठेव"), "Deposit"),
    (("dpdc", "डीपीडीसी"), "DPDC"),
    (("2059", "nonres", "non-residential", "अनिवासी"), "NonResBuilding"),
    (("2216", "resbuilding", "residential building", "निवासी इमारत"), "ResBuilding"),
)

_DISTRICT_HINTS = (
    (("akola", "अकोला"), ["Akola", "अकोला"]),
    (("washim", "वाशिम"), ["Washim", "वाशिम"]),
    (("buldhana", "बुलढाणा", "बुलधाना"), ["Buldhana", "बुलढाणा"]),
    (("khamgaon", "खामगाव"), ["Khamgaon", "खामगाव"]),
)

def _mentions_contractors(text):
    return contractor_names.mentions_contractors(text)
_COUNT_HINTS = (
    "how many", "number of", "count of", "total number", "count ",
    "किती", "संख्या", "एकूण", "एकुण", "ची संख्या", "एकूण किती",
)
_FINANCE_HINTS = (
    "budget provision", "expenditure", "allotment", "tartud", "remaining amount",
    "तरतूद", "एकूण खर्च", "खर्च किती", "खर्चाची", "अंदाजपत्रक",
    "march ending", "urvarit", "उरलेली रक्कम", "मागणी",
)
_WORK_HINTS = (
    "work id", "workid", "work name", "kamache", "which works", "list of works",
    "कामाचे नाव", "कामांची यादी", "कोणती कामे", "वर्क आयडी",
)
_WORK_LIST_HINTS = (
    "work id", "workid", "work name", "kamache", "which works", "list of works",
    "कामाचे नाव", "कामांची यादी", "कोणती कामे", "त्याची कामे", "त्याच्या कामा",
    "वर्क आयडी", "show works", "his works", "their works", "कामे किती",
)
_STATUS_HINTS = (
    (("पूर्ण झालेल", "पूर्ण झाले", "completed"), "पूर्ण"),
    (("प्रगतीत", "in progress", "inprogress"), "प्रगतीत"),
    (("निविदा स्तर", "tender stage"), "निविदा स्तर"),
    (("अंदाजपत्रकीय स्तर", "estimated stage"), "अंदाजपत्रकीय स्तर"),
    (("सुरु न झाले", "सुरू न झाले", "not started"), "सुरु न झालेली"),
)


def _contains_any(text, words):
    lower = text.lower()
    return any(word.lower() in lower for word in words)


def _scheme_from_label(label):
    if not label:
        return None
    raw = label.strip()
    if raw in database.SCHEME_MASTERS:
        return raw
    aliases = {
        "sh & dor": "Road",
        "road": "Road",
        "रस्ता": "Road",
        "रस्ते": "Road",
        "annuity": "Annuity",
        "aunty": "Annuity",
        "अॅन्युइटी": "Annuity",
        "building": "Building",
        "इमारत": "Building",
        "इमारती": "Building",
        "बांधकाम": "Building",
        "nonplan": "GAT_A",
        "nonplan(3054)": "GAT_A",
        "gat_a": "GAT_A",
        "नॉन प्लॅन": "GAT_A",
        "deposite funds": "Deposit",
        "deposit": "Deposit",
        "ठेव": "Deposit",
        "nonresbuilding": "NonResBuilding",
        "resbuilding": "ResBuilding",
        "नाबार्ड": "NABARD",
        "आमदार": "MLA",
        "खासदार": "MP",
        "ग्रामविकास": "2515",
    }
    return aliases.get(raw.lower()) or aliases.get(raw)


def _provision_table_for_master(master):
    bare = (master or "").split(".")[-1]
    suffix = bare.replace("BudgetMaster", "")
    return f"dbo.{suffix}Provision"


def _budget_year():
    return os.getenv("BUDGET_YEAR", "2025-2026")


def _parse_json_object(text):
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


def _rule_based_plan(question):
    """High-confidence plans for common PWD questions — no extra LLM call."""
    q = question or ""
    ql = q.lower()
    slots = meaning.parse_question(q)

    scheme = None
    cat_match = re.search(r"Budget category:\s*([^.]*)", q, re.I)
    if cat_match:
        scheme = _scheme_from_label(cat_match.group(1))
    schemes = list(slots.get("schemes") or [])
    if scheme and scheme not in schemes:
        schemes.insert(0, scheme)
    if not schemes:
        for hints, name in _SCHEME_HINTS:
            if _contains_any(ql, hints) or _contains_any(q, hints):
                schemes.append(name)
                break
    if slots.get("all_schemes") or (slots.get("breakdown") and not schemes):
        schemes = list(database.SCHEME_MASTERS.keys())
    if schemes:
        scheme = schemes[0]
    table = database.SCHEME_MASTERS.get(scheme) if scheme else None

    if (slots.get("each") or slots.get("breakdown")) and schemes and (
        slots.get("count") or slots.get("breakdown")
    ):
        metric = slots.get("metric") or "works"
        intent = "count_works_by_scheme" if metric != "contractors" else "count_entities_by_scheme"
        count_col = "WorkId" if intent == "count_works_by_scheme" else "ThekedaarName"
        tables = [database.SCHEME_MASTERS[name] for name in schemes if name in database.SCHEME_MASTERS]
        return {
            "confidence": "high",
            "intent": intent,
            "scheme": scheme,
            "schemes": schemes,
            "tables": tables,
            "join_provision": False,
            "distinct": True,
            "count_column": count_col,
            "columns": [count_col],
            "filters": [],
            "exclude_placeholders": intent != "count_works_by_scheme",
            "skip_name_resolution": True,
            "reason": (
                "Types/each = breakdown by scheme, not 'N types'. "
                f"Count {metric} for each of: {', '.join(schemes)}."
            ),
        }

    wants_count_early = contractor_names.is_aggregate_count_question(q)
    wants_contractors_early = _mentions_contractors(q)
    named_early = bool(slots.get("name_tokens")) and contractor_names.looks_like_name_mention(q)
    existence_early = contractor_names.is_existence_question(q)
    wants_finance_early = _contains_any(ql, _FINANCE_HINTS) or _contains_any(q, _FINANCE_HINTS)
    wants_works_early = (
        _contains_any(ql, _WORK_LIST_HINTS)
        or _contains_any(q, _WORK_LIST_HINTS)
        or ("कामे" in q)
    )

    filters_early = []
    for hints, values in _DISTRICT_HINTS:
        if _contains_any(q, hints):
            filters_early.append({"column": "Dist", "values": values})
            break
    status_early = None
    for hints, value in _STATUS_HINTS:
        if _contains_any(q, hints) or _contains_any(ql, hints):
            status_early = value
            break
    if status_early:
        filters_early.append({"column": "Sadyasthiti", "values": [status_early]})

    if named_early:
        named_tables = [table] if table else list(database.SCHEME_MASTERS.values())
        if wants_finance_early:
            provision_tables = [_provision_table_for_master(t) for t in named_tables]
            return {
                "confidence": "high",
                "intent": "finance",
                "scheme": scheme,
                "tables": named_tables + provision_tables,
                "join_provision": True,
                "distinct": False,
                "columns": ["WorkId", "KamacheName", "ThekedaarName", "Tartud", "AikunKharch"],
                "filters": filters_early,
                "exclude_placeholders": True,
                "reason": "Named contractor + money: resolve name, hold WorkIds, then query provision.",
            }
        if existence_early and not wants_works_early:
            return {
                "confidence": "high",
                "intent": "exists_entity",
                "scheme": scheme,
                "tables": named_tables,
                "join_provision": False,
                "distinct": True,
                "columns": ["ThekedaarName"],
                "filters": filters_early,
                "exclude_placeholders": True,
                "reason": "Asked whether a named contractor exists. Search all relevant masters.",
            }
        return {
            "confidence": "high",
            "intent": "work_list",
            "scheme": scheme,
            "tables": named_tables,
            "join_provision": False,
            "distinct": False,
            "columns": ["WorkId", "KamacheName", "ThekedaarName"],
            "filters": filters_early,
            "exclude_placeholders": True,
            "reason": "Named contractor: resolve exact ThekedaarName, then list their works.",
        }

    if wants_count_early and wants_contractors_early and not named_early:
        count_tables = [table] if table else list(database.SCHEME_MASTERS.values())
        return {
            "confidence": "high",
            "intent": "count_entities",
            "scheme": scheme,
            "tables": count_tables,
            "join_provision": False,
            "distinct": True,
            "count_column": "ThekedaarName",
            "columns": ["ThekedaarName"],
            "filters": filters_early,
            "exclude_placeholders": True,
            "reason": "Contractor count across masters when no scheme was named.",
        }

    if not scheme:
        return None

    table = database.SCHEME_MASTERS.get(scheme)
    if not table:
        return None

    dist_values = []
    for hints, values in _DISTRICT_HINTS:
        if _contains_any(q, hints):
            dist_values = values
            break

    wants_contractors = _mentions_contractors(q)
    wants_finance = _contains_any(ql, _FINANCE_HINTS) or _contains_any(q, _FINANCE_HINTS)
    wants_works = _contains_any(ql, _WORK_HINTS) or _contains_any(q, _WORK_HINTS)
    wants_count = (
        contractor_names.is_aggregate_count_question(q)
        or _contains_any(ql, _COUNT_HINTS)
        or _contains_any(q, _COUNT_HINTS)
    )
    named_contractor = contractor_names.looks_like_name_mention(q)
    if named_contractor:
        wants_works = True

    status_value = None
    for hints, value in _STATUS_HINTS:
        if _contains_any(q, hints) or _contains_any(ql, hints):
            status_value = value
            break

    filters = []
    if dist_values:
        filters.append({"column": "Dist", "values": dist_values})
    if status_value:
        filters.append({"column": "Sadyasthiti", "values": [status_value]})

    if wants_count and wants_contractors and not named_contractor and not wants_finance:
        count_tables = [table] if scheme else list(database.SCHEME_MASTERS.values())
        return {
            "confidence": "high",
            "intent": "count_entities",
            "scheme": scheme,
            "tables": count_tables,
            "join_provision": False,
            "distinct": True,
            "count_column": "ThekedaarName",
            "columns": ["ThekedaarName"],
            "filters": filters,
            "exclude_placeholders": True,
            "reason": "Asked for contractor count (English/Marathi). COUNT DISTINCT ThekedaarName.",
        }

    if (wants_contractors or named_contractor) and not wants_finance:
        columns = ["ThekedaarName"]
        if wants_works or named_contractor:
            columns = ["WorkId", "KamacheName", "ThekedaarName"]
        return {
            "confidence": "high",
            "intent": "list_entities" if columns == ["ThekedaarName"] else "work_list",
            "scheme": scheme,
            "tables": [table],
            "join_provision": False,
            "distinct": columns == ["ThekedaarName"],
            "columns": columns,
            "filters": filters,
            "exclude_placeholders": True,
            "reason": "Asked for contractors (English/Marathi). Master table only — no provision join.",
        }

    if wants_finance:
        bare = table.split(".")[-1]
        suffix = bare.replace("BudgetMaster", "")
        provision_table = f"dbo.{suffix}Provision"
        return {
            "confidence": "high",
            "intent": "finance",
            "scheme": scheme,
            "tables": [table, provision_table],
            "join_provision": True,
            "distinct": False,
            "columns": ["WorkId", "KamacheName", "ThekedaarName", "Tartud", "AikunKharch"],
            "filters": filters,
            "exclude_placeholders": False,
            "reason": "Asked for budget/expenditure. LEFT JOIN provision for this-year money only.",
        }

    return None


def plan_question(question, model_name, api_key, logs_callback):
    """Decide intent, table, and columns before writing SQL."""
    slots = meaning.parse_question(question)
    described = meaning.describe(
        slots,
        "mr" if question and _DEVANAGARI_RE.search(question) else "en",
    )
    if described:
        logs_callback(described)

    rule_plan = _rule_based_plan(question)
    if rule_plan:
        logs_callback(f"Step 1: Query plan (rules) — {rule_plan['reason']}")
        return rule_plan

    logs_callback("Step 1: Planning the smallest query that answers the question...")
    system_instruction = (
        "You are the query planner for a PWD AI agent. Questions may be Marathi, English, or mixed.\n"
        "Return ONLY JSON. Pick the smallest table/column set that answers the question.\n"
        "Marathi: ठेकेदार/कंत्राटदार=ThekedaarName; English contractor/thekedar (Roman) = same column. Mixed questions are normal.\n"
        "इमारत=Building, रस्ता=Road, जिल्हा Dist (अकोला=Akola), पूर्ण=Sadyasthiti पूर्ण, तरतूद/खर्च=provision join.\n"
        "'काम करत' means working, not a work-list. Do not join provision unless they asked for तरतूद, खर्च, allotment, expenditure.\n"
        "If they asked which contractors / कोणते ठेकेदार / list thekedars, columns must be only ThekedaarName and distinct=true.\n"
        "If they asked how many / किती / संख्या / count (using contractor OR ठेकेदार OR thekedar), intent=count_entities and COUNT DISTINCT ThekedaarName — not a name lookup.\n"
        "If they asked आहे का / is there a contractor named X, intent=exists_entity, columns only ThekedaarName, distinct=true, all masters unless a scheme was named.\n"
        "If they asked how many types of works / कामांचे प्रकार / like Building NABARD CRF etc, intent=count_works_by_scheme: count WorkId per scheme. Never answer with only 'N types'.\n"
        "If they named a contractor (Kothari, Oberoi, मे.ए.एम.कोठारी), do not invent English spellings — the resolver will supply exact ThekedaarName values."
    )
    prompt = f"""
{database.get_planner_catalog()}

User question: "{question}"

JSON shape:
{{
  "intent": "exists_entity|list_entities|work_list|finance|count_entities|other",
  "scheme": "Building",
  "tables": ["dbo.BudgetMasterBuilding"],
  "join_provision": false,
  "distinct": true,
  "columns": ["ThekedaarName"],
  "filters": [{{"column": "Dist", "values": ["Akola", "अकोला"]}}],
  "exclude_placeholders": true,
  "reason": "short reason"
}}
"""
    try:
        raw = call_llm(prompt, system_instruction, model_name, api_key)
        parsed = _parse_json_object(raw)
        if parsed and parsed.get("tables"):
            parsed["confidence"] = "llm"
            logs_callback(f"Step 1: Query plan (LLM) — {parsed.get('reason', '')}")
            return parsed
    except Exception as exc:
        logs_callback(f"Planner fallback: {exc}")

    logs_callback("Step 1: No tight plan; using focused defaults.")
    return {
        "confidence": "low",
        "intent": "other",
        "scheme": None,
        "tables": [],
        "join_provision": False,
        "distinct": False,
        "columns": [],
        "filters": [],
        "exclude_placeholders": True,
        "reason": "Ambiguous question.",
    }


def _format_query_plan(plan):
    if not plan:
        return "No plan."
    columns = ", ".join(plan.get("columns") or []) or "(keep to the fewest columns that answer the question)"
    tables = ", ".join(plan.get("tables") or []) or "(see schema)"
    join_rule = (
        "LEFT JOIN matching *Provision on WorkId for this-year money only."
        if plan.get("join_provision")
        else "Do NOT join any Provision table. Do NOT select Tartud, AikunKharch, ManjurAmt, or budget columns."
    )
    distinct = "SELECT DISTINCT" if plan.get("distinct") else "SELECT (no DISTINCT unless needed)"
    filters = plan.get("filters") or []
    filter_txt = json.dumps(filters, ensure_ascii=False) if filters else "none unless the user stated a place/status"
    text = (
        f"Intent: {plan.get('intent')}\n"
        f"Scheme: {plan.get('scheme')}\n"
        f"Tables: {tables}\n"
        f"Columns: {columns}\n"
        f"{distinct}\n"
        f"{join_rule}\n"
        f"Filters: {filter_txt}\n"
        f"Exclude placeholder names (कृपया नाव निवडा, 0, blank): {plan.get('exclude_placeholders', True)}\n"
        f"Why: {plan.get('reason')}"
    )
    name_filter = next(
        (item for item in filters if item.get("column") == "ThekedaarName" and item.get("values")),
        None,
    )
    if name_filter:
        names = ", ".join("N'" + str(value).replace("'", "''") + "'" for value in name_filter["values"])
        text += f"\nThekedaarName MUST be one of these exact DB values: {names}"
    return text


def _sql_n(value):
    return "N'" + str(value).replace("'", "''") + "'"


def _escape_like(value):
    text = str(value).replace("'", "''")
    return text.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def _master_tables_from_plan(plan):
    tables = []
    for name in plan.get("tables") or []:
        if not name or "Provision" in name:
            continue
        if name not in tables:
            tables.append(name)
    return tables


def _where_clauses_from_plan(plan):
    clauses = []
    for filt in plan.get("filters") or []:
        column = filt.get("column")
        values = [v for v in (filt.get("values") or []) if v is not None and str(v).strip() != ""]
        if not column or not values:
            continue
        quoted = f"[{column}]"
        literals = ", ".join(_sql_n(v) for v in values)
        if len(values) == 1:
            clauses.append(f"{quoted} = {literals}")
        else:
            clauses.append(f"{quoted} IN ({literals})")
    like_token = (plan.get("name_like") or "").strip()
    has_exact_name = any(
        filt.get("column") == "ThekedaarName" and filt.get("values")
        for filt in (plan.get("filters") or [])
    )
    if like_token and not has_exact_name:
        clauses.append(f"[ThekedaarName] LIKE N'%{_escape_like(like_token)}%'")
    if plan.get("exclude_placeholders"):
        clauses.append(
            "[ThekedaarName] IS NOT NULL AND "
            "LTRIM(RTRIM(CAST([ThekedaarName] AS nvarchar(500)))) "
            "NOT IN (N'', N'0', N'कृपया नाव निवडा')"
        )
    return clauses


def compile_plan_sql(plan):
    """Deterministic T-SQL from a high-confidence plan so names stay exact Unicode."""
    if not plan or plan.get("join_provision"):
        return None
    has_exact_names = any(
        filt.get("column") == "ThekedaarName" and filt.get("values")
        for filt in (plan.get("filters") or [])
    )
    has_like = bool((plan.get("name_like") or "").strip())
    if plan.get("confidence") != "high" and not has_exact_names and not has_like:
        return None
    tables = _master_tables_from_plan(plan)
    if plan.get("intent") in ("count_entities", "count_works") and tables:
        count_col = plan.get("count_column") or "ThekedaarName"
        alias = "contractor_count" if plan.get("intent") == "count_entities" else "work_count"
        wheres = _where_clauses_from_plan(plan)
        where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
        if len(tables) == 1:
            quoted = database._quote_mssql_table(tables[0])
            return (
                f"SELECT COUNT(DISTINCT [{count_col}]) AS {alias} "
                f"FROM {quoted}{where_sql}"
            )
        parts = [
            f"SELECT DISTINCT [{count_col}] AS n FROM {database._quote_mssql_table(table)}{where_sql}"
            for table in tables
        ]
        union = " UNION ".join(parts)
        return f"SELECT COUNT(*) AS {alias} FROM ({union}) AS all_rows"
    columns = plan.get("columns") or []
    if not columns or not tables:
        return None
    col_sql = ", ".join(f"[{col}]" for col in columns)
    distinct = "DISTINCT " if plan.get("distinct") else ""
    top = "" if plan.get("distinct") else "TOP 200 "
    wheres = _where_clauses_from_plan(plan)
    where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
    if len(tables) == 1:
        return f"SELECT {distinct}{top}{col_sql} FROM {database._quote_mssql_table(tables[0])}{where_sql}"
    parts = []
    for table in tables:
        parts.append(
            f"SELECT {col_sql} FROM {database._quote_mssql_table(table)}{where_sql}"
        )
    return f"SELECT {distinct}{top}* FROM ({' UNION ALL '.join(parts)}) AS works"


def _apply_contractor_resolution(question, plan, logs_callback):
    """Map spoken/short names onto exact ThekedaarName values, or prepare a LIKE search."""
    if plan.get("skip_name_resolution"):
        return plan, None
    if not contractor_names.looks_like_name_mention(question):
        return plan, None

    tables = _master_tables_from_plan(plan)
    master_table = tables[0] if len(tables) == 1 else None
    names = database.get_contractor_names(master_table)
    if not names:
        logs_callback("Contractor catalog empty — skipping name resolver.")
        return plan, None

    resolution = contractor_names.resolve_contractor(question, names)
    action = resolution.get("action")
    if action == "none":
        return plan, None

    fragment = resolution.get("fragment") or ""
    existence = (
        plan.get("intent") == "exists_entity"
        or contractor_names.is_existence_question(question)
    )

    if action == "clarify" and resolution.get("reason") == "ambiguous":
        if existence:
            values = resolution.get("candidates") or []
            if values:
                logs_callback(
                    f"Existence check: holding {len(values)} contractor(s) matching '{fragment}'."
                )
                return _attach_name_filter(plan, values, question, logs_callback, fragment), None
        logs_callback(f"Contractor name '{fragment}' is ambiguous — asking which one.")
        return plan, resolution

    if action == "clarify" and resolution.get("reason") == "no_match":
        harvested = contractor_names.harvest_name_tokens(question)
        token = harvested[0] if harvested else fragment
        if token:
            plan = copy.deepcopy(plan)
            plan["name_like"] = token
            plan["exclude_placeholders"] = True
            plan["confidence"] = "high"
            if not plan.get("tables"):
                plan["tables"] = list(database.SCHEME_MASTERS.values())
            logs_callback(
                f"No catalog hit for '{token}'. Holding the fragment and searching ThekedaarName LIKE %...%."
            )
            return plan, None
        logs_callback(f"Contractor name '{fragment}' is missing — asking a fallback question.")
        return plan, resolution

    values = resolution.get("values") or []
    if not values:
        return plan, None

    logs_callback(
        f"Matched contractor '{fragment}' → {resolution.get('canonical') or values[0]} "
        f"({len(values)} stored name variant(s)). Holding exact names for the next query."
    )
    return _attach_name_filter(plan, values, question, logs_callback, fragment), None


def _attach_name_filter(plan, values, question, logs_callback, fragment):
    plan = copy.deepcopy(plan)
    filters = [item for item in (plan.get("filters") or []) if item.get("column") != "ThekedaarName"]
    filters.append({"column": "ThekedaarName", "values": values})
    plan["filters"] = filters
    plan["exclude_placeholders"] = True
    plan["name_like"] = None
    plan["held_names"] = values
    if plan.get("intent") == "list_entities":
        plan["intent"] = "work_list"
        plan["distinct"] = False
        plan["columns"] = ["WorkId", "KamacheName", "ThekedaarName"]
    if not plan.get("tables"):
        plan["tables"] = list(database.SCHEME_MASTERS.values())
        plan["confidence"] = "high"
        if plan.get("intent") in (None, "other"):
            if contractor_names.is_existence_question(question):
                plan["intent"] = "exists_entity"
                plan["distinct"] = True
                plan["columns"] = ["ThekedaarName"]
            else:
                plan["intent"] = "work_list"
                plan["columns"] = plan.get("columns") or ["WorkId", "KamacheName", "ThekedaarName"]
    return plan


def _unique_field(rows, *keys):
    values = []
    seen = set()
    for row in rows or []:
        for key in keys:
            if not isinstance(row, dict):
                continue
            if key in row and row[key] not in (None, ""):
                value = row[key]
                marker = str(value)
                if marker not in seen:
                    seen.add(marker)
                    values.append(value)
                break
            for actual in row:
                if actual.lower() == key.lower() and row[actual] not in (None, ""):
                    value = row[actual]
                    marker = str(value)
                    if marker not in seen:
                        seen.add(marker)
                        values.append(value)
                    break
    return values


def compile_provision_sql(work_ids, provision_tables, year=None):
    if not work_ids or not provision_tables:
        return None
    year = year or _budget_year()
    ids = ", ".join(_sql_n(i) for i in work_ids[:400])
    parts = []
    for table in provision_tables:
        quoted = database._quote_mssql_table(table)
        parts.append(
            f"SELECT [WorkId], [Tartud], [AikunKharch] FROM {quoted} "
            f"WHERE [WorkId] IN ({ids}) AND [Arthsankalpiyyear] = {_sql_n(year)}"
        )
    if len(parts) == 1:
        return parts[0]
    return " UNION ALL ".join(parts)


def _merge_works_and_provision(works, provision):
    money = {}
    for row in provision or []:
        wid = None
        for key in ("WorkId", "WorkID", "Work_Id"):
            if isinstance(row, dict) and row.get(key) is not None:
                wid = row.get(key)
                break
        if wid is None:
            continue
        bucket = money.setdefault(str(wid), {"Tartud": 0, "AikunKharch": 0})
        tartud = row.get("Tartud") or 0
        kharch = row.get("AikunKharch") or 0
        try:
            bucket["Tartud"] += float(tartud)
            bucket["AikunKharch"] += float(kharch)
        except (TypeError, ValueError):
            pass
    merged = []
    for work in works or []:
        row = dict(work)
        wid = None
        for key in ("WorkId", "WorkID", "Work_Id"):
            if row.get(key) is not None:
                wid = row.get(key)
                break
        extra = money.get(str(wid), {}) if wid is not None else {}
        row["Tartud"] = extra.get("Tartud")
        row["AikunKharch"] = extra.get("AikunKharch")
        merged.append(row)
    return merged


def build_sql_chain(question, plan):
    """Split one user ask into ordered SQL steps that can reuse held rows."""
    plan = copy.deepcopy(plan)
    intent = plan.get("intent")
    wants_works = (
        _contains_any((question or "").lower(), _WORK_LIST_HINTS)
        or _contains_any(question or "", _WORK_LIST_HINTS)
        or ("कामे" in (question or ""))
    )
    if intent in ("count_works_by_scheme", "count_entities_by_scheme"):
        schemes = plan.get("schemes") or []
        count_col = plan.get("count_column") or (
            "WorkId" if "works" in intent else "ThekedaarName"
        )
        step_intent = "count_works" if "works" in intent else "count_entities"
        steps = []
        for name in schemes:
            table = database.SCHEME_MASTERS.get(name)
            if not table:
                continue
            step = copy.deepcopy(plan)
            step["intent"] = step_intent
            step["join_provision"] = False
            step["scheme"] = name
            step["tables"] = [table]
            step["count_column"] = count_col
            step["columns"] = [count_col]
            step["distinct"] = True
            step["hold_as"] = f"count:{name}"
            step["label"] = (
                f"Count works in {name}" if step_intent == "count_works"
                else f"Count contractors in {name}"
            )
            steps.append(step)
        return steps or [{**plan, "hold_as": "results"}]
    if intent == "finance" or plan.get("join_provision"):
        masters = _master_tables_from_plan(plan)
        works_plan = copy.deepcopy(plan)
        works_plan["intent"] = "work_list"
        works_plan["join_provision"] = False
        works_plan["tables"] = masters
        works_plan["columns"] = ["WorkId", "KamacheName", "ThekedaarName"]
        works_plan["distinct"] = False
        works_plan["hold_as"] = "works"
        works_plan["label"] = "Find matching works and hold WorkIds"
        provision_tables = [_provision_table_for_master(t) for t in masters]
        return [
            works_plan,
            {
                "action": "provision_by_work_ids",
                "intent": "finance",
                "hold_as": "provision",
                "bind_from": "works",
                "tables": provision_tables,
                "label": "Query provision using held WorkIds",
                "year": _budget_year(),
            },
        ]
    if intent == "exists_entity" and wants_works:
        exists_plan = copy.deepcopy(plan)
        exists_plan["hold_as"] = "names"
        exists_plan["label"] = "Confirm matching contractor names"
        exists_plan["distinct"] = True
        exists_plan["columns"] = ["ThekedaarName"]
        works_plan = copy.deepcopy(plan)
        works_plan["intent"] = "work_list"
        works_plan["hold_as"] = "works"
        works_plan["distinct"] = False
        works_plan["columns"] = ["WorkId", "KamacheName", "ThekedaarName"]
        works_plan["label"] = "List works for held contractor names"
        return [exists_plan, works_plan]
    step = copy.deepcopy(plan)
    step.setdefault("hold_as", "results")
    labels = {
        "exists_entity": "Search contractor names",
        "count_entities": "Count distinct contractors",
        "count_works": "Count works for the held contractor",
        "work_list": "List matching works",
        "list_entities": "List matching contractors",
    }
    step["label"] = labels.get(intent, "Run the planned query")
    return [step]


def execute_sql_chain(question, plan, schema_text, model_name, api_key, logs_callback, dialect, language):
    """Run chained SQL, holding each result for the next step."""
    held = {}
    if plan.get("held_names"):
        held["contractor_values"] = list(plan["held_names"])
        logs_callback(
            "Holding previous result: "
            + ", ".join(str(n) for n in held["contractor_values"][:5])
        )
    steps = build_sql_chain(question, plan)
    queries = []
    last_columns, last_rows = [], []
    total = len(steps)

    for index, step in enumerate(steps, 1):
        label = step.get("label") or f"query {index}"
        logs_callback(f"Chain {index}/{total}: {label}")

        if step.get("action") == "provision_by_work_ids":
            work_rows = held.get(step.get("bind_from") or "works") or []
            work_ids = _unique_field(work_rows, "WorkId", "WorkID", "Work_Id")
            if not work_ids:
                logs_callback("No WorkIds in held results — skipping provision query.")
                held[step.get("hold_as") or "provision"] = []
                continue
            logs_callback(f"Using {len(work_ids)} held WorkId value(s) in the next query.")
            sql_query = compile_provision_sql(work_ids, step.get("tables") or [], step.get("year"))
            if not sql_query:
                continue
            logs_callback(f"Generated SQL:\n{sql_query}")
            columns, rows, error_message = database.execute_query(sql_query)
            if error_message:
                logs_callback(f"Database execution failed: {error_message}")
                return {
                    "success": False,
                    "query": "\n\n-- next query --\n\n".join(queries + [sql_query]),
                    "error": error_message,
                    "columns": last_columns,
                    "results": last_rows,
                    "held": held,
                    "queries": queries,
                }
            queries.append(sql_query)
            held[step.get("hold_as") or "provision"] = rows or []
            last_columns = ["WorkId", "KamacheName", "ThekedaarName", "Tartud", "AikunKharch"]
            last_rows = _merge_works_and_provision(held.get("works") or [], rows or [])
            logs_callback(f"Held provision rows: {len(rows or [])}. Merged with {len(last_rows)} work row(s).")
            continue

        compiled_sql = compile_plan_sql(step) if dialect == "mssql" else None
        if compiled_sql:
            sql_query = compiled_sql
            logs_callback("Using planned SQL with held name/WorkId filters.")
            logs_callback(f"Generated SQL:\n{sql_query}")
            columns, rows, error_message = database.execute_query(sql_query)
            if error_message:
                logs_callback(f"Database execution failed: {error_message}")
                return {
                    "success": False,
                    "query": "\n\n-- next query --\n\n".join(queries + [sql_query]),
                    "error": error_message,
                    "columns": [],
                    "results": [],
                    "held": held,
                    "queries": queries,
                }
        else:
            result = generate_sql_agent(
                question=question,
                schema_text=schema_text,
                model_name=model_name,
                api_key=api_key,
                logs_callback=logs_callback,
                dialect=dialect,
                language=language,
                query_plan=step,
            )
            if not result["success"]:
                result["held"] = held
                result["queries"] = queries
                return result
            sql_query = result["query"]
            columns, rows = result["columns"], result["results"]
            error_message = None

        queries.append(sql_query)
        last_columns, last_rows = columns or [], rows or []
        hold_key = step.get("hold_as") or f"step_{index}"
        held[hold_key] = last_rows
        logs_callback(f"Held {len(last_rows)} row(s) as '{hold_key}'.")
        if not last_rows and index < total and step.get("intent") in ("exists_entity", "work_list"):
            logs_callback("No rows held — stopping the chain because later queries would be empty.")
            break

    grouped = (plan.get("intent") or "")
    if grouped in ("count_works_by_scheme", "count_entities_by_scheme"):
        count_key = "work_count" if "works" in grouped else "contractor_count"
        summary = []
        for name in plan.get("schemes") or []:
            rows = held.get(f"count:{name}") or []
            number = 0
            if rows and isinstance(rows[0], dict):
                number = (
                    rows[0].get(count_key)
                    or rows[0].get("work_count")
                    or rows[0].get("contractor_count")
                    or 0
                )
            summary.append({"scheme": name, count_key: number})
            logs_callback(f"Held {name} {count_key} = {number}")
        last_columns = ["scheme", count_key]
        last_rows = summary

    return {
        "success": True,
        "query": "\n\n-- next query --\n\n".join(queries),
        "columns": last_columns,
        "results": last_rows,
        "held": held,
        "queries": queries,
    }


def _sql_agent_instructions(dialect, language="en"):
    lang_rules = _language_sql_rules(language)
    if dialect == "mssql":
        return (
            "You write the smallest T-SQL query that answers the user's question.\n"
            "Follow the QUERY PLAN exactly.\n"
            "Rules:\n"
            "1. SELECT only the planned columns. Do not add WorkId, amounts, or joins 'just in case'.\n"
            "2. Use [dbo].[Table] names. TOP n not LIMIT. Unicode strings as N'अकोला' or N'पूर्ण'. Never LIKE LOWER() on Marathi.\n"
            "3. If the plan says no provision join, query the BudgetMaster table only.\n"
            "4. If DISTINCT is planned, use SELECT DISTINCT.\n"
            "5. Exclude placeholder names: N'कृपया नाव निवडा', N'0', blank.\n"
            "6. Match Dist in both English and Marathi when a district is given (Akola / अकोला).\n"
            "7. If the plan lists exact ThekedaarName values, use those Unicode strings in IN (N'...') — never translate contractor names to English.\n"
            "8. Output ONLY the SQL inside ```sql ... ```. No explanation."
            + (f"\n{lang_rules}" if lang_rules else "")
        )
    return (
        "You are an expert AI SQL Agent for SQLite databases.\n"
        "Your task is to write a single executable SQLite query that accurately answers the user's question.\n"
        "Rules:\n"
        "1. Study the database schema, foreign key relations, and sample data carefully.\n"
        "2. Join tables correctly using proper foreign keys.\n"
        "3. Output ONLY the SQLite query. Place it inside a ```sql ... ``` block or <sql>...</sql> tags.\n"
        "4. NEVER explain the query or output anything else in this turn. Just output the query.\n"
        "5. Do NOT perform any mutating operations (INSERT, UPDATE, DELETE, DROP) unless explicitly requested. ONLY generate SELECT queries by default.\n"
        "6. Handle case-insensitive matching where appropriate using 'LIKE' or 'LOWER()' if names or text searches are involved."
        + (f"\n{lang_rules}" if lang_rules else "")
    )


def generate_sql_agent(question, schema_text, model_name, api_key, logs_callback, dialect="sqlite", language="en", query_plan=None):
    """AI Agent Loop to generate, execute, and self-correct SQL queries."""
    dialect_label = "T-SQL (SQL Server)" if dialect == "mssql" else "SQLite"
    system_instruction = _sql_agent_instructions(dialect, language)
    plan_block = _format_query_plan(query_plan)

    prompt = f"""
QUERY PLAN — follow this exactly:
{plan_block}

{dialect_label} schema (only relevant tables):
========================================
{schema_text}
========================================

User Question: "{question}"

Write the smallest SQL that satisfies the plan.
"""

    logs_callback("Step 2: Writing a minimal SQL query from the plan...")

    sql_query = ""
    error_message = None
    columns, rows = None, None
    max_retries = 3
    retry_count = 0
    compiled_sql = compile_plan_sql(query_plan) if dialect == "mssql" else None

    while retry_count <= max_retries:
        try:
            if compiled_sql and retry_count == 0:
                sql_query = compiled_sql
                logs_callback("Step 2: Using planned SQL with exact contractor/name filters.")
            elif retry_count == 0:
                logs_callback(f"Step 2: Requesting SQL query from OpenAI ({model_name})...")
                response = call_llm(prompt, system_instruction, model_name, api_key)
                sql_query = clean_sql(response)
            else:
                logs_callback(f"Step 2 (Retry {retry_count}): Sending execution error back to OpenAI for correction...")
                correction_prompt = f"""
QUERY PLAN — follow this exactly:
{plan_block}

{dialect_label} schema:
========================================
{schema_text}
========================================

You previously generated this SQL query:
```sql
{sql_query}
```

However, executing this query threw the following database error:
"{error_message}"

Write a corrected {dialect_label} query that still follows the plan (no extra joins or columns).
Output ONLY the corrected SQL query inside ```sql ... ``` block or <sql>...</sql> tags.
"""
                response = call_llm(correction_prompt, system_instruction, model_name, api_key)
                sql_query = clean_sql(response)

            if dialect == "mssql":
                normalized = normalize_mssql_unicode_literals(sql_query)
                if normalized != sql_query:
                    logs_callback("Normalized Marathi literals to Unicode equality (N'...').")
                    sql_query = normalized
            logs_callback(f"Generated SQL:\n{sql_query}")

            if not sql_query:
                error_message = "No SQL query could be parsed from LLM response."
                logs_callback(f"Parser error: {error_message}")
                retry_count += 1
                continue

            logs_callback(f"Step 3: Executing SQL query on the {dialect_label} database...")
            columns, rows, error_message = database.execute_query(sql_query)

            if error_message:
                logs_callback(f"Database execution failed: {error_message}")
                retry_count += 1
            else:
                logs_callback("Step 4: Query executed successfully! Retrieved data rows.")
                break

        except Exception as e:
            error_message = str(e)
            logs_callback(f"Error in Agent loop: {error_message}")
            retry_count += 1

    if error_message and retry_count > max_retries:
        logs_callback("Agent failed to generate a valid working SQL query after multiple attempts.")
        return {
            "success": False,
            "query": sql_query,
            "error": error_message,
            "columns": [],
            "results": [],
        }

    return {
        "success": True,
        "query": sql_query,
        "columns": columns,
        "results": rows,
    }


def formulate_answer(question, sql_query, results, model_name, api_key, logs_callback, language="en", query_plan=None, held=None):
    """Generate a natural language response based on the query results."""
    logs_callback("Step 5: Formulating a direct answer...")

    intent = (query_plan or {}).get("intent") or "other"
    fragment = ""
    for filt in (query_plan or {}).get("filters") or []:
        if filt.get("column") == "ThekedaarName" and filt.get("values"):
            fragment = filt["values"][0]
            break
    fragment = fragment or (query_plan or {}).get("name_like") or ""
    direct = _direct_answer(question, query_plan, results, language, held=held, fragment=fragment)
    if direct:
        logs_callback("Step 6: Answer built from held query results (no extra wording pass).")
        return direct

    held_note = ""
    if held:
        summary = {key: (len(val) if isinstance(val, list) else val) for key, val in held.items()}
        held_note = f"\nHeld intermediate results: {json.dumps(summary, ensure_ascii=False)}\n"

    system_instruction = (
        "You are a concise PWD analyst speaking to an officer.\n"
        "Answer only what was asked. Do not mention SQL, joins, or extra fields.\n"
        "Keep contractor names, work names, Dist, and numbers exactly as in the results.\n"
        "Do not translate proper nouns like ThekedaarName into English.\n"
        "If they asked which contractors/ठेकेदार, list unique ThekedaarName values in a short paragraph or bullets.\n"
        "If intent is exists_entity, say clearly whether such a contractor exists and give the stored names.\n"
        "If intent is count_entities, give the number clearly (Marathi answer: use ठेकेदार even if they said contractor in English).\n"
        "If several queries were chained, combine the held facts into one answer.\n"
        "Skip placeholder names like कृपया नाव निवडा.\n"
        "If no rows, say none were found.\n"
        f"Question intent: {intent}.\n"
        + _language_answer_rules(language)
    )

    prompt = f"""
User Question: "{question}"
SQL Query Executed:
```sql
{sql_query}
```
{held_note}
Query Results (JSON format):
{results}

Formulate a short natural language answer. Do not recap unused columns.
"""

    try:
        answer = call_llm(prompt, system_instruction, model_name, api_key)
        logs_callback("Step 6: Answer successfully generated!")
        return answer
    except Exception as e:
        error_msg = f"Failed to formulate answer: {str(e)}"
        logs_callback(error_msg)
        return f"Query succeeded, but could not formulate natural language answer. Raw Results: {results}"


def _direct_answer(question, query_plan, results, language, held=None, fragment=""):
    intent = (query_plan or {}).get("intent") or "other"
    held = held or {}
    if intent == "exists_entity":
        name_rows = held.get("names") or held.get("results") or results
        names = _unique_field(name_rows, "ThekedaarName")
        label = fragment or "that name"
        if language == "mr":
            if not names:
                return f"नाही. «{label}» या नावाने ठेकेदार सापडला नाही."
            if len(names) == 1:
                return f"होय. {names[0]} या नावाने ठेकेदार आहे."
            listed = ", ".join(names)
            return f"होय. {len(names)} ठेकेदार सापडले: {listed}."
        if not names:
            return f"No. There is no contractor matching “{label}”."
        if len(names) == 1:
            return f"Yes. There is a contractor named {names[0]}."
        return f"Yes. {len(names)} contractors match: {', '.join(names)}."
    if intent in ("count_works_by_scheme", "count_entities_by_scheme"):
        count_key = "work_count" if "works" in intent else "contractor_count"
        noun = "कामे" if count_key == "work_count" else "ठेकेदार"
        noun_en = "works" if count_key == "work_count" else "contractors"
        lines = []
        for row in results or []:
            if not isinstance(row, dict):
                continue
            label = row.get("scheme") or ""
            number = row.get(count_key)
            if language == "mr":
                lines.append(f"{label}: {number} {noun}")
            else:
                lines.append(f"{label}: {number} {noun_en}")
        if lines:
            if language == "mr":
                return "प्रत्येक योजनेतील संख्या:\n" + "\n".join(lines)
            return "Count for each scheme:\n" + "\n".join(lines)
    if intent == "count_entities" and results:
        row = results[0] if isinstance(results[0], dict) else {}
        count = row.get("contractor_count")
        if count is not None:
            if language == "mr":
                return f"एकूण {count} ठेकेदार आहेत."
            return f"There are {count} contractors."
    if intent == "count_works" and results:
        row = results[0] if isinstance(results[0], dict) else {}
        count = row.get("work_count")
        if count is not None:
            if language == "mr":
                return f"या ठेकेदाराची {count} कामे आहेत."
            return f"This contractor has {count} works."
    return None


def run_agent(question, model_name, api_key, db_path=database.DEFAULT_DB_PATH, language="en"):
    """The main coordinator for the AI SQL Agent."""
    logs = []

    def logs_callback(msg):
        logs.append(msg)
        print(msg)

    if not api_key:
        return {
            "success": False,
            "error": "Missing API Key. Set OPENAI_API_KEY in the server .env file.",
            "logs": ["Failed: OpenAI API key is required."],
        }

    if not model_name:
        model_name = DEFAULT_MODEL

    language = detect_language(question, language)
    if language == "mr":
        logs_callback("Language: Marathi — plan, SQL literals, and answer in मराठी.")

    try:
        plan = plan_question(question, model_name, api_key, logs_callback)
        plan, clarification = _apply_contractor_resolution(question, plan, logs_callback)
        if clarification:
            return {
                "success": True,
                "needs_clarification": True,
                "query": "",
                "columns": [],
                "results": [],
                "answer": contractor_names.clarification_message(clarification, language),
                "options": clarification.get("options") or [],
                "logs": logs,
            }

        dialect = database.get_db_dialect()
        schema_text = database.get_focused_schema_text(plan.get("tables") or [])

        sql_agent_result = execute_sql_chain(
            question=question,
            plan=plan,
            schema_text=schema_text,
            model_name=model_name,
            api_key=api_key,
            logs_callback=logs_callback,
            dialect=dialect,
            language=language,
        )

        if not sql_agent_result["success"]:
            return {
                "success": False,
                "error": sql_agent_result["error"],
                "query": sql_agent_result["query"],
                "logs": logs,
            }

        answer = formulate_answer(
            question=question,
            sql_query=sql_agent_result["query"],
            results=sql_agent_result["results"],
            model_name=model_name,
            api_key=api_key,
            logs_callback=logs_callback,
            language=language,
            query_plan=plan,
            held=sql_agent_result.get("held"),
        )

        return {
            "success": True,
            "query": sql_agent_result["query"],
            "columns": sql_agent_result["columns"],
            "results": sql_agent_result["results"],
            "answer": answer,
            "logs": logs,
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "logs": logs + [f"Fatal Error: {str(e)}"],
        }
