"""
Step 4: Dump SQL Server schema + sample rows to schema_export.txt
Run: python3 inspect_mssql_schema.py
"""
import os

from dotenv import load_dotenv

import database

load_dotenv()

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_export.txt")


def main():
    if not database.uses_mssql():
        print("Set DB_ENGINE=mssql in .env first.")
        return

    database.test_connection()
    text = database.get_schema_summary_text()
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(text)
    schema = database.get_schema()
    print(f"Exported {len(schema)} tables to {OUTPUT}")


if __name__ == "__main__":
    main()
