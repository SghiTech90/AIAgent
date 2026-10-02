import os
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
DB_ENGINE = os.getenv("DB_ENGINE", "mssql").lower().strip()
SCHEMA_SAMPLE_LIMIT = int(os.getenv("SCHEMA_SAMPLE_LIMIT", "30"))
SCHEMA_NOTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_notes.txt")
_SKIP_SAMPLE_TABLES = {
    "login",
    "user",
    "usercredintiall",
    "screateadmin",
    "thekedarphoto",
    "imagegallary",
    "imagespath",
    "uploaddocuments",
    "tbl_all_img",
}
_BINARY_SAMPLE_COLUMNS = {
    "image",
    "img1",
    "img2",
    "img3",
    "photo",
    "filepath",
    "imageurl",
    "error_img",
    "error_imgtype",
}
_WORK_SATELLITE_TABLES = {
    "ImageGallary",
    "ImagesPath",
    "NividaDetails",
    "StatusBillPayment",
    "UploadDocuments",
    "SendSms_tbl",
    "tbl_All_Img",
    "tbl_Bill_Status",
}
_LOOKUP_JOINS = (
    ("Taluka", "SettingTaluka", "Taluka"),
    ("Dist", "SettingJilha", "Jilha"),
    ("Jilha", "SettingJilha", "Jilha"),
    ("Upvibhag", "SettingUpVibhag", "UpVibhagacheName"),
    ("LekhaShirsh", "SettingLekhaShirsh", "code"),
    ("Lekhashirsh", "SettingLekhaShirsh", "code"),
    ("Type", "SettingType", "Type"),
)

SCHEME_MASTERS = {
    "Building": "dbo.BudgetMasterBuilding",
    "Road": "dbo.BudgetMasterRoad",
    "Annuity": "dbo.BudgetMasterAunty",
    "CRF": "dbo.BudgetMasterCRF",
    "NABARD": "dbo.BudgetMasterNABARD",
    "GAT_A": "dbo.BudgetMasterGAT_A",
    "GAT_D": "dbo.BudgetMasterGAT_D",
    "GAT_FBC": "dbo.BudgetMasterGAT_FBC",
    "MLA": "dbo.BudgetMasterMLA",
    "MP": "dbo.BudgetMasterMP",
    "2515": "dbo.BudgetMaster2515",
    "Deposit": "dbo.BudgetMasterDepositFund",
    "DPDC": "dbo.BudgetMasterDPDC",
    "NonResBuilding": "dbo.BudgetMasterNonResidentialBuilding",
    "ResBuilding": "dbo.BudgetMasterResidentialBuilding",
}

PLACEHOLDER_NAMES = ("कृपया नाव निवडा", "0", "")
_contractor_name_cache = {}


def uses_mssql():
    return DB_ENGINE == "mssql"


def get_db_dialect():
    return "mssql" if uses_mssql() else "sqlite"


def get_db_label():
    if uses_mssql():
        return os.getenv("DB_DATABASE", "SQL Server")
    return "data.db (Sample)"


def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _row_to_dict(columns, row):
    return {col: _serialize_value(val) for col, val in zip(columns, row)}


def _mssql_connection_string():
    import pyodbc

    server = os.environ["DB_SERVER"]
    database = os.environ["DB_DATABASE"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    port = os.getenv("DB_PORT", "1433")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    encrypt = os.getenv("DB_ENCRYPT", "no")
    trust = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"TrustServerCertificate={trust};"
        f"Encrypt={encrypt};"
    )


def get_mssql_connection():
    import pyodbc

    timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "3"))
    return pyodbc.connect(_mssql_connection_string(), timeout=timeout)


def get_db_connection(db_path=DEFAULT_DB_PATH):
    """Establish a connection to the active database."""
    if uses_mssql():
        return get_mssql_connection()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _qualified_table_name(schema_name, table_name):
    return f"{schema_name}.{table_name}"


def _parse_table_reference(table_name, default_schema="dbo"):
    if "." in table_name:
        schema_name, bare_name = table_name.split(".", 1)
        return schema_name.strip("[]"), bare_name.strip("[]")
    return default_schema, table_name.strip("[]")


def _quote_mssql_identifier(name):
    return f"[{name.replace(']', ']]')}]"


def _quote_mssql_table(table_name, default_schema="dbo"):
    schema_name, bare_name = _parse_table_reference(table_name, default_schema)
    return f"{_quote_mssql_identifier(schema_name)}.{_quote_mssql_identifier(bare_name)}"


