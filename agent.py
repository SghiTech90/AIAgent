import re
import traceback
import google.generativeai as genai
from openai import OpenAI
import database

def clean_sql(sql_text):
    """
    Extract the raw SQL query from potential markdown formatting or XML tags.
    """
    if not sql_text:
        return ""
    
    # Remove markdown code blocks if present
    sql_text = re.sub(r'```sql\s*(.*?)\s*```', r'\1', sql_text, flags=re.DOTALL | re.IGNORECASE)
    sql_text = re.sub(r'```\s*(.*?)\s*```', r'\1', sql_text, flags=re.DOTALL)
    
    # Remove XML-like tags <sql>...</sql> if present
    sql_text = re.sub(r'<sql>\s*(.*?)\s*</sql>', r'\1', sql_text, flags=re.DOTALL | re.IGNORECASE)
    
    # Clean whitespace and strip semicolon at the end (SQLite handles it, but let's be clean)
    sql_text = sql_text.strip()
    
    # Make sure we don't return an empty query
    return sql_text

def call_llm(prompt, system_instruction, provider, model_name, api_key):
    """
    Call the appropriate LLM provider (Gemini or OpenAI) with the given prompt.
    """
    if not api_key:
        raise ValueError(f"API key is required for {provider}")

    if provider == "google":
        # Configure Gemini
        genai.configure(api_key=api_key)
        
        # Select appropriate model
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1}  # Low temperature for highly deterministic SQL
        )
        return response.text.strip()
        
    elif provider == "openai":
        # Configure OpenAI
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    else:
        raise ValueError(f"Unknown provider: {provider}")

def generate_sql_agent(question, schema_text, provider, model_name, api_key, logs_callback):
    """
    AI Agent Loop to generate, execute, and self-correct SQL queries.
    """
    # 1. System instruction for SQL Generation
    system_instruction = (
        "You are an expert AI SQL Agent for SQLite databases.\n"
        "Your task is to write a single executable SQLite query that accurately answers the user's question.\n"
        "Rules:\n"
        "1. Study the database schema, foreign key relations, and sample data carefully.\n"
        "2. Join tables correctly using proper foreign keys.\n"
        "3. Output ONLY the SQLite query. Place it inside a ```sql ... ``` block or <sql>...</sql> tags.\n"
        "4. NEVER explain the query or output anything else in this turn. Just output the query.\n"
        "5. Do NOT perform any mutating operations (INSERT, UPDATE, DELETE, DROP) unless explicitly requested. ONLY generate SELECT queries by default.\n"
        "6. Handle case-insensitive matching where appropriate using 'LIKE' or 'LOWER()' if names or text searches are involved (e.g. search for 'raj' should match 'Raj Malhotra')."
    )

    prompt = f"""
Here is the SQLite Database Schema:
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
                logs_callback(f"Step 2: Requesting SQL query from {provider} ({model_name})...")
                response = call_llm(prompt, system_instruction, provider, model_name, api_key)
            else:
                logs_callback(f"Step 2 (Retry {retry_count}): Sending execution error back to {provider} for correction...")
                correction_prompt = f"""
You previously generated this SQL query:
```sql
{sql_query}
```

However, executing this query threw the following SQLite error:
"{error_message}"

Please inspect the database schema carefully, identify the bug in your query, and write a corrected SQLite query.
Output ONLY the corrected SQL query inside ```sql ... ``` block or <sql>...</sql> tags.
"""
                response = call_llm(correction_prompt, system_instruction, provider, model_name, api_key)

            # Clean and parse SQL
            sql_query = clean_sql(response)
            logs_callback(f"Generated SQL:\n{sql_query}")

            if not sql_query:
                error_message = "No SQL query could be parsed from LLM response."
                logs_callback(f"Parser error: {error_message}")
                retry_count += 1
                continue

            # Execute SQL query on SQLite
            logs_callback("Step 3: Executing SQL query on the SQLite database...")
            columns, rows, error_message = database.execute_query(sql_query)

            if error_message:
                logs_callback(f"Database execution failed: {error_message}")
                retry_count += 1
            else:
                logs_callback("Step 4: Query executed successfully! Retrieved data rows.")
                break  # Success! Exit loop

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
            "results": []
        }

    return {
        "success": True,
        "query": sql_query,
        "columns": columns,
        "results": rows
    }

def formulate_answer(question, sql_query, results, provider, model_name, api_key, logs_callback):
    """
    Generate a highly professional, user-friendly natural language response based on the query results.
    """
    logs_callback("Step 5: Formulating natural language answer from database results...")
    
    system_instruction = (
        "You are a friendly and professional database AI analyst.\n"
        "Your task is to take the user's question, the SQL query that was executed, and the raw SQL query results,\n"
        "and formulate a clear, comprehensive, and accurate natural language answer.\n"
        "Rules:\n"
        "1. Ground your answer completely in the query results. Do NOT make up information.\n"
        "2. If no rows were returned, politely inform the user that no matching records were found in the database.\n"
        "3. Present names, dates, financial figures (like salaries and budgets), and project details beautifully and clearly.\n"
        "4. Be direct and avoid saying 'According to the SQL query...'. Talk like a smart analyst speaking to a manager."
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
        answer = call_llm(prompt, system_instruction, provider, model_name, api_key)
        logs_callback("Step 6: Answer successfully generated!")
        return answer
    except Exception as e:
        error_msg = f"Failed to formulate answer: {str(e)}"
        logs_callback(error_msg)
        return f"Query succeeded, but could not formulate natural language answer. Raw Results: {results}"

def run_agent(question, provider, model_name, api_key, db_path=database.DEFAULT_DB_PATH):
    """
    The main coordinator for the AI SQL Agent.
    """
    logs = []
    def logs_callback(msg):
        logs.append(msg)
        print(msg)

    # Validate provider and credentials
    if not api_key:
        return {
            "success": False,
            "error": "Missing API Key. Please provide a valid Gemini or OpenAI API Key in the settings.",
            "logs": ["Failed: API Key is required."]
        }

    try:
        # Get schema
        schema_text = database.get_schema_summary_text(db_path)
        
        # Execute the agent loop to generate and run SQL
        sql_agent_result = generate_sql_agent(
            question=question,
            schema_text=schema_text,
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            logs_callback=logs_callback
        )
        
        if not sql_agent_result["success"]:
            return {
                "success": False,
                "error": sql_agent_result["error"],
                "query": sql_agent_result["query"],
                "logs": logs
            }
            
        # Formulate final response
        answer = formulate_answer(
            question=question,
            sql_query=sql_agent_result["query"],
            results=sql_agent_result["results"],
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            logs_callback=logs_callback
        )
        
        return {
            "success": True,
            "query": sql_agent_result["query"],
            "columns": sql_agent_result["columns"],
            "results": sql_agent_result["results"],
            "answer": answer,
            "logs": logs
        }
        
    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "logs": logs + [f"Fatal Error: {str(e)}"]
        }
