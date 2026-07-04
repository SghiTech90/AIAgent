import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

server = os.environ["DB_SERVER"]
database = os.environ["DB_DATABASE"]
user = os.environ["DB_USER"]
password = os.environ["DB_PASSWORD"]
port = os.getenv("DB_PORT", "1433")

driver = "ODBC Driver 18 for SQL Server"
conn_str = (
    f"DRIVER={{{driver}}};"
    f"SERVER={server},{port};"
    f"DATABASE={database};"
    f"UID={user};"
    f"PWD={password};"
    f"TrustServerCertificate=yes;"
    f"Encrypt=no;"
)

conn = pyodbc.connect(conn_str, timeout=15)
cur = conn.cursor()
cur.execute("""
    SELECT TABLE_SCHEMA, TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_SCHEMA, TABLE_NAME
""")
for row in cur.fetchall():
    print(f"{row[0]}.{row[1]}")
conn.close()
print("OK")