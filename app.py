import os
import tempfile
import werkzeug.utils
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS

load_dotenv()

import database
import agent

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = "ai_sql_agent_super_secret_key"

_cors_origins = os.getenv("CORS_ORIGINS", "*")
CORS(app, origins=_cors_origins.split(",") if _cors_origins != "*" else "*")


def _resolve_api_key():
    """Load OpenAI API key from server .env only (OPENAI_API_KEY)."""
    return os.getenv("OPENAI_API_KEY")


def _resolve_model_name(model_name):
    if model_name:
        return model_name
    return os.getenv("DEFAULT_LLM_MODEL", "gpt-4o-mini")


def _build_scoped_question(question, office=None, category=None):
    """Scope NL question to office and budget category for mobile Ask AI."""
    parts = []
    if office:
        parts.append(f"Office: {office}.")
    if category:
        parts.append(f"Budget category: {category}.")
    parts.append(f"Question: {question}")
    return " ".join(parts)


def _check_api_token():
    """Optional bearer-style check for mobile clients."""
    expected = os.getenv("AI_AGENT_API_TOKEN")
    if not expected:
        return None
    token = request.headers.get("X-API-Token") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if token != expected:
        return jsonify({"success": False, "error": "Unauthorized."}), 401
    return None

# Define workspace directories
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(WORKSPACE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_DB_EXTENSIONS = {'db', 'sqlite', 'sqlite3'}
ALLOWED_AUDIO_EXTENSIONS = {'wav', 'webm', 'mp3', 'm4a', 'ogg'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Online database connection check deferred to runtime to prevent gunicorn worker hang

@app.route('/')
def index():
    """Render the main index page."""
    return render_template('index.html')

@app.route('/api/db_info', methods=['GET'])
def get_db_info_endpoint():
    """Active database engine and display label for the UI."""
    try:
        if database.uses_mssql():
            database.test_connection()
        schema = database.get_schema()
        return jsonify({
            "success": True,
            "engine": database.get_db_dialect(),
            "label": database.get_db_label(),
            "table_count": len(schema),
            "read_only": database.uses_mssql() and os.getenv("DB_READ_ONLY", "true").lower() == "true",
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/schema', methods=['GET'])
def get_schema_endpoint():
    """Retrieve the current database schema."""
    try:
        schema = database.get_schema()
        return jsonify({"success": True, "schema": schema})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/tables', methods=['GET'])
def get_tables_endpoint():
    """Retrieve list of all tables in the database."""
    try:
        schema = database.get_schema()
        return jsonify({"success": True, "tables": list(schema.keys())})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/table/<table_name>', methods=['GET'])
def get_table_data_endpoint(table_name):
    """Retrieve data rows and columns for a specific table."""
    try:
        limit = request.args.get('limit', default=50, type=int)
        data = database.get_table_data(table_name, limit=limit)
        if data["error"]:
            return jsonify({"success": False, "error": data["error"]})
        return jsonify({
            "success": True, 
            "columns": data["columns"], 
            "rows": data["rows"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/query', methods=['POST'])
def process_query_endpoint():
    """Process a natural language query via the AI Agent."""
    auth_error = _check_api_token()
    if auth_error:
        return auth_error

    data = request.json or {}
    question = data.get('question')
    office = data.get('office')
    category = data.get('category')
    model_name = _resolve_model_name(data.get('model_name'))
    api_key = _resolve_api_key()
    language = (data.get('language') or 'en').lower()
    if language not in ('en', 'mr'):
        language = 'en'

    if not question:
        return jsonify({"success": False, "error": "Question is required."})

    if not api_key:
        return jsonify({
            "success": False,
            "error": "API Key is required. Set OPENAI_API_KEY in the server .env file.",
        })

    scoped_question = _build_scoped_question(question, office=office, category=category)
    print(f"Processing query: '{scoped_question}' using OpenAI ({model_name})")

    result = agent.run_agent(
        question=scoped_question,
        model_name=model_name,
        api_key=api_key,
        language=language,
    )
    
    return jsonify(result)

@app.route('/api/manual_sql', methods=['POST'])
def process_manual_sql_endpoint():
    """Execute raw SQL statements directly in the SQL sandbox."""
    data = request.json or {}
    sql_query = data.get('query')

    if not sql_query:
        return jsonify({"success": False, "error": "SQL query is required."})
    
    # Block extremely destructive queries just for basic safety
    # (Though user runs locally, let's keep it safe)
    lower_query = sql_query.lower().strip()
    blocked = (
        lower_query.startswith("drop database")
        or ("sqlite_master" in lower_query and "delete" in lower_query)
        or lower_query.startswith("drop table")
        or lower_query.startswith("truncate table")
    )
    if blocked:
        return jsonify({"success": False, "error": "This operation is restricted for database safety."})

    columns, rows, error = database.execute_query(sql_query)
    if error:
        return jsonify({"success": False, "error": error})
    
    return jsonify({
        "success": True,
        "columns": columns,
        "rows": rows
    })

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio_endpoint():
    """Transcribe recorded voice from binary audio upload using OpenAI Whisper."""
    if 'audio' not in request.files:
        return jsonify({"success": False, "error": "No audio file part in request."})
    
    audio_file = request.files['audio']
    api_key = _resolve_api_key()
    language = (request.form.get('language') or 'en').lower()
    whisper_lang = 'mr' if language == 'mr' else 'en'

    if audio_file.filename == '':
        return jsonify({"success": False, "error": "No audio file selected."})

    if not api_key:
        return jsonify({
            "success": False,
            "error": "OpenAI API Key is required for audio transcription. Set OPENAI_API_KEY in the server .env file.",
        })

    if audio_file and allowed_file(audio_file.filename, ALLOWED_AUDIO_EXTENSIONS):
        try:
            # Save to temporary file with correct extension
            ext = audio_file.filename.rsplit('.', 1)[1].lower()
            temp_dir = tempfile.gettempdir()
            temp_file_path = os.path.join(temp_dir, f"recorded_voice.{ext}")
            
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                
            audio_file.save(temp_file_path)
            
            # Send to OpenAI Whisper
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            with open(temp_file_path, "rb") as f:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=whisper_lang,
                )
            
            # Cleanup
            os.remove(temp_file_path)
            
            return jsonify({
                "success": True, 
                "text": transcription.text
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Transcription failed: {str(e)}"})
    else:
        return jsonify({"success": False, "error": "Invalid audio file format."})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    print(f"Starting Voice AI SQL Agent Web Server on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')