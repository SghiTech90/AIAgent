import os
import tempfile
import werkzeug.utils
from flask import Flask, request, jsonify, render_template, send_from_directory
import database
import agent

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = "ai_sql_agent_super_secret_key"

# Define workspace directories
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(WORKSPACE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_DB_EXTENSIONS = {'db', 'sqlite', 'sqlite3'}
ALLOWED_AUDIO_EXTENSIONS = {'wav', 'webm', 'mp3', 'm4a', 'ogg'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Ensure database is initialized on startup if it doesn't exist
if not os.path.exists(database.DEFAULT_DB_PATH):
    print("Database data.db not found. Initializing now...")
    database.init_db()

@app.route('/')
def index():
    """Render the main index page."""
    return render_template('index.html')

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
    data = request.json or {}
    question = data.get('question')
    provider = data.get('provider', 'google')  # 'google' or 'openai'
    model_name = data.get('model_name')
    api_key = data.get('api_key')

    if not question:
        return jsonify({"success": False, "error": "Question is required."})
    
    if not api_key:
        return jsonify({"success": False, "error": "API Key is required to call the AI agent."})

    # Set default model name if not provided
    if not model_name:
        model_name = "gemini-1.5-flash" if provider == "google" else "gpt-4o-mini"

    print(f"Processing query: '{question}' using {provider} ({model_name})")
    
    # Run the AI SQL Agent
    result = agent.run_agent(
        question=question,
        provider=provider,
        model_name=model_name,
        api_key=api_key
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
    if lower_query.startswith("drop database") or "sqlite_master" in lower_query and "delete" in lower_query:
        return jsonify({"success": False, "error": "This operation is restricted for database safety."})

    columns, rows, error = database.execute_query(sql_query)
    if error:
        return jsonify({"success": False, "error": error})
    
    return jsonify({
        "success": True,
        "columns": columns,
        "rows": rows
    })

@app.route('/api/reset_db', methods=['POST'])
def reset_db_endpoint():
    """Reset the database to the standard rich Employees & Projects sample data."""
    try:
        database.init_db()
        return jsonify({"success": True, "message": "Database reset to sample data successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/upload_db', methods=['POST'])
def upload_db_endpoint():
    """Upload a custom SQLite database file to replace the active one."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request."})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected for uploading."})
    
    if file and allowed_file(file.filename, ALLOWED_DB_EXTENSIONS):
        try:
            # Save the uploaded database file as the active default database (data.db)
            # Make sure we close existing connections before overwriting
            target_path = database.DEFAULT_DB_PATH
            
            # Temporary file first to verify it's a valid SQLite file
            temp_path = os.path.join(UPLOAD_FOLDER, "temp_uploaded.db")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            file.save(temp_path)
            
            # Test connection to make sure it's a valid sqlite database
            import sqlite3
            conn = None
            try:
                conn = sqlite3.connect(temp_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                conn.close()
            except sqlite3.Error as se:
                if conn: conn.close()
                os.remove(temp_path)
                return jsonify({"success": False, "error": f"Invalid SQLite database file: {str(se)}"})

            # Overwrite active database file
            if os.path.exists(target_path):
                os.remove(target_path)
            os.rename(temp_path, target_path)

            return jsonify({
                "success": True, 
                "message": "Custom SQLite database uploaded successfully! New schema loaded.",
                "tables_found": len(tables)
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Failed to upload database: {str(e)}"})
    else:
        return jsonify({"success": False, "error": "Allowed file types: .db, .sqlite, .sqlite3"})

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio_endpoint():
    """Transcribe recorded voice from binary audio upload using OpenAI Whisper."""
    if 'audio' not in request.files:
        return jsonify({"success": False, "error": "No audio file part in request."})
    
    audio_file = request.files['audio']
    api_key = request.form.get('api_key')

    if audio_file.filename == '':
        return jsonify({"success": False, "error": "No audio file selected."})

    if not api_key:
        return jsonify({"success": False, "error": "OpenAI API Key is required for backend audio transcription."})

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
                    file=f
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
    # Run the server locally on port 5001
    print("Starting Voice AI SQL Agent Web Server on http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)
