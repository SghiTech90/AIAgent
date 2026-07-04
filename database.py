import os
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower().strip()
SCHEMA_SAMPLE_LIMIT = int(os.getenv("SCHEMA_SAMPLE_LIMIT", "30"))
SCHEMA_NOTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_notes.txt")


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

    timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "15"))
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


def init_db(db_path=DEFAULT_DB_PATH):
    """Initialize the SQLite sample database (ignored when DB_ENGINE=mssql)."""
    if uses_mssql():
        raise RuntimeError("init_db() is only available for the local SQLite sample database.")

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError as e:
            print(f"Error removing existing database: {e}")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        department TEXT NOT NULL,
        salary REAL NOT NULL,
        hire_date TEXT NOT NULL,
        manager_id INTEGER,
        email TEXT UNIQUE NOT NULL,
        FOREIGN KEY (manager_id) REFERENCES employees (id) ON DELETE SET NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        budget REAL NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT,
        status TEXT NOT NULL CHECK (status IN ('Planning', 'Active', 'On Hold', 'Completed'))
    );
    """)

    cursor.execute("""
    CREATE TABLE employee_projects (
        employee_id INTEGER,
        project_id INTEGER,
        hours_per_week INTEGER DEFAULT 40,
        role_in_project TEXT NOT NULL,
        PRIMARY KEY (employee_id, project_id),
        FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    INSERT INTO employees (id, name, role, department, salary, hire_date, manager_id, email) VALUES
    (1, 'Priya Sharma', 'Engineering Director', 'Engineering', 145000.00, '2021-03-15', NULL, 'priya.sharma@company.com');
    """)

    employees = [
        (2, 'Raj Malhotra', 'Senior Lead Developer', 'Engineering', 115000.00, '2022-06-01', 1, 'raj.malhotra@company.com'),
        (3, 'Amit Patel', 'Senior UX/UI Designer', 'Design', 95000.00, '2023-01-10', 1, 'amit.patel@company.com'),
        (4, 'Rohan Mehta', 'Frontend Engineer', 'Engineering', 85000.00, '2023-08-15', 2, 'rohan.mehta@company.com'),
        (5, 'Sunita Rao', 'Backend Engineer', 'Engineering', 90000.00, '2022-11-20', 2, 'sunita.rao@company.com'),
        (6, 'Neha Gupta', 'Data Scientist', 'Analytics', 105000.00, '2023-02-28', 1, 'neha.gupta@company.com'),
        (7, 'Vikram Singh', 'QA Engineer', 'Engineering', 75000.00, '2024-01-05', 2, 'vikram.singh@company.com'),
        (8, 'Sarah Johnson', 'Product Manager', 'Product', 120000.00, '2022-04-10', None, 'sarah.j@company.com'),
    ]
    cursor.executemany(
        """
        INSERT INTO employees (id, name, role, department, salary, hire_date, manager_id, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        employees,
    )

    projects = [
        (101, 'Project Alpha', 'Next-generation AI core engine and query processor.', 250000.00, '2025-01-10', '2026-06-30', 'Active'),
        (102, 'Project Beta', 'Modern cloud migration and API infrastructure overhaul.', 180000.00, '2025-03-01', '2025-12-15', 'Active'),
        (103, 'Project Gamma', 'Redesign of customer portal and analytics dashboard.', 95000.00, '2025-05-01', '2025-10-31', 'Planning'),
        (104, 'Project Delta', 'Automated security vulnerability scanner tool.', 150000.00, '2024-06-01', '2025-04-30', 'Completed'),
    ]
    cursor.executemany(
        """
        INSERT INTO projects (id, name, description, budget, start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        projects,
    )

    assignments = [
        (2, 101, 20, 'Technical Architect'),
        (4, 101, 30, 'Frontend Lead'),
        (5, 101, 30, 'Backend Developer'),
        (6, 101, 15, 'Data Engineer'),
        (8, 101, 15, 'Product Lead'),
        (2, 102, 20, 'Lead Consultant'),
        (5, 102, 10, 'Cloud Infrastructure'),
        (7, 102, 40, 'QA Automation Lead'),
        (8, 102, 20, 'Product Owner'),
        (3, 103, 35, 'Lead UX/UI Designer'),
        (4, 103, 10, 'UI Prototyper'),
        (8, 103, 5, 'Advisory PM'),
        (2, 104, 0, 'Security Advisor'),
        (5, 104, 0, 'Security Implementation'),
    ]
    cursor.executemany(
        """
        INSERT INTO employee_projects (employee_id, project_id, hours_per_week, role_in_project)
        VALUES (?, ?, ?, ?);
        """,
        assignments,
    )

    conn.commit()
    conn.close()
    print(f"Database initialized successfully at {db_path}!")


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


def get_schema(db_path=DEFAULT_DB_PATH):
    """Return tables, columns, and foreign keys for the active database."""
    if uses_mssql():
        return _get_mssql_schema()
    return _get_sqlite_schema(db_path)


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

    table_names = sorted(schema.keys())
    for index, table_name in enumerate(table_names):
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
                fk_texts.append(
                    f"  - FOREIGN KEY ({fk['from_column']}) REFERENCES {fk['to_table']}({fk['to_column']})"
                )
            summary.append("\n".join(fk_texts))

        include_samples = index < SCHEMA_SAMPLE_LIMIT
        if include_samples:
            if uses_mssql():
                quoted = _quote_mssql_table(table_name)
                sample_sql = f"SELECT TOP 3 * FROM {quoted};"
            else:
                sample_sql = f"SELECT * FROM {table_name} LIMIT 3;"
            columns, rows, _ = execute_query(sample_sql, db_path)
            if rows:
                summary.append("  Sample Rows:")
                for row in rows:
                    summary.append(f"    {row}")
        else:
            summary.append("  (Sample rows omitted for brevity — columns listed above.)")

        summary.append("-" * 40)

    if len(table_names) > SCHEMA_SAMPLE_LIMIT:
        summary.append(
            f"Note: Sample rows shown for first {SCHEMA_SAMPLE_LIMIT} tables only. "
            f"All {len(table_names)} tables are listed with columns."
        )

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