def _is_write_query(query):
    stripped = re.sub(r"/\*.*?\*/", "", query, flags=re.DOTALL)
    stripped = re.sub(r"--.*?$", "", stripped, flags=re.MULTILINE).strip().lower()
    if not stripped:
        return False
    first = stripped.split()[0]
    return first not in ("select", "with", "show", "explain")


def execute_query(query, db_path=DEFAULT_DB_PATH):
    """
    Execute a query. SELECT-like queries return columns and rows.
    Returns: (columns, rows, error_message)
    """
    if uses_mssql() and os.getenv("DB_READ_ONLY", "true").lower() == "true":
        if _is_write_query(query):
            return None, None, "Write operations are disabled for SQL Server (DB_READ_ONLY=true)."

    conn = None
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(query)

        if cursor.description:
            columns = [col[0] for col in cursor.description]
            if uses_mssql():
                rows = [_row_to_dict(columns, row) for row in cursor.fetchall()]
            else:
                rows = [dict(row) for row in cursor.fetchall()]
            return columns, rows, None

        conn.commit()
        return [], [{"affected_rows": cursor.rowcount}], None
    except Exception as e:
        return None, None, str(e)
    finally:
        if conn:
            conn.close()


def _get_sqlite_schema(db_path):
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row["name"] for row in cursor.fetchall()]

    schema = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns_info = cursor.fetchall()
        cursor.execute(f"PRAGMA foreign_key_list({table});")
        fk_info = cursor.fetchall()

        columns = []
        for col in columns_info:
            columns.append({
                "name": col["name"],
                "type": col["type"],
                "notnull": bool(col["notnull"]),
                "pk": bool(col["pk"]),
            })

        foreign_keys = []
        for fk in fk_info:
            foreign_keys.append({
                "from_column": fk["from"],
                "to_table": fk["table"],
                "to_column": fk["to"],
            })

        schema[table] = {"columns": columns, "foreign_keys": foreign_keys}

    conn.close()
    return schema


def _get_mssql_schema():
    conn = get_mssql_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
    """)
    tables = cursor.fetchall()

    cursor.execute("""
        SELECT
            OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS parent_schema,
            OBJECT_NAME(fkc.parent_object_id) AS parent_table,
            COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS parent_column,
            OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS ref_schema,
            OBJECT_NAME(fkc.referenced_object_id) AS ref_table,
            COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS ref_column
        FROM sys.foreign_key_columns fkc
    """)
    fk_rows = cursor.fetchall()
    fk_map = {}
    for parent_schema, parent_table, parent_column, ref_schema, ref_table, ref_column in fk_rows:
        key = _qualified_table_name(parent_schema, parent_table)
        fk_map.setdefault(key, []).append({
            "from_column": parent_column,
            "to_table": _qualified_table_name(ref_schema, ref_table),
            "to_column": ref_column,
        })

    schema = {}
    for table_schema, table_name in tables:
        qualified = _qualified_table_name(table_schema, table_name)
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """, (table_schema, table_name))
        columns_info = cursor.fetchall()

        cursor.execute("""
            SELECT c.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE c
              ON c.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
             AND c.TABLE_SCHEMA = tc.TABLE_SCHEMA
             AND c.TABLE_NAME = tc.TABLE_NAME
            WHERE tc.TABLE_SCHEMA = ? AND tc.TABLE_NAME = ? AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        """, (table_schema, table_name))
        pk_columns = {row[0] for row in cursor.fetchall()}

        columns = []
        for col_name, data_type, is_nullable, char_len in columns_info:
            type_label = data_type
            if char_len and data_type in ("varchar", "nvarchar", "char", "nchar"):
                type_label = f"{data_type}({char_len})"
            columns.append({
                "name": col_name,
                "type": type_label,
                "notnull": is_nullable == "NO",
                "pk": col_name in pk_columns,
            })

        schema[qualified] = {
            "columns": columns,
            "foreign_keys": fk_map.get(qualified, []),
        }

    conn.close()
    return schema


def _bare_table_name(table_name):
    return table_name.split(".")[-1]


def _normalize_col_name(name):
    return name.lower().replace("_", "")


def _find_column(columns, *aliases):
    wanted = {_normalize_col_name(alias) for alias in aliases}
    for col in columns:
        if _normalize_col_name(col["name"]) in wanted:
            return col["name"]
    return None


def _add_relationship(schema, from_table, from_column, to_table, to_column, inferred=True):
    if from_table not in schema or to_table not in schema:
        return
    existing = schema[from_table].setdefault("foreign_keys", [])
    for fk in existing:
        if (
            _normalize_col_name(fk["from_column"]) == _normalize_col_name(from_column)
            and fk["to_table"] == to_table
            and _normalize_col_name(fk["to_column"]) == _normalize_col_name(to_column)
        ):
            return
    existing.append({
        "from_column": from_column,
        "to_table": to_table,
        "to_column": to_column,
        "inferred": inferred,
    })


