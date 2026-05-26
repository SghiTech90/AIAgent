import sqlite3
import os

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")

def get_db_connection(db_path=DEFAULT_DB_PATH):
    """Establish a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path=DEFAULT_DB_PATH):
    """
    Initialize the database, creating the schema and inserting
    sample data for Employees, Projects, and assignments.
    """
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception as e:
            print(f"Error removing existing database: {e}")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Create Employees table
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

    # 2. Create Projects table
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

    # 3. Create Employee Projects (Many-to-Many junction table)
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

    # Insert sample Employees (including managers)
    # Priya Sharma is the Department Head / Manager
    cursor.execute("""
    INSERT INTO employees (id, name, role, department, salary, hire_date, manager_id, email) VALUES
    (1, 'Priya Sharma', 'Engineering Director', 'Engineering', 145000.00, '2021-03-15', NULL, 'priya.sharma@company.com');
    """)

    # Other employees, reporting to Priya (manager_id = 1) or other supervisors
    employees = [
        (2, 'Raj Malhotra', 'Senior Lead Developer', 'Engineering', 115000.00, '2022-06-01', 1, 'raj.malhotra@company.com'),
        (3, 'Amit Patel', 'Senior UX/UI Designer', 'Design', 95000.00, '2023-01-10', 1, 'amit.patel@company.com'),
        (4, 'Rohan Mehta', 'Frontend Engineer', 'Engineering', 85000.00, '2023-08-15', 2, 'rohan.mehta@company.com'),
        (5, 'Sunita Rao', 'Backend Engineer', 'Engineering', 90000.00, '2022-11-20', 2, 'sunita.rao@company.com'),
        (6, 'Neha Gupta', 'Data Scientist', 'Analytics', 105000.00, '2023-02-28', 1, 'neha.gupta@company.com'),
        (7, 'Vikram Singh', 'QA Engineer', 'Engineering', 75000.00, '2024-01-05', 2, 'vikram.singh@company.com'),
        (8, 'Sarah Johnson', 'Product Manager', 'Product', 120000.00, '2022-04-10', None, 'sarah.j@company.com')
    ]
    cursor.executemany("""
    INSERT INTO employees (id, name, role, department, salary, hire_date, manager_id, email)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, employees)

    # Insert sample Projects
    projects = [
        (101, 'Project Alpha', 'Next-generation AI core engine and query processor.', 250000.00, '2025-01-10', '2026-06-30', 'Active'),
        (102, 'Project Beta', 'Modern cloud migration and API infrastructure overhaul.', 180000.00, '2025-03-01', '2025-12-15', 'Active'),
        (103, 'Project Gamma', 'Redesign of customer portal and analytics dashboard.', 95000.00, '2025-05-01', '2025-10-31', 'Planning'),
        (104, 'Project Delta', 'Automated security vulnerability scanner tool.', 150000.00, '2024-06-01', '2025-04-30', 'Completed')
    ]
    cursor.executemany("""
    INSERT INTO projects (id, name, description, budget, start_date, end_date, status)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, projects)

    # Insert assignments mapping employees to projects
    assignments = [
        # Project Alpha (101) - Active
        (2, 101, 20, 'Technical Architect'),    # Raj Malhotra
        (4, 101, 30, 'Frontend Lead'),          # Rohan Mehta
        (5, 101, 30, 'Backend Developer'),       # Sunita Rao
        (6, 101, 15, 'Data Engineer'),           # Neha Gupta
        (8, 101, 15, 'Product Lead'),            # Sarah Johnson

        # Project Beta (102) - Active
        (2, 102, 20, 'Lead Consultant'),        # Raj Malhotra
        (5, 102, 10, 'Cloud Infrastructure'),    # Sunita Rao
        (7, 102, 40, 'QA Automation Lead'),      # Vikram Singh
        (8, 102, 20, 'Product Owner'),           # Sarah Johnson

        # Project Gamma (103) - Planning
        (3, 103, 35, 'Lead UX/UI Designer'),     # Amit Patel
        (4, 103, 10, 'UI Prototyper'),           # Rohan Mehta
        (8, 103, 5, 'Advisory PM'),              # Sarah Johnson

        # Project Delta (104) - Completed
        (2, 104, 0, 'Security Advisor'),        # Raj Malhotra (completed)
        (5, 104, 0, 'Security Implementation')  # Sunita Rao (completed)
    ]
    cursor.executemany("""
    INSERT INTO employee_projects (employee_id, project_id, hours_per_week, role_in_project)
    VALUES (?, ?, ?, ?);
    """, assignments)

    conn.commit()
    conn.close()
    print(f"Database initialized successfully at {db_path}!")

def execute_query(query, db_path=DEFAULT_DB_PATH):
    """
    Execute a query. If it is a SELECT query, returns columns and rows.
    If it is a modification query, commits and returns status.
    Returns: (columns, rows, error_message)
    """
    conn = None
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(query)

        # Check if the query returns data (is a SELECT-like statement)
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = [dict(row) for row in cursor.fetchall()]
            return columns, rows, None
        else:
            conn.commit()
            return [], [{"affected_rows": cursor.rowcount}], None
    except sqlite3.Error as e:
        return None, None, str(e)
    finally:
        if conn:
            conn.close()

def get_schema(db_path=DEFAULT_DB_PATH):
    """
    Extract the database schema detailing tables, columns, data types,
    primary keys, and foreign keys in a structured dictionary.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Get list of tables (excluding sqlite internal tables)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row['name'] for row in cursor.fetchall()]

    schema = {}
    for table in tables:
        # Get column details
        cursor.execute(f"PRAGMA table_info({table});")
        columns_info = cursor.fetchall()

        # Get foreign key details
        cursor.execute(f"PRAGMA foreign_key_list({table});")
        fk_info = cursor.fetchall()

        columns = []
        for col in columns_info:
            columns.append({
                "name": col['name'],
                "type": col['type'],
                "notnull": bool(col['notnull']),
                "pk": bool(col['pk'])
            })

        foreign_keys = []
        for fk in fk_info:
            foreign_keys.append({
                "from_column": fk['from'],
                "to_table": fk['table'],
                "to_column": fk['to']
            })

        schema[table] = {
            "columns": columns,
            "foreign_keys": foreign_keys
        }

    conn.close()
    return schema

