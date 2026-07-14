# AI AGENT - Voice-Activated AI SQL Database Agent 🧠🎙️

AI AGENT is a state-of-the-art, voice-activated full-stack AI database agent. It features a stunning, premium dark-themed glassmorphic interface, allowing you to ask natural language questions using your voice, translates them into SQLite queries, executes them against your database, self-corrects if any SQLite compile errors occur, and reads the final analyst answers aloud!

---

## ✨ Features & Capabilities

*   **🎙️ Real-time Voice to Text**: Utilizes the high-fidelity browser-native **Web Speech API** for instantaneous, zero-latency, keyless voice transcribing that prints words on screen as you talk. Includes a fallback audio recorder to transcribe voice files via **OpenAI Whisper**.
*   **🔊 Text to Speech (TTS)**: Features an analyst voice assistant that speaks the database answers back to you aloud!
*   **🤖 AI Self-Correction Agent Loop**:
    *   Constructs a detailed database schema context (tables, columns, data types, foreign keys, and sample rows).
    *   Generates SQL queries using **OpenAI GPT** (GPT-4o / GPT-4o Mini) with the API key loaded from the server `.env` file (`OPENAI_API_KEY`).
    *   Executes the query and inspects the result.
    *   If a SQLite runtime error occurs, the agent catches the compiler error and recursively feeds it back to the LLM to write a corrected query (up to 3 retries) before delivering results.
*   **🗄️ Relational Database & Uploads**:
    *   Starts pre-populated with a complex sample relational database representing **Employees**, **Projects**, and **Assignments (junction table)**.
    *   **Upload Custom Database**: Satisfies the *"we will give him our database"* requirement! Drag and drop or upload any custom `.db`, `.sqlite`, or `.sqlite3` database to instantly inspect its tables and query it.
    *   **Reset database**: Instantly restores the pre-populated Employees & Projects database at any time.
*   **🎨 Premium Glassmorphic UI**:
    *   Deep space gradient backdrop with glowing cyan, purple, and green highlights.
    *   *Micro-animations & Halo Ripples*: Interactive circular microphone button with live HTML5 Canvas audio frequency waveform visualization.
    *   *Dynamic Schema Accordion*: Shows columns, types, primary and foreign key tags, plus real-time schema searching and instant table data browsing.
    *   *Agent Console log*: Displays the Agent's thought processes (e.g., "Step 1: Reading schema...", "Step 2: Requesting query...", "Step 3: Correcting SQL...", "Succeeded!") inside a scrolling developer console.
    *   *SQL Sandbox Editor*: A manual SQL workspace to edit, compose, and execute raw SQL statements directly.

---

## 🗄️ Database Sample Schema (Employees & Projects)

The database initializes with this multi-table relationship:

*   **`employees`**: Details of engineering developers, designers, product managers, and supervisors, featuring salaries, hire dates, and manager-employee hierarchical self-joins (`manager_id` -> `employees.id`).
*   **`projects`**: Corporate projects with active/planning/completed statuses, budgets, and timeline dates.
*   **`employee_projects`**: Many-to-many link, mapping employees to projects, outlining their weekly hours and individual roles (e.g., Raj Malhotra as the Technical Architect contributing 20 hours per week to Project Alpha).

---

## 🚀 How to Get Started

### 1. Install Dependencies
Ensure you have Python 3.9+ installed, then install the required Python libraries using pip:

```bash
pip3 install -r requirements.txt
```

### 2. SQL Server (optional)

Copy `.env.example` to `.env`, set `DB_ENGINE=mssql` and your server credentials, then test:

```bash
python3 test_mssql.py
python3 inspect_mssql_schema.py   # writes schema_export.txt for review
```

Edit `schema_notes.txt` with business meanings (budget tables, bill status, etc.) to help the AI.

### 3. Start the Server
Run the Flask application:

```bash
python3 app.py
```

This will spin up a local development web server at **`http://localhost:5001`**.

### 4. Open in Browser
Open your browser and navigate to:
👉 **[http://localhost:5001](http://localhost:5001)**

---

## ⚙️ Configuration & Quick Start

1.  **Set your OpenAI API Key**:
    *   Copy `.env.example` to `.env` (if you have not already).
    *   Set `OPENAI_API_KEY=sk-proj-...` in that file. The key is read only on the server — there is no API key field in the UI.
    *   Optionally pick a model under **AI Config** (model choice only; the key stays in `.env`).
2.  **Voice Query**:
    *   Click the central glowing microphone button.
    *   Grant microphone permission to the browser.
    *   Say something like: *"Who all are working on Project Alpha with Raj Malhotra?"*
    *   Click the microphone again to finish, inspect/edit your words if needed, and click **`Execute`**!
3.  **Type Query (Alternative)**:
    *   Go to the **Type Question** tab.
    *   Click **View Sample Questions** for ideas, or type your own.
    *   Click **Execute**.
4.  **Sandbox**:
    *   Browse generated queries, copy them, or click **Edit** to open them inside the SQL Sandbox.
    *   Compose manual SQL queries and click **Run Query** to see immediate grid rows.