def _attach_inferred_relationships(schema):
    """Infer PWD scheme joins the way the Node APIs do (no declared FKs)."""
    by_bare = {_bare_table_name(table): table for table in schema}

    for bare, qualified in by_bare.items():
        if not bare.startswith("BudgetMaster"):
            continue
        suffix = bare[len("BudgetMaster"):]
        provision = by_bare.get(f"{suffix}Provision")
        if not provision:
            continue
        master_work = _find_column(schema[qualified]["columns"], "WorkId", "WorkID", "Work_Id")
        provision_work = _find_column(schema[provision]["columns"], "WorkId", "WorkID", "Work_Id")
        if master_work and provision_work:
            _add_relationship(schema, qualified, master_work, provision, provision_work)
            _add_relationship(schema, provision, provision_work, qualified, master_work)

        for from_col, lookup_bare, lookup_col in _LOOKUP_JOINS:
            lookup_table = by_bare.get(lookup_bare)
            actual_from = _find_column(schema[qualified]["columns"], from_col)
            if not lookup_table or not actual_from:
                continue
            actual_to = _find_column(schema[lookup_table]["columns"], lookup_col)
            if actual_to:
                _add_relationship(schema, qualified, actual_from, lookup_table, actual_to)


def _relationship_graph_text(schema):
    pairs = []
    seen_pairs = set()
    lookup_patterns = []
    seen_lookups = set()
    by_bare = {_bare_table_name(table): table for table in schema}

    for table, details in schema.items():
        for fk in details.get("foreign_keys") or []:
            if not fk.get("inferred"):
                continue
            from_bare = _bare_table_name(table)
            to_bare = _bare_table_name(fk["to_table"])
            if from_bare.startswith("BudgetMaster") and to_bare.endswith("Provision"):
                key = (from_bare, to_bare)
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    pairs.append(
                        f"  - [{table}].[{fk['from_column']}] = [{fk['to_table']}].[{fk['to_column']}]"
                    )
            elif to_bare.startswith("Setting"):
                pattern = (fk["from_column"], to_bare, fk["to_column"])
                if pattern not in seen_lookups:
                    seen_lookups.add(pattern)
                    lookup_patterns.append(
                        f"  - BudgetMaster*.[{fk['from_column']}] ~ [{fk['to_table']}].[{fk['to_column']}] (text match)"
                    )

    satellites = [by_bare[bare] for bare in sorted(_WORK_SATELLITE_TABLES) if bare in by_bare]
    if not pairs:
        return ""

    lines = [
        "JOIN MAP (this database has ZERO declared foreign keys):",
        "DEFAULT: use BudgetMaster{Scheme} alone for work lists (WorkId, KamacheName, ThekedaarName, Sadyasthiti, Dist, Taluka, Upvibhag).",
        "Do NOT INNER JOIN *Provision for those questions — provision has fewer rows (budget year money only) and the join hides most works.",
        "Join *Provision ONLY for Tartud / AikunKharch / MarchEndingExpn / UrvaritAmt / Magni. Then LEFT JOIN on WorkId and filter b.Arthsankalpiyyear (default 2025-2026).",
        "Do NOT require a.Arthsankalpiyyear = b.Arthsankalpiyyear.",
        "Estimated/AA cost = a.PrashaskiyAmt (master). T.S. cost = a.TrantrikAmt (master). Contractor = a.ThekedaarName (master).",
        "Work status = a.Sadyasthiti. Filter only with Unicode equality, e.g. a.Sadyasthiti = N'पूर्ण'. Never LIKE LOWER('पूर्ण').",
    ]
    lines.append("Scheme pairs:")
    lines.extend(pairs)
    if satellites:
        lines.append(
            "Work satellite tables join matching BudgetMaster* on WorkId "
            "(WorkId / WorkID / Work_Id / Work_ID): " + ", ".join(satellites)
        )
        lines.append("ImageGallary.Type names the scheme (Road, Building, ...).")
    if lookup_patterns:
        lines.append("Geography / account-head lookups (match text, not numeric IDs):")
        lines.extend(lookup_patterns)
    return "\n".join(lines)


def _sample_priority(table_name):
    bare = _bare_table_name(table_name)
    if bare.lower() in _SKIP_SAMPLE_TABLES:
        return 99
    if bare.startswith("BudgetMaster") or bare.endswith("Provision"):
        return 0
    if bare.startswith("Setting") or bare in _WORK_SATELLITE_TABLES:
        return 1
    if bare in ("BillStatus", "Division", "Post", "Month"):
        return 1
    return 2