def get_table_data(table_name, db_path=DEFAULT_DB_PATH, limit=50):
    """Retrieve all rows for a given table, safely."""
    # Check if table name is valid to prevent SQL injection
    schema = get_schema(db_path)
    if table_name not in schema:
        raise ValueError(f"Table '{table_name}' does not exist.")

    columns, rows, error = execute_query(f"SELECT * FROM {table_name} LIMIT {limit};", db_path)
    return {
        "columns": columns,
        "rows": rows,
        "error": error
    }

def get_schema_summary_text(db_path=DEFAULT_DB_PATH):
    """
    Generate a highly informative text representation of the schema.
    This is passed directly to the LLM agent to understand table relations.
    """
    schema = get_schema(db_path)
    summary = []
    
    for table_name, details in schema.items():
        summary.append(f"Table: {table_name}")
        
        # Columns
        col_texts = []
        for col in details["columns"]:
            pk_suffix = " (PRIMARY KEY)" if col["pk"] else ""
            notnull_suffix = " NOT NULL" if col["notnull"] else ""
            col_texts.append(f"  - {col['name']} ({col['type']}){pk_suffix}{notnull_suffix}")
        summary.append("\n".join(col_texts))
        
        # Foreign Keys
        if details["foreign_keys"]:
            fk_texts = []
            for fk in details["foreign_keys"]:
                fk_texts.append(f"  - FOREIGN KEY ({fk['from_column']}) REFERENCES {fk['to_table']}({fk['to_column']})")
            summary.append("\n".join(fk_texts))
            
        # Sample rows for better context
        columns, rows, _ = execute_query(f"SELECT * FROM {table_name} LIMIT 3;", db_path)
        if rows:
            summary.append("  Sample Rows:")
            for row in rows:
                summary.append(f"    {dict(row)}")
        summary.append("-" * 40)
        
    return "\n".join(summary)

if __name__ == "__main__":
    # Test initialization
    init_db()
    print("Schema Summary:")
    print(get_schema_summary_text())
