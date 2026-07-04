import re
import traceback
from openai import OpenAI
import database

DEFAULT_MODEL = "gpt-4o-mini"


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
    if language == "mr":
        return (
            "9. The user question may be in Marathi (मराठी), English, or mixed. Understand the intent in any language.\n"
            "10. SQL identifiers (table/column names) must match the schema exactly; only the user's natural language varies."
        )
    return ""


def _language_answer_rules(language):
    if language == "mr":
        return (
            "5. Write the entire answer in Marathi (मराठी) using clear, simple administrative language.\n"
            "6. Keep numbers, dates, and proper nouns from the database as shown in the results."
        )
    return "5. Write the answer in English unless the user clearly used another language."


def _sql_agent_instructions(dialect, language="en"):
    lang_rules = _language_sql_rules(language)
    if dialect == "mssql":
        return (
            "You are an expert AI SQL Agent for Microsoft SQL Server (T-SQL).\n"
            "Your task is to write a single executable T-SQL query that accurately answers the user's question.\n"
            "Rules:\n"
            "1. Study the database schema, foreign key relations, and sample data carefully.\n"
            "2. Use fully qualified table names with brackets, e.g. [dbo].[BudgetMasterRoad].\n"
            "3. Use TOP n for row limits (not LIMIT). Use GETDATE() for current date/time.\n"
            "4. Join tables correctly using foreign keys and matching column names.\n"
            "5. Output ONLY the T-SQL query inside a ```sql ... ``` block or <sql>...</sql> tags.\n"
            "6. NEVER explain the query. Do NOT run INSERT, UPDATE, DELETE, DROP, or EXEC unless explicitly requested.\n"
            "7. For text search use LIKE with LOWER() when case-insensitive matching is needed.\n"
            "8. Prefer readable column aliases when aggregating."
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


def generate_sql_agent(question, schema_text, model_name, api_key, logs_callback, dialect="sqlite", language="en"):
    """AI Agent Loop to generate, execute, and self-correct SQL queries."""
    dialect_label = "T-SQL (SQL Server)" if dialect == "mssql" else "SQLite"
    system_instruction = _sql_agent_instructions(dialect, language)

    prompt = f"""
Here is the {dialect_label} Database Schema:
========================================
{schema_text}
========================================

User Question: "{question}"

Generate the SQL query to fetch the correct data:
"""

    logs_callback("Step 1: Analyzing schema and crafting query prompt...")

    sql_query = ""
    error_message = None
    columns, rows = None, None
    max_retries = 3
    retry_count = 0

    while retry_count <= max_retries:
        try:
            if retry_count == 0:
                logs_callback(f"Step 2: Requesting SQL query from OpenAI ({model_name})...")
                response = call_llm(prompt, system_instruction, model_name, api_key)
            else:
                logs_callback(f"Step 2 (Retry {retry_count}): Sending execution error back to OpenAI for correction...")
                correction_prompt = f"""
You previously generated this SQL query:
```sql
{sql_query}
```

However, executing this query threw the following database error:
"{error_message}"

Please inspect the database schema carefully, identify the bug in your query, and write a corrected {dialect_label} query.
Output ONLY the corrected SQL query inside ```sql ... ``` block or <sql>...</sql> tags.
"""
                response = call_llm(correction_prompt, system_instruction, model_name, api_key)

            sql_query = clean_sql(response)
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


def formulate_answer(question, sql_query, results, model_name, api_key, logs_callback, language="en"):
    """Generate a natural language response based on the query results."""
    logs_callback("Step 5: Formulating natural language answer from database results...")

    system_instruction = (
        "You are a friendly and professional database AI analyst.\n"
        "Your task is to take the user's question, the SQL query that was executed, and the raw SQL query results,\n"
        "and formulate a clear, comprehensive, and accurate natural language answer.\n"
        "Rules:\n"
        "1. Ground your answer completely in the query results. Do NOT make up information.\n"
        "2. If no rows were returned, politely inform the user that no matching records were found in the database.\n"
        "3. Present names, dates, financial figures (like salaries and budgets), and project details beautifully and clearly.\n"
        "4. Be direct and avoid saying 'According to the SQL query...'. Talk like a smart analyst speaking to a manager.\n"
        + _language_answer_rules(language)
    )

    prompt = f"""
User Question: "{question}"
SQL Query Executed:
```sql
{sql_query}
```
Query Results (JSON format):
{results}

Formulate a natural language answer based on these details:
"""

    try:
        answer = call_llm(prompt, system_instruction, model_name, api_key)
        logs_callback("Step 6: Answer successfully generated!")
        return answer
    except Exception as e:
        error_msg = f"Failed to formulate answer: {str(e)}"
        logs_callback(error_msg)
        return f"Query succeeded, but could not formulate natural language answer. Raw Results: {results}"


def run_agent(question, model_name, api_key, db_path=database.DEFAULT_DB_PATH, language="en"):
    """The main coordinator for the AI SQL Agent."""
    logs = []

    def logs_callback(msg):
        logs.append(msg)
        print(msg)

    if not api_key:
        return {
            "success": False,
            "error": "Missing API Key. Set OPENAI_API_KEY in server .env or provide a key in settings.",
            "logs": ["Failed: OpenAI API key is required."],
        }

    if not model_name:
        model_name = DEFAULT_MODEL

    try:
        schema_text = database.get_schema_summary_text(db_path)
        dialect = database.get_db_dialect()

        sql_agent_result = generate_sql_agent(
            question=question,
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