def _compact_sample_row(row):
    compact = {}
    for key, value in row.items():
        if key.lower() in _BINARY_SAMPLE_COLUMNS:
            compact[key] = "<omitted>"
            continue
        if isinstance(value, str) and len(value) > 180:
            compact[key] = value[:180] + "…"
        else:
            compact[key] = value
    return compact


def _priority_sample_tables(schema):
    ranked = sorted(schema.keys(), key=lambda name: (_sample_priority(name), name))
    chosen = []
    for table_name in ranked:
        if _sample_priority(table_name) >= 99:
            continue
        chosen.append(table_name)
        if len(chosen) >= SCHEMA_SAMPLE_LIMIT:
            break
    return chosen


def get_schema(db_path=DEFAULT_DB_PATH):
    """Return tables, columns, and foreign keys for the active database."""
    if uses_mssql():
        schema = _get_mssql_schema()
    else:
        schema = _get_sqlite_schema(db_path)
    _attach_inferred_relationships(schema)
    return schema


def get_table_data(table_name, db_path=DEFAULT_DB_PATH, limit=50):
    """Retrieve rows for a given table."""
    schema = get_schema(db_path)
    if table_name not in schema:
        raise ValueError(f"Table '{table_name}' does not exist.")

    if uses_mssql():
        quoted = _quote_mssql_table(table_name)
        query = f"SELECT TOP {int(limit)} * FROM {quoted};"
    else:
        query = f"SELECT * FROM {table_name} LIMIT {int(limit)};"

    columns, rows, error = execute_query(query, db_path)
    return {"columns": columns, "rows": rows, "error": error}


