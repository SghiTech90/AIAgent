/* ==========================================================================
   AI AGENT - Voice-Activated AI Database Agent
   Frontend Controller & Audio Processing Engine
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // --- Application State ---
    const state = {
        activeTab: 'tab-voice',
        apiConfig: {
            modelName: 'gpt-4o-mini',
            apiKey: ''
        },
        voice: {
            isRecording: false,
            recognition: null,
            mediaRecorder: null,
            audioChunks: [],
            audioContext: null,
            analyser: null,
            dataArray: null,
            source: null,
            animationFrameId: null
        },
        activeTable: null,
        inputLanguage: 'en'
    };

    const LANGUAGE_CONFIG = {
        en: {
            speechLang: 'en-US',
            ttsLang: 'en-US',
            whisperLang: 'en',
            voicePlaceholder: 'Your spoken words will appear here in real-time... Feel free to edit them before asking the agent.',
            textPlaceholder: 'Type your question in English...',
            voiceStatusIdle: 'Click the microphone & start speaking',
            listening: 'Listening... Speak now (English)',
        },
        mr: {
            speechLang: 'mr-IN',
            ttsLang: 'mr-IN',
            whisperLang: 'mr',
            voicePlaceholder: 'तुमचे बोललेले शब्द येथे दिसतील... एजंटला विचारण्यापूर्वी संपादित करू शकता.',
            textPlaceholder: 'तुमचा प्रश्न मराठीत लिहा...',
            voiceStatusIdle: 'मायक्रोफोन दाबा आणि मराठीत बोला',
            listening: 'ऐकत आहे... आता मराठीत बोला',
        },
    };

    // --- DOM Elements Cache ---
    const els = {
        // Tabs
        tabBtns: document.querySelectorAll('.tab-btn'),
        tabContents: document.querySelectorAll('.tab-content'),
        
        // Configuration
        btnSettingsToggle: document.getElementById('btn-settings-toggle'),
        settingsDropdown: document.getElementById('settings-dropdown'),
        llmModel: document.getElementById('llm-model'),
        apiKey: document.getElementById('api-key'),
        apiKeyLabel: document.getElementById('api-key-label'),
        btnToggleKeyVisibility: document.getElementById('btn-toggle-key-visibility'),
        btnSaveSettings: document.getElementById('btn-save-settings'),
        inputLanguage: document.getElementById('input-language'),
        inputLanguageVoice: document.getElementById('input-language-voice'),
        sampleQueriesEn: document.getElementById('sample-queries-en'),
        sampleQueriesMr: document.getElementById('sample-queries-mr'),
        sampleQueriesHeading: document.getElementById('sample-queries-heading'),

        // Database / Schema
        activeDbName: document.getElementById('active-db-name'),
        dbTablesCount: document.getElementById('db-tables-count'),
        btnUploadTrigger: document.getElementById('btn-upload-trigger'),
        dbFileInput: document.getElementById('db-file-input'),
        btnResetDb: document.getElementById('btn-reset-db'),
        btnRefreshSchema: document.getElementById('btn-refresh-schema'),
        schemaSearch: document.getElementById('schema-search'),
        schemaAccordion: document.getElementById('schema-accordion'),

        // Voice Controls
        btnRecord: document.getElementById('btn-record'),
        voicePulseRing: document.getElementById('voice-pulse-ring'),
        voiceStatusText: document.getElementById('voice-status-text'),
        voiceTranscript: document.getElementById('voice-transcript'),
        btnClearTranscript: document.getElementById('btn-clear-transcript'),
        btnAskVoice: document.getElementById('btn-ask-voice'),
        waveformCanvas: document.getElementById('waveform-canvas'),

        // Text Controls
        btnToggleSamples: document.getElementById('btn-toggle-samples'),
        sampleQueriesBox: document.getElementById('sample-queries-box'),
        sampleQueryItems: document.querySelectorAll('.sample-query-item'),
        textQuestion: document.getElementById('text-question'),
        btnAskText: document.getElementById('btn-ask-text'),

        // Sandbox Controls
        btnRunManualSql: document.getElementById('btn-run-manual-sql'),
        btnClearSandbox: document.getElementById('btn-clear-sandbox'),
        sandboxSqlEditor: document.getElementById('sandbox-sql-editor'),
        sandboxError: document.getElementById('sandbox-error'),
        sandboxTableContainer: document.getElementById('sandbox-table-container'),

        // Browser Controls
        browserTableSelect: document.getElementById('browser-table-select'),
        browserRowsCount: document.getElementById('browser-rows-count'),
        browserTableContainer: document.getElementById('browser-table-container'),

        // Agent Thinking Log Panel
        thinkingPanel: document.getElementById('thinking-panel'),
        agentCurrentStatus: document.getElementById('agent-current-status'),
        agentThinkingLogs: document.getElementById('agent-thinking-logs'),

        // Agent Results
        resultsPanel: document.getElementById('results-panel'),
        agentNlAnswer: document.getElementById('agent-nl-answer'),
        btnSpeakAnswer: document.getElementById('btn-speak-answer'),
        generatedSqlCode: document.getElementById('generated-sql-code'),
        btnCopySql: document.getElementById('btn-copy-sql'),
        btnSandboxSql: document.getElementById('btn-sandbox-sql'),
        resultsRecordsCount: document.getElementById('results-records-count'),
        resultsTableContainer: document.getElementById('results-table-container'),
        
        toastContainer: document.getElementById('toast-container')
    };

    // --- Toast Notifications ---
    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let icon = 'fa-circle-info';
        if (type === 'success') icon = 'fa-circle-check';
        if (type === 'error') icon = 'fa-circle-exclamation';

        toast.innerHTML = `
            <i class="fa-solid ${icon} toast-icon"></i>
            <span class="toast-message">${message}</span>
        `;
        els.toastContainer.appendChild(toast);

        // Slide out and remove
        setTimeout(() => {
            toast.style.animation = 'toastAppear 0.3s reverse forwards';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    // --- Initialize Configuration & LocalStorage ---
    function loadSavedConfig() {
        const savedModel = localStorage.getItem('llm_model');
        const savedKey = localStorage.getItem('llm_api_key');

        if (savedModel) {
            state.apiConfig.modelName = savedModel;
            els.llmModel.value = savedModel;
        }

        if (savedKey) {
            state.apiConfig.apiKey = savedKey;
            els.apiKey.value = savedKey;
        }

        const savedLang = localStorage.getItem('input_language');
        if (savedLang && LANGUAGE_CONFIG[savedLang]) {
            setInputLanguage(savedLang, false);
        } else {
            applyInputLanguageUI();
        }
    }

    function getLanguageConfig() {
        return LANGUAGE_CONFIG[state.inputLanguage] || LANGUAGE_CONFIG.en;
    }

    function applyInputLanguageUI() {
        const cfg = getLanguageConfig();
        if (els.voiceTranscript) {
            els.voiceTranscript.placeholder = cfg.voicePlaceholder;
        }
        if (els.textQuestion) {
            els.textQuestion.placeholder = cfg.textPlaceholder;
        }
        if (els.voiceStatusText && !state.voice.isRecording) {
            els.voiceStatusText.textContent = cfg.voiceStatusIdle;
        }
        if (els.inputLanguage) {
            els.inputLanguage.value = state.inputLanguage;
        }
        if (els.inputLanguageVoice) {
            els.inputLanguageVoice.value = state.inputLanguage;
        }
        if (els.sampleQueriesEn && els.sampleQueriesMr) {
            const isMr = state.inputLanguage === 'mr';
            els.sampleQueriesEn.style.display = isMr ? 'none' : 'block';
            els.sampleQueriesMr.style.display = isMr ? 'block' : 'none';
            if (els.sampleQueriesHeading) {
                els.sampleQueriesHeading.textContent = isMr
                    ? 'हे नमुना प्रश्न वापरून पहा:'
                    : 'Try these sample questions:';
            }
        }
        document.documentElement.lang = state.inputLanguage === 'mr' ? 'mr' : 'en';
    }

    function setInputLanguage(lang, showToastMsg = true) {
        if (!LANGUAGE_CONFIG[lang]) {
            lang = 'en';
        }
        if (state.voice.isRecording) {
            stopRecording();
        }
        state.inputLanguage = lang;
        localStorage.setItem('input_language', lang);
        state.voice.recognition = null;
        applyInputLanguageUI();
        if (showToastMsg) {
            showToast(
                lang === 'mr' ? 'मराठी भाषा सक्षम केली.' : 'English language enabled.',
                'success'
            );
        }
    }

    function saveConfig() {
        const modelName = els.llmModel.value;
        const apiKey = els.apiKey.value.strip ? els.apiKey.value.strip() : els.apiKey.value.trim();

        if (!apiKey) {
            showToast("Please provide a valid OpenAI API key.", "error");
            return false;
        }

        state.apiConfig.modelName = modelName;
        state.apiConfig.apiKey = apiKey;

        localStorage.setItem('llm_model', modelName);
        localStorage.setItem('llm_api_key', apiKey);

        if (els.inputLanguage) {
            setInputLanguage(els.inputLanguage.value, false);
        }

        els.settingsDropdown.style.display = 'none';
        showToast("Configuration saved successfully!", "success");
        return true;
    }

    // Toggle Settings Dropdown
    els.btnSettingsToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const display = els.settingsDropdown.style.display;
        els.settingsDropdown.style.display = display === 'block' ? 'none' : 'block';
    });

    document.addEventListener('click', (e) => {
        if (!els.settingsDropdown.contains(e.target) && !els.btnSettingsToggle.contains(e.target)) {
            els.settingsDropdown.style.display = 'none';
        }
    });

    els.settingsDropdown.addEventListener('click', (e) => e.stopPropagation());

    els.btnToggleKeyVisibility.addEventListener('click', () => {
        const type = els.apiKey.getAttribute('type');
        els.apiKey.setAttribute('type', type === 'password' ? 'text' : 'password');
        const icon = els.btnToggleKeyVisibility.querySelector('i');
        icon.className = type === 'password' ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye';
    });

    els.btnSaveSettings.addEventListener('click', saveConfig);

    // --- Tab Switching System ---
    els.tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            
            // Toggle buttons
            els.tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Toggle contents
            els.tabContents.forEach(c => c.classList.remove('active'));
            document.getElementById(targetTab).classList.add('active');

            state.activeTab = targetTab;
            
            // Adjust canvas size if switching to voice
            if (targetTab === 'tab-voice') {
                fitCanvasToContainer();
            }
        });
    });

    // --- Dynamic Schema Explorer & Loading ---
    async function loadDbInfo() {
        try {
            const res = await fetch('/api/db_info');
            const data = await res.json();
            if (!data.success) {
                els.activeDbName.textContent = 'Database connection error';
                showToast(`Database: ${data.error}`, 'error');
                return;
            }
            const engineLabel = data.engine === 'mssql' ? 'SQL Server' : 'SQLite';
            els.activeDbName.textContent = `${data.label} (${engineLabel})`;
            if (data.engine === 'mssql') {
                els.btnUploadTrigger.style.display = 'none';
                els.btnResetDb.style.display = 'none';
                els.dbFileInput.style.display = 'none';
            }
        } catch (err) {
            console.warn('db_info failed', err);
        }
    }

    async function loadSchema() {
        try {
            const res = await fetch('/api/schema');
            const data = await res.json();

            if (!data.success) {
                showToast(`Failed to load schema: ${data.error}`, "error");
                return;
            }

            const schema = data.schema;
            renderSchema(schema);
            updateTableSelectors(schema);
        } catch (err) {
            showToast(`Error connecting to schema API: ${err.message}`, "error");
        }
    }

    function renderSchema(schema) {
        const tables = Object.keys(schema);
        els.dbTablesCount.textContent = `${tables.length} Tables loaded`;
        
        if (tables.length === 0) {
            els.schemaAccordion.innerHTML = `
                <div class="table-placeholder">
                    <i class="fa-solid fa-folder-open placeholder-icon"></i>
                    <span>No tables found in database.</span>
                </div>
            `;
            return;
        }

        els.schemaAccordion.innerHTML = '';
        
        tables.forEach(tableName => {
            const details = schema[tableName];
            const item = document.createElement('div');
            item.className = 'schema-item';
            item.id = `schema-table-${tableName}`;

            const trigger = document.createElement('div');
            trigger.className = 'schema-trigger';
            trigger.innerHTML = `
                <div class="schema-trigger-title">
                    <i class="fa-solid fa-table"></i>
                    <span>${tableName}</span>
                </div>
                <div class="schema-trigger-actions">
                    <button class="btn-view-data" data-table="${tableName}" title="Browse table rows">
                        <i class="fa-solid fa-table-list"></i>
                    </button>
                    <i class="fa-solid fa-chevron-down chevron"></i>
                </div>
            `;

            const content = document.createElement('div');
            content.className = 'schema-content';
            
            const list = document.createElement('ul');
            list.className = 'column-list';

            details.columns.forEach(col => {
                const li = document.createElement('li');
                li.className = 'column-item';
                
                // Identify icon (PK, FK, or standard)
                let iconClass = 'fa-solid fa-circle-dot';
                let iconTitle = 'Column';
                
                if (col.pk) {
                    iconClass = 'fa-solid fa-key pk-icon';
                    iconTitle = 'Primary Key';
                } else {
                    const isFk = details.foreign_keys.find(fk => fk.from_column === col.name);
                    if (isFk) {
                        iconClass = 'fa-solid fa-link fk-icon';
                        iconTitle = `Foreign Key pointing to ${isFk.to_table}(${isFk.to_column})`;
                    }
                }

                const fkMatch = details.foreign_keys.find(fk => fk.from_column === col.name);
                const fkTag = fkMatch ? `<span class="fk-relation-tag" title="References ${fkMatch.to_table}(${fkMatch.to_column})">→ ${fkMatch.to_table}</span>` : '';

                li.innerHTML = `
                    <div class="column-name-type">
                        <i class="${iconClass}" title="${iconTitle}"></i>
                        <span class="column-name">${col.name}</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:6px;">
                        ${fkTag}
                        <span class="column-type">${col.type}</span>
                    </div>
                `;
                list.appendChild(li);
            });

            content.appendChild(list);
            item.appendChild(trigger);
            item.appendChild(content);
            els.schemaAccordion.appendChild(item);

            // Handle accordion expand/collapse
            trigger.addEventListener('click', (e) => {
                // If clicked "View Data" icon, do not expand accordion
                if (e.target.closest('.btn-view-data')) return;
                
                const isActive = item.classList.contains('active');
                
                // Collapse all
                document.querySelectorAll('.schema-item').forEach(el => el.classList.remove('active'));
                
                // Expand current if it wasn't active
                if (!isActive) {
                    item.classList.add('active');
                }
            });

            // Handle "View Data" trigger click
            trigger.querySelector('.btn-view-data').addEventListener('click', () => {
                browseTable(tableName);
            });
        });
    }

    function updateTableSelectors(schema) {
        const tables = Object.keys(schema);
        
        // Main browser tab dropdown
        els.browserTableSelect.innerHTML = '<option value="" disabled selected>Select a table...</option>';
        tables.forEach(tableName => {
            const opt = document.createElement('option');
            opt.value = tableName;
            opt.textContent = tableName;
            els.browserTableSelect.appendChild(opt);
        });
    }

    // Refresh schema manually
    els.btnRefreshSchema.addEventListener('click', () => {
        loadSchema();
        showToast("Schema refreshed.", "info");
    });

    // Schema search filtering
    els.schemaSearch.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const items = els.schemaAccordion.querySelectorAll('.schema-item');

        items.forEach(item => {
            const tableName = item.id.replace('schema-table-', '').toLowerCase();
            const cols = Array.from(item.querySelectorAll('.column-name')).map(c => c.textContent.toLowerCase());
            
            const matchTable = tableName.includes(query);
            const matchCols = cols.some(col => col.includes(query));

            if (matchTable || matchCols) {
                item.style.display = 'block';
                if (query !== '' && matchCols) {
                    item.classList.add('active'); // Expand if matching column
                }
            } else {
                item.style.display = 'none';
                item.classList.remove('active');
            }
        });
    });

    // --- Browser Tab controller ---
    async function browseTable(tableName) {
        state.activeTable = tableName;
        els.browserTableSelect.value = tableName;
        
        // Go to browser tab
        document.getElementById('tab-btn-browser').click();
        
        els.browserTableContainer.innerHTML = `
            <div class="loading-spinner-container">
                <div class="spinner"></div>
                <span class="loading-text">Loading rows from ${tableName}...</span>
            </div>
        `;

        try {
            const res = await fetch(`/api/table/${encodeURIComponent(tableName)}?limit=100`);
            const data = await res.json();

            if (!data.success) {
                els.browserTableContainer.innerHTML = `
                    <div class="error-panel">${data.error}</div>
                `;
                els.browserRowsCount.textContent = 'Error';
                return;
            }

            els.browserRowsCount.textContent = `${data.rows.length} rows`;
            renderGrid(data.columns, data.rows, els.browserTableContainer);
        } catch (err) {
            els.browserTableContainer.innerHTML = `
                <div class="error-panel">Connection failure: ${err.message}</div>
            `;
        }
    }

    els.browserTableSelect.addEventListener('change', (e) => {
        browseTable(e.target.value);
    });

    // --- Grid Rendering Helper ---
    function renderGrid(columns, rows, container) {
        if (!columns || columns.length === 0) {
            container.innerHTML = `
                <div class="table-placeholder">
                    <i class="fa-solid fa-circle-exclamation placeholder-icon"></i>
                    <span>No records fetched or query was a modification structure.</span>
                </div>
            `;
            return;
        }

        const table = document.createElement('table');
        table.className = 'glass-table';
        
        // Header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        columns.forEach(col => {
            const th = document.createElement('th');
            th.textContent = col;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Body
        const tbody = document.createElement('tbody');
        if (rows.length === 0) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = columns.length;
            td.style.textAlign = 'center';
            td.style.color = 'var(--text-muted)';
            td.textContent = 'Zero matching records found.';
            tr.appendChild(td);
            tbody.appendChild(tr);
        } else {
            rows.forEach(row => {
                const tr = document.createElement('tr');
                columns.forEach(col => {
                    const td = document.createElement('td');
                    // Handle null objects beautifully
                    let val = row[col];
                    if (val === null || val === undefined) {
                        td.innerHTML = '<span style="color:var(--text-muted); font-style:italic;">NULL</span>';
                    } else if (typeof val === 'number') {
                        // Format currency if it looks like salary/budget
                        if (col.includes('salary') || col.includes('budget')) {
                            td.textContent = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
                        } else {
                            td.textContent = val;
                        }
                    } else {
                        td.textContent = val;
                    }
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
        }
        table.appendChild(tbody);
        
        container.innerHTML = '';
        container.appendChild(table);
    }

    // --- SQLite DB Uploads and Resets ---
    els.btnUploadTrigger.addEventListener('click', () => {
        els.dbFileInput.click();
    });

    els.dbFileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        showToast("Uploading database...", "info");
        
        try {
            const res = await fetch('/api/upload_db', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (!data.success) {
                showToast(`Upload failed: ${data.error}`, "error");
                return;
            }

            els.activeDbName.textContent = `${file.name} (Custom)`;
            showToast(data.message, "success");
            
            // Re-load schema and clear active search
            els.schemaSearch.value = '';
            loadSchema();
        } catch (err) {
            showToast(`Upload connection error: ${err.message}`, "error");
        }
    });

    els.btnResetDb.addEventListener('click', async () => {
        if (!confirm("Are you sure you want to delete custom modifications and reset the database back to standard Employees & Projects sample tables?")) {
            return;
        }

        showToast("Resetting database...", "info");
        try {
            const res = await fetch('/api/reset_db', { method: 'POST' });
            const data = await res.json();

            if (!data.success) {
                showToast(`Reset failed: ${data.error}`, "error");
                return;
            }

            els.activeDbName.textContent = `data.db (Sample)`;
            showToast("Database restored successfully!", "success");
            
            els.schemaSearch.value = '';
            loadSchema();
        } catch (err) {
            showToast(`Connection failure during reset: ${err.message}`, "error");
        }
    });

    if (els.inputLanguage) {
        els.inputLanguage.addEventListener('change', () => {
            setInputLanguage(els.inputLanguage.value);
        });
    }
    if (els.inputLanguageVoice) {
        els.inputLanguageVoice.addEventListener('change', () => {
            setInputLanguage(els.inputLanguageVoice.value);
        });
    }

    // --- Web Speech API (Client-side Voice Recognition) ---
    function initSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            showToast("Your browser does not support Web Speech recognition. Text entry is supported, and backend voice uploads require configuring OpenAI keys.", "warning");
            return;
        }

        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = getLanguageConfig().speechLang;

        recognition.onstart = () => {
            state.voice.isRecording = true;
            els.btnRecord.classList.add('recording');
            els.voiceStatusText.textContent = getLanguageConfig().listening;
            els.voiceStatusText.classList.add('recording-text');
            showToast("Microphone active. Start speaking!", "info");
            
            // Start visual wave animations
            startAudioWave();
        };

        recognition.onresult = (event) => {
            let transcript = '';
            for (let i = 0; i < event.results.length; ++i) {
                transcript += event.results[i][0].transcript;
            }
            if (transcript && state.voice.isRecording) {
                els.voiceTranscript.value = transcript;
            }
        };

        recognition.onerror = (e) => {
            console.error("Speech Error:", e);
            if (e.error === 'not-allowed') {
                showToast("Microphone access denied! Check browser permissions.", "error");
                stopRecording();
            } else if (e.error === 'no-speech') {
                showToast("No speech detected. Mic still open.", "info");
            }
        };

        recognition.onend = () => {
            // Only toggle states if recording was active
            if (state.voice.isRecording) {
                stopRecording();
            }
        };

        state.voice.recognition = recognition;
    }

    function startRecording() {
        if (!state.voice.recognition) {
            initSpeechRecognition();
        }

        if (state.voice.recognition) {
            try {
                state.voice.recognition.start();
            } catch (err) {
                console.error("Failed to start speech:", err);
            }
        } else {
            // Setup backend Audio Recording Fallback if Web Speech API isn't built in
            startMediaRecorderRecording();
        }
    }

    function stopRecording() {
        state.voice.isRecording = false;
        els.btnRecord.classList.remove('recording');
        els.voiceStatusText.textContent = getLanguageConfig().voiceStatusIdle;
        els.voiceStatusText.classList.remove('recording-text');
        
        if (state.voice.recognition) {
            try {
                state.voice.recognition.stop();
            } catch (err) { }
        } else if (state.voice.mediaRecorder) {
            stopMediaRecorderRecording();
        }
        
        stopAudioWave();
    }

    els.btnRecord.addEventListener('click', () => {
        if (state.voice.isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    });

    els.btnClearTranscript.addEventListener('click', () => {
        els.voiceTranscript.value = '';
    });

    // --- Fallback MediaRecorder API for Backend Whisper Uploads ---
    async function startMediaRecorderRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showToast("Microphone access is not supported by your browser.", "error");
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            state.voice.isRecording = true;
            els.btnRecord.classList.add('recording');
            els.voiceStatusText.textContent = "Recording audio (Whisper Fallback)...";
            els.voiceStatusText.classList.add('recording-text');

            const mediaRecorder = new MediaRecorder(stream);
            state.voice.audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    state.voice.audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                // Compile chunks
                const audioBlob = new Blob(state.voice.audioChunks, { type: 'audio/webm' });
                
                // Stop all tracks on the stream
                stream.getTracks().forEach(track => track.stop());

                // If no key configured, we can't do backend transcribing
                if (!state.apiConfig.apiKey) {
                    showToast("Configure an OpenAI API key in 'AI Config' first to use backend Whisper transcription.", "error");
                    return;
                }

                // Send to backend Whisper API
                const formData = new FormData();
                formData.append('audio', audioBlob, 'recorded_voice.webm');
                formData.append('api_key', state.apiConfig.apiKey);
                formData.append('language', state.inputLanguage);

                showToast("Transcribing voice recording via Whisper...", "info");
                
                try {
                    const res = await fetch('/api/transcribe', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();

                    if (!data.success) {
                        showToast(`Transcription failed: ${data.error}`, "error");
                        return;
                    }

                    if (els.voiceTranscript.value === '') {
                        els.voiceTranscript.value = data.text;
                    } else {
                        els.voiceTranscript.value = els.voiceTranscript.value.trim() + ' ' + data.text;
                    }
                    showToast("Transcription ready!", "success");
                } catch (err) {
                    showToast(`Transcription request failed: ${err.message}`, "error");
                }
            };

            state.voice.mediaRecorder = mediaRecorder;
            mediaRecorder.start();
            
            // Start Visual Canvas Wave
            startAudioWave(stream);

        } catch (err) {
            showToast(`Microphone connection failed: ${err.message}`, "error");
            state.voice.isRecording = false;
            els.btnRecord.classList.remove('recording');
        }
    }

    function stopMediaRecorderRecording() {
        if (state.voice.mediaRecorder && state.voice.mediaRecorder.state !== 'inactive') {
            state.voice.mediaRecorder.stop();
        }
    }

    // --- HTML5 Canvas Audio Wave Visualizer ---
    const ctx = els.waveformCanvas.getContext('2d');
    
    function fitCanvasToContainer() {
        const container = els.waveformCanvas.parentElement;
        els.waveformCanvas.width = container.clientWidth;
        els.waveformCanvas.height = container.clientHeight;
    }

    window.addEventListener('resize', fitCanvasToContainer);
    fitCanvasToContainer();

    async function startAudioWave(existingStream = null) {
        try {
            let stream = existingStream;
            if (!stream) {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            }

            state.voice.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            state.voice.analyser = state.voice.audioContext.createAnalyser();
            state.voice.source = state.voice.audioContext.createMediaStreamSource(stream);
            
            state.voice.source.connect(state.voice.analyser);
            state.voice.analyser.fftSize = 256;
            
            const bufferLength = state.voice.analyser.frequencyBinCount;
            state.voice.dataArray = new Uint8Array(bufferLength);

            drawWave();

        } catch (err) {
            console.warn("Wave visualizer failed to load audio context:", err);
            // Draw static moving wave if microphone fails to bind context
            drawStaticWave();
        }
    }

    function drawWave() {
        if (!state.voice.isRecording) return;
        
        state.voice.animationFrameId = requestAnimationFrame(drawWave);
        state.voice.analyser.getByteFrequencyData(state.voice.dataArray);
        
        ctx.clearRect(0, 0, els.waveformCanvas.width, els.waveformCanvas.height);
        
        const width = els.waveformCanvas.width;
        const height = els.waveformCanvas.height;
        const barWidth = (width / state.voice.dataArray.length) * 1.5;
        let barHeight;
        let x = 0;

        for (let i = 0; i < state.voice.dataArray.length; i++) {
            barHeight = state.voice.dataArray[i] * 0.7;

            // Gradient bar
            const grad = ctx.createLinearGradient(0, height / 2 - barHeight / 2, 0, height / 2 + barHeight / 2);
            grad.addColorStop(0, 'rgba(177, 85, 255, 0.45)');  // Neon Purple
            grad.addColorStop(0.5, 'rgba(0, 242, 254, 0.6)');  // Neon Cyan
            grad.addColorStop(1, 'rgba(177, 85, 255, 0.45)');

            ctx.fillStyle = grad;
            ctx.fillRect(x, height / 2 - barHeight / 2, barWidth - 2, barHeight);

            x += barWidth;
        }
    }

    let staticWavePhase = 0;
    function drawStaticWave() {
        if (!state.voice.isRecording) return;
        
        state.voice.animationFrameId = requestAnimationFrame(drawStaticWave);
        ctx.clearRect(0, 0, els.waveformCanvas.width, els.waveformCanvas.height);

        const width = els.waveformCanvas.width;
        const height = els.waveformCanvas.height;
        
        ctx.beginPath();
        ctx.lineWidth = 3;
        
        const grad = ctx.createLinearGradient(0, 0, width, 0);
        grad.addColorStop(0, '#b155ff');
        grad.addColorStop(0.5, '#00f2fe');
        grad.addColorStop(1, '#b155ff');
        ctx.strokeStyle = grad;

        for (let x = 0; x < width; x++) {
            const y = height / 2 + Math.sin(x * 0.015 + staticWavePhase) * 20 * Math.sin(x * 0.005);
            if (x === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        
        ctx.stroke();
        staticWavePhase += 0.05;
    }

    function stopAudioWave() {
        if (state.voice.animationFrameId) {
            cancelAnimationFrame(state.voice.animationFrameId);
        }
        
        if (state.voice.source) {
            state.voice.source.disconnect();
        }
        
        if (state.voice.audioContext) {
            state.voice.audioContext.close();
        }

        ctx.clearRect(0, 0, els.waveformCanvas.width, els.waveformCanvas.height);
    }

    // --- Sample Queries Clicking ---
    els.btnToggleSamples.addEventListener('click', () => {
        const display = els.sampleQueriesBox.style.display;
        els.sampleQueriesBox.style.display = display === 'block' ? 'none' : 'block';
    });

    document.querySelectorAll('.sample-query-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            els.textQuestion.value = item.textContent;
            els.sampleQueriesBox.style.display = 'none';
            showToast("Sample query loaded into input box.", "info");
        });
    });

    // --- AI Agent Query Submission ---
    async function submitAgentQuery(question) {
        if (!question || question.trim() === '') {
            showToast("Please provide a question first.", "warning");
            return;
        }

        // Validate Key exists
        if (!state.apiConfig.apiKey) {
            showToast("AI API Key is required. Please click 'AI Config' in the top header to enter your API key first.", "error");
            // Highlight config button
            els.btnSettingsToggle.classList.add('btn-primary');
            setTimeout(() => els.btnSettingsToggle.classList.remove('btn-primary'), 1500);
            return;
        }

        // Show thinking panel & hide results panel
        els.thinkingPanel.style.display = 'block';
        els.resultsPanel.style.display = 'none';
        els.agentThinkingLogs.innerHTML = '';
        els.agentCurrentStatus.textContent = "Consulting AI...";

        // Scroll to thinking panel
        els.thinkingPanel.scrollIntoView({ behavior: 'smooth' });

        const payload = {
            question: question.trim(),
            model_name: state.apiConfig.modelName,
            api_key: state.apiConfig.apiKey,
            language: state.inputLanguage,
        };

        // Create virtual loading console lines
        printLogLine("Consulting database schema indices...", "info");

        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (!data.success) {
                // Print failure logs
                if (data.logs) {
                    data.logs.forEach(log => printLogLine(log));
                }
                printLogLine(`Fatal Error: ${data.error}`, "error");
                els.agentCurrentStatus.textContent = "Agent Failed";
                showToast(`Agent failed: ${data.error}`, "error");
                return;
            }

            // Successfully returned results!
            // Typewrite the logs returned from backend to show details
            els.agentCurrentStatus.textContent = "Task Completed";
            
            await typewriteLogs(data.logs);

            // Populate Results Panel
            els.agentNlAnswer.textContent = data.answer;
            els.generatedSqlCode.textContent = data.query;
            els.resultsRecordsCount.textContent = `${data.results ? data.results.length : 0} rows returned`;
            
            // Render SQLite results in beautiful table grid
            renderGrid(data.columns, data.results, els.resultsTableContainer);

            // Display Results
            els.resultsPanel.style.display = 'block';
            showToast("Agent resolved query successfully!", "success");

            // Scroll to results
            els.resultsPanel.scrollIntoView({ behavior: 'smooth' });

        } catch (err) {
            printLogLine(`Network error calling AI Agent: ${err.message}`, "error");
            els.agentCurrentStatus.textContent = "Error";
        }
    }

    // Console logging printing system
    function printLogLine(text, type = 'info') {
        const line = document.createElement('div');
        line.className = `log-line ${type}`;
        line.innerHTML = `<span style="opacity: 0.5;">[${new Date().toLocaleTimeString()}]</span> ${text}`;
        els.agentThinkingLogs.appendChild(line);
        els.agentThinkingLogs.scrollTop = els.agentThinkingLogs.scrollHeight;
    }

    // Simulate real-time typewriting stream of Agent logs for immersion!
    async function typewriteLogs(logLines) {
        els.agentThinkingLogs.innerHTML = '';
        
        for (let i = 0; i < logLines.length; i++) {
            const lineText = logLines[i];
            let type = 'info';
            
            if (lineText.toLowerCase().includes('failed') || lineText.toLowerCase().includes('error')) {
                type = 'error';
            } else if (lineText.toLowerCase().includes('success') || lineText.toLowerCase().includes('succeeded')) {
                type = 'success';
            } else if (lineText.startsWith('Generated SQL:')) {
                type = 'sql-output';
            }

            printLogLine(lineText, type);
            // Zippy 100ms gap between logs to look alive
            await new Promise(r => setTimeout(r, 150));
        }
    }

    // Ask actions
    els.btnAskVoice.addEventListener('click', () => {
        submitAgentQuery(els.voiceTranscript.value);
    });

    els.btnAskText.addEventListener('click', () => {
        submitAgentQuery(els.textQuestion.value);
    });

    // --- Manual SQL Sandbox ---
    els.btnRunManualSql.addEventListener('click', async () => {
        const sql = els.sandboxSqlEditor.value;
        if (!sql || sql.trim() === '') {
            showToast("Type an SQL query first.", "warning");
            return;
        }

        els.sandboxError.style.display = 'none';
        els.sandboxTableContainer.innerHTML = `
            <div class="loading-spinner-container">
                <div class="spinner"></div>
                <span class="loading-text">Executing SQL statement...</span>
            </div>
        `;

        try {
            const res = await fetch('/api/manual_sql', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: sql })
            });
            const data = await res.json();

            if (!data.success) {
                els.sandboxTableContainer.innerHTML = `
                    <div class="table-placeholder">
                        <i class="fa-solid fa-triangle-exclamation placeholder-icon"></i>
                        <span>SQLite compilation failed.</span>
                    </div>
                `;
                els.sandboxError.textContent = data.error;
                els.sandboxError.style.display = 'block';
                showToast("SQL Execution failed.", "error");
                return;
            }

            // Succeeded! Render grid
            renderGrid(data.columns, data.rows, els.sandboxTableContainer);
            showToast("SQL statement completed successfully.", "success");
            
            // Refresh Schema Panel automatically just in case they added custom tables/rows!
            loadSchema();

        } catch (err) {
            els.sandboxTableContainer.innerHTML = `
                <div class="table-placeholder">
                    <i class="fa-solid fa-triangle-exclamation placeholder-icon"></i>
                    <span>Network failure.</span>
                </div>
            `;
            els.sandboxError.textContent = err.message;
            els.sandboxError.style.display = 'block';
        }
    });

    els.btnClearSandbox.addEventListener('click', () => {
        els.sandboxSqlEditor.value = '';
        els.sandboxError.style.display = 'none';
        els.sandboxTableContainer.innerHTML = `
            <div class="table-placeholder">
                <i class="fa-solid fa-terminal placeholder-icon"></i>
                <span>Run an SQL query to see results here</span>
            </div>
        `;
    });

    // Copy SQL Query
    els.btnCopySql.addEventListener('click', () => {
        const code = els.generatedSqlCode.textContent;
        navigator.clipboard.writeText(code).then(() => {
            showToast("SQL copied to clipboard!", "success");
        }).catch(err => {
            showToast("Failed to copy.", "error");
        });
    });

    // Open Generated SQL inside Sandbox Editor
    els.btnSandboxSql.addEventListener('click', () => {
        const code = els.generatedSqlCode.textContent;
        els.sandboxSqlEditor.value = code;
        
        // Go to Sandbox Tab
        els.tabBtns.forEach(btn => {
            if (btn.getAttribute('data-tab') === 'tab-sandbox') {
                btn.click();
            }
        });
        showToast("SQL loaded into Sandbox editor. Hit Run to execute!", "info");
    });

    // --- Browser SpeechSynthesis (Text-to-Speech Aloud) ---
    let synth = window.speechSynthesis;
    let activeUtterance = null;

    els.btnSpeakAnswer.addEventListener('click', () => {
        if (!synth) {
            showToast("Text-to-speech is not supported by your browser.", "warning");
            return;
        }

        // If speaking already, cancel it
        if (synth.speaking) {
            synth.cancel();
            els.btnSpeakAnswer.innerHTML = '<i class="fa-solid fa-volume-high"></i> Speak';
            showToast("Speech cancelled.", "info");
            return;
        }

        const text = els.agentNlAnswer.textContent;
        if (!text || text.trim() === '') return;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = getLanguageConfig().ttsLang;
        const voices = synth.getVoices();
        const preferred = voices.find(v => v.lang === getLanguageConfig().ttsLang)
            || voices.find(v => v.lang && v.lang.startsWith(state.inputLanguage));
        if (preferred) {
            utterance.voice = preferred;
        }
        utterance.onend = () => {
            els.btnSpeakAnswer.innerHTML = '<i class="fa-solid fa-volume-high"></i> Speak';
        };
        utterance.onerror = (e) => {
            console.error("SpeechSynthesis Error:", e);
            els.btnSpeakAnswer.innerHTML = '<i class="fa-solid fa-volume-high"></i> Speak';
        };

        els.btnSpeakAnswer.innerHTML = '<i class="fa-solid fa-circle-stop"></i> Stop';
        activeUtterance = utterance;
        
        // Speak!
        synth.speak(utterance);
        showToast("Reading answer aloud...", "info");
    });

    if (window.speechSynthesis) {
        window.speechSynthesis.onvoiceschanged = () => {};
    }

    // --- App Booting Initialization ---
    loadSavedConfig();
    loadDbInfo();
    loadSchema();
    showToast("AI AGENT neural dashboard online.", "success");
});