def _load_schema_notes():
    if not os.path.isfile(SCHEMA_NOTES_PATH):
        return ""
    lines = []
    with open(SCHEMA_NOTES_PATH, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def get_schema_summary_text(db_path=DEFAULT_DB_PATH):
    """Text schema context for the LLM agent."""
    schema = get_schema(db_path)
    summary = []
    notes = _load_schema_notes()
    if notes:
        summary.append("Business notes (domain context):")
        summary.append(notes)
        summary.append("=" * 40)

    if uses_mssql():
        summary.append(f"Database: Microsoft SQL Server ({get_db_label()})")
        summary.append("Use T-SQL syntax: TOP n instead of LIMIT, bracketed names like [dbo].[Table].")
        summary.append("=" * 40)

    graph = _relationship_graph_text(schema)
    if graph:
        summary.append(graph)
        summary.append("=" * 40)

    table_names = sorted(schema.keys())
    sample_tables = set(_priority_sample_tables(schema))
    for table_name in table_names:
        details = schema[table_name]
        summary.append(f"Table: {table_name}")

        col_texts = []
        for col in details["columns"]:
            pk_suffix = " (PRIMARY KEY)" if col["pk"] else ""
            notnull_suffix = " NOT NULL" if col["notnull"] else ""
            col_texts.append(f"  - {col['name']} ({col['type']}){pk_suffix}{notnull_suffix}")
        summary.append("\n".join(col_texts))

        if details["foreign_keys"]:
            fk_texts = []
            for fk in details["foreign_keys"]:
                label = "INFERRED JOIN" if fk.get("inferred") else "FOREIGN KEY"
                fk_texts.append(
                    f"  - {label} ({fk['from_column']}) REFERENCES {fk['to_table']}({fk['to_column']})"
                )
            summary.append("\n".join(fk_texts))

        bare = _bare_table_name(table_name)
        skip_sample = bare.lower() in _SKIP_SAMPLE_TABLES
        include_samples = (not skip_sample) and table_name in sample_tables
        if skip_sample:
            summary.append("  (Sample rows omitted — credentials, photos, or binary content. Never SELECT Password.)")
        elif include_samples:
            if uses_mssql():
                quoted = _quote_mssql_table(table_name)
                sample_sql = f"SELECT TOP 3 * FROM {quoted};"
            else:
                sample_sql = f"SELECT * FROM {table_name} LIMIT 3;"
            columns, rows, _ = execute_query(sample_sql, db_path)
            if rows:
                summary.append("  Sample Rows:")
                for row in rows:
                    summary.append(f"    {_compact_sample_row(row)}")
            else:
                summary.append("  Sample Rows: none (table appears empty — prefer a sibling table that has rows).")
        else:
            summary.append("  (Sample rows omitted for brevity — columns listed above.)")

        summary.append("-" * 40)

    if len(table_names) > len(sample_tables):
        summary.append(
            f"Note: Sample rows shown for {len(sample_tables)} priority tables "
            f"(scheme masters, provisions, lookups). All {len(table_names)} tables are listed with columns."
        )

    return "\n".join(summary)


def get_planner_catalog():
    """Tiny scheme map for the intent planner — not the full schema dump."""
    lines = [
        "PWD schemes (master tables hold works, contractors, Dist, status):",
    ]
    for scheme, table in SCHEME_MASTERS.items():
        lines.append(f"  - {scheme} → [{table}]")
    lines.extend([
        "Useful master columns: WorkId, KamacheName, ThekedaarName, Dist, Taluka, Upvibhag, Sadyasthiti, PrashaskiyAmt, TrantrikAmt.",
        "Provision tables (*Provision) are ONLY for this-year money: Tartud, AikunKharch, MarchEndingExpn, UrvaritAmt, Magni.",
        "Place names: Dist may be Akola or अकोला. Dummy names to exclude: कृपया नाव निवडा, 0, blank.",
        "Contractor synonyms (same column ThekedaarName): English contractor/thekedar, Marathi ठेकेदार/कंत्राटदार; mixed questions OK.",
        "Marathi glossary: ठेकेदार/कंत्राटदार=ThekedaarName, इमारत=Building, रस्ता=Road, जिल्हा=Dist,",
        "पूर्ण=completed status, तरतूद=Tartud, खर्च रक्कम=AikunKharch, कामाचे नाव=KamacheName.",
        "App aliases: SH & DOR=Road, Annuity=Aunty, NonPlan=GAT_A, 2059=NonResBuilding, 2216=ResBuilding.",
    ])
    return "\n".join(lines)


def get_contractor_names(master_table=None):
    """Distinct ThekedaarName values from one scheme master or all masters."""
    if not uses_mssql():
        return []
    import time

    cache_key = _bare_table_name(master_table) if master_table else "*"
    now = time.time()
    cached = _contractor_name_cache.get(cache_key)
    if cached and now - cached["at"] < 300:
        return cached["names"]

    tables = [master_table] if master_table else list(SCHEME_MASTERS.values())
    parts = []
    for table in tables:
        quoted = _quote_mssql_table(table)
        parts.append(
            "SELECT DISTINCT ThekedaarName AS name FROM "
            f"{quoted} WHERE ThekedaarName IS NOT NULL "
            "AND LTRIM(RTRIM(CAST(ThekedaarName AS nvarchar(500)))) "
            "NOT IN (N'', N'0', N'कृपया नाव निवडा')"
        )
    _, rows, error = execute_query(" UNION ".join(parts))
    if error:
        return []
    names = [row.get("name") for row in (rows or []) if row.get("name")]
    _contractor_name_cache[cache_key] = {"at": now, "names": names}
    if len(_contractor_name_cache) > 20:
        oldest = min(_contractor_name_cache, key=lambda key: _contractor_name_cache[key]["at"])
        _contractor_name_cache.pop(oldest, None)
    return names


def _resolve_schema_table(schema, table_name):
    if not table_name:
        return None
    if table_name in schema:
        return table_name
    bare = _bare_table_name(table_name).strip("[]")
    for key in schema:
        if _bare_table_name(key).lower() == bare.lower():
            return key
    return None


def get_focused_schema_text(table_names, db_path=DEFAULT_DB_PATH):
    """Schema for only the tables the planner selected — no 65-table dump."""
    schema = get_schema(db_path)
    resolved = []
    for name in table_names or []:
        match = _resolve_schema_table(schema, name)
        if match and match not in resolved:
            resolved.append(match)

    if not resolved:
        return get_schema_summary_text(db_path)

    summary = [
        "Use ONLY the tables below. Do not invent joins or extra columns.",
        get_planner_catalog(),
        "=" * 40,
    ]
    if uses_mssql():
        summary.append("T-SQL: TOP n, [dbo].[Table], Unicode strings as N'अकोला'.")
        summary.append("=" * 40)

    for table_name in resolved:
        details = schema[table_name]
        summary.append(f"Table: {table_name}")
        col_texts = []
        for col in details["columns"]:
            pk_suffix = " (PRIMARY KEY)" if col.get("pk") else ""
            col_texts.append(f"  - {col['name']} ({col['type']}){pk_suffix}")
        summary.append("\n".join(col_texts))
        summary.append("-" * 40)
    return "\n".join(summary)


def test_connection():
    """Verify database connectivity. Raises on failure."""
    conn = get_db_connection()
    try:
        if uses_mssql():
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        else:
            conn.execute("SELECT 1")
    finally:
        conn.close()
