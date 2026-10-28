# Syllabus-Aligned AI Learning Assistant

Design and Development of a Syllabus-Aligned AI Learning Assistant for Sri Lankan Primary School Students (Grades 1–5).

## Current implementation status

The Phase 1 frontend/backend skeleton is complete. Phase 2 has processed the locally supplied 86 PDFs into manually user-verified OCR pages, lesson-aware chunks, and a multilingual vector index. The user attested to the official status of the PDFs; independent publisher verification and exact source URLs are not recorded. Some titles, editions, lessons, and topics therefore remain `unknown`.

The backend has filtered retrieval and grounded tutor-answer APIs. The frontend provides a multilingual student tutor, browser speech input/output when supported, a textbook-evidence quiz, and a light/dark appearance toggle whose choice is saved in the browser. Parent accounts can create child profiles; parent/teacher access is checked on every student-record request, and quiz attempts and earned badges are stored in Supabase. Teacher access is only granted to accounts and student relationships provisioned after approval; the project does not yet provide an in-app consent/invitation workflow. Supabase migrations and NVIDIA configuration are required before these cloud-backed features can run. They have focused mocked/API and build tests, but have not been exercised against a configured Supabase project or actual device speech services.

## Architecture

```text
React + TypeScript (Vite)
        │ HTTPS / versioned JSON API
        ▼
FastAPI backend ── Supabase Auth / PostgreSQL
        │           application records, relationships, progress
        │
        ├── PDF extraction / OCR / lesson-aware chunking
        ├── multilingual-e5-large embeddings ── ChromaDB
        └── NVIDIA hosted inference API
```

- The browser calls FastAPI; it does not call NVIDIA, another upstream model provider, or ChromaDB directly.
- Supabase Auth is the identity provider and PostgreSQL stores application records. The API verifies bearer tokens with Supabase Auth and checks the student's parent/teacher relationship on every protected record request. PostgreSQL Row Level Security (RLS) is a second boundary. A Supabase service-role key is used only by the backend and must never be sent to the browser.
- The ingestion pipeline will retain grade, subject, medium, textbook, edition, chapter, lesson, topic, and printed page metadata. Extracted page numbers must be distinguished from PDF page indexes.
- Retrieval applies the selected grade, subject, and language filters before sending verified textbook evidence through NVIDIA to the configured model. Supported textbook answers cite their sources. Safe, age-appropriate general-knowledge answers can be provided without textbook citations and are explicitly labeled as not found in the selected textbook; uncertain or unsafe questions are declined.
- ChromaDB is the initial vector store. PostgreSQL remains the system of record for users, relationships, activities, and progress; it is not replaced by the vector index.
- This separation keeps the model and vector store behind the API and allows independently testing authorization, retrieval, and answer grounding.

### Planned implementation phases

1. **Foundation (complete):** architecture, folder structure, dependency manifests, environment templates, and app startup.
2. **Source inventory and ingestion (complete for current local corpus):** 86 books have verified page OCR, subject labels with separate evidence provenance, chunks, and source/page metadata. Official-source status remains user-attested, not independently verified; unresolved metadata remains unknown.
3. **Retrieval and answer generation (implemented, NVIDIA API key and model required):** multilingual-e5-large embeddings, ChromaDB indexing, grade/subject/medium/page-verification filters, validated citations for textbook-grounded answers, clearly labeled general-knowledge answers when safe and appropriate, and abstention handling.
4. **Quality and safety (in progress):** API-level grounding, citation, filter, and abstention tests exist. Curated multilingual retrieval/answer evaluation and human evaluation of generated answers still remain.
5. **Identity and learning product (implementation added; cloud setup pending):** parent sign-up/sign-in, parent-created child profiles, teacher/student access checks, textbook-evidence quizzes, persisted quiz attempts, a progress summary, and database-awarded badges are wired. Apply the Supabase migration and configure credentials before use. Teacher provisioning/parent-approved relationships remain an administrative setup step, not an in-app workflow.
6. **Accessible interaction and integration (implementation added; device validation pending):** browser speech recognition and synthesis are capability-checked and report unavailable language/device support. Responsive UI and basic keyboard/screen-reader support exist; full accessibility and real-device voice validation remain.

Phases may be refined as source verification and testing reveal constraints. No textbook URLs, page references, or lesson metadata should be inferred or invented.

## Folder structure

```text
.
├── data/
│   ├── Grade 01/ ... Grade 05/        # Local source PDFs (not committed)
│   ├── manifests/                     # Inventory CSV is committed
│   └── extracted/ and index/          # Local generated OCR/chunks/index (not committed)
├── backend/
│   ├── app/
│   │   ├── api/                       # Versioned API routes
│   │   ├── core/                      # Settings and shared configuration
│   │   ├── ingestion/                 # Inventory, extraction, cleaning, chunking, export
│   │   ├── rag/                       # Shared multilingual embeddings and grounded answers
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt              # API and Supabase foundation
│   ├── requirements-rag.txt          # Heavier document/AI dependencies
│   └── requirements-dev.txt
├── frontend/
│   ├── src/
│   ├── .env.example
│   └── package.json
├── .env.example
├── supabase/
│   └── migrations/                    # Auth profiles, RLS, student/quiz/progress schema
└── README.md
```

### GitHub and deployment data

The repository intentionally excludes all textbook PDFs and derived page/OCR/chunk/index files under `data/`. The textbooks may be copyrighted, and the local corpus/index is large; do not publish them to GitHub. Only `data/manifests/textbook_inventory.csv` is tracked. Before deploying textbook-grounded answers, provision the authorized source files and a matching verified ChromaDB index through private storage or the deployment platform's protected volume, then set `CHROMA_PERSIST_DIR` to that index. The hosted API also needs its own NVIDIA and (for family features) Supabase environment variables. A GitHub push alone does not deploy the app or provide those services.

The student interface includes grade selection, separate textbook and answer language controls, and subject choices matching current inventory grade/medium labels. Selecting English for textbook language shows every subject currently inventoried for that grade; when the selected subject has no English-medium book, retrieval automatically uses the available subject-specific source language (Tamil is preferred over Sinhala when both exist), while the selected answer language remains unchanged. The actual source textbook page is used for tutor answers, coloring, and quizzes. Subject metadata retains its existing verification provenance; inventory-derived choices are not independent confirmation that a book's subject is correct. The tutor posts the backend's exact request fields and displays only citations returned by the API. The latest eight chat turns are temporary page state and are not saved. The quiz generator uses selected grade, subject, medium, and topic filters; it refuses empty/insufficient evidence, validates returned source chunk IDs and language script, and only sends questions/options to the browser before submission. Score keys and explanations remain server-side until the attempt is submitted. Completed attempts and threshold-based badges are saved to PostgreSQL. The browser voice APIs depend on browser, OS, microphone permission, and installed language voices; this is not a guarantee that every device supports Sinhala or Tamil speech.

### Parent/teacher records and textbook quizzes

1. In Supabase, apply [`supabase/migrations/202606010001_learning_records.sql`](./supabase/migrations/202606010001_learning_records.sql) using the SQL editor or your migration runner. The migration creates the profile trigger, student/teacher relationships, quiz/progress/badge tables, RLS policies, and the progress summary view. If existing accounts were created before the profile trigger was installed, also apply [`supabase/migrations/202610250001_backfill_auth_profiles.sql`](./supabase/migrations/202610250001_backfill_auth_profiles.sql) to add the default parent profile only for accounts that are missing one; existing teacher roles are left unchanged.
2. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` in the root `.env`. Use a backend-only secret/service-role key for the last value; never place it in `frontend/.env` or expose it to the browser. Restart FastAPI after changing settings.
3. Create a parent account in the Family dashboard. If Supabase email confirmation is enabled, verify the email and then sign in. Add child profiles there; only the authenticated parent who created a profile can access it.
4. Teacher accounts are not self-selectable or self-approvable. An administrator must create the teacher's Auth account, change the resulting profile role to `teacher`, obtain parent consent through the school's process, and insert a matching `teacher_student_access` row. The foreign key requires the recorded approving parent to be the student's actual parent. Until this is done, the teacher sees no students.
5. To make a quiz, sign in, select the authorized child, choose a textbook medium and an available subject, then select a verified lesson suggestion or enter a topic. The grade always follows the selected student's saved profile; changing the medium refreshes verified subjects and topic suggestions for that grade. Only verified-page Chroma evidence matching the child's grade, subject, and selected medium can be cited. The current index is locally stored; the backend process must be able to read it. A generated question is model-produced from cited passages, not independently human-reviewed; check generated question quality before classroom use.
6. Progress and badges appear after the saved quiz is submitted. The initial badge criteria are: `first_quiz` after one completion, `careful_thinker` for a score of at least 80%, and `steady_learner` after three completions. PostgreSQL awards these in the same transaction as the attempt.

The browser session token is held in React memory only and is cleared on page reload or sign-out. The current family API stores quiz records and answer keys server-side; it does not save student names beyond the parent-created display name, or save tutor conversations.

## Local textbook inventory and pilot

Generate or refresh the metadata inventory and its summary report for PDFs recursively located below `data\Grade 01`–`data\Grade 05`:

```powershell
python backend\app\ingestion\inventory.py --root data --output data\manifests\textbook_inventory.csv --report data\manifests\inventory_report.json
```

Run this command from the project root. The inventory records source paths relative to `data`, grade and medium only from unambiguous folder names, page counts and PDF document title metadata, text-based/scanned/mixed classification, expected Unicode script presence, and content hashes for duplicate detection. Missing or uncertain subject, title, edition, and folder metadata are `unknown`; verification remains `unverified`. A filename is not treated as evidence of a textbook title. `unicode_mapping_review` marks a selectable text layer that contains no characters from its expected language script; this can indicate legacy font encoding and needs manual review or OCR. Original PDF files are never modified.

`data\manifests\textbook_inventory.csv` is the canonical inventory. The older `data\catalog\textbook_inventory.csv`, if present, is a preliminary filename-only catalog and must not be used for ingestion.

Create a separate, read-only audit report of inventory metadata coverage and local source-file presence:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.inventory_audit
```

The report is written to `data\manifests\textbook_inventory_audit.json`; an existing report is never overwritten. This audit reads the CSV and checks whether each relative local file exists under `data`; it does not modify the manifest, verify official publishers or editions, or reopen/recount PDF pages. Exact source URLs, publishers, and edition/year details remain unknown unless supported by documentary evidence. Subject labels may be based on explicit filename/PDF-title evidence and carry their own provenance; this is not independent source verification. Page-level OCR verification is separate from official-source verification.

If the user personally downloaded and checked that every inventoried book is official, record that as a **user attestation** (not independent verification) after all local PDF paths have passed the existence check:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.inventory_audit --record-user-attestation --output data\manifests\textbook_inventory_audit_user_attested.json
```

This adds per-book user-attestation provenance and download-status fields to the canonical inventory. The exact source URL, publisher evidence, subject, and edition/year remain unknown unless separately provided; OCR verification remains a separate status. Use a new output path or the command will refuse to overwrite an existing audit report.

Generate conservative subject suggestions from explicit English, Sinhala, and Tamil subject terms in PDF filenames and non-unknown PDF metadata titles:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.subject_candidates --output data\manifests\textbook_subject_candidates_multilingual.json
```

Multiple distinct subject clues are marked ambiguous; records without explicit clues remain unknown. Grade and language medium alone are not treated as subjects. Scholarship-exam wording in the relative path is considered only when the PDF name/path also identifies exam papers or marking schemes.

For an explicit, unique title match that the project owner has authorized to apply without individual review, use the separate evidence-assignment mode:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.subject_candidates --apply-evidence-backed-candidates --output data\manifests\textbook_subject_candidates_multilingual.json --replace-report --evidence-assignment-report data\manifests\textbook_subject_evidence_assignment.json
```

This records `filename_evidence_assigned`, not `user_confirmed`, for each changed subject. The assignment log preserves each matched term and source field, and the command refuses stale reports, ambiguous matches, existing conflicting labels, and log overwrites. In this inventory, all 73 previously unknown subjects had one explicit filename/path match; the 13 earlier user-confirmed subjects remain separately marked. The 86 labels are now populated, but this does not independently verify the publisher, source URL, or edition/year. Those details remain unknown where documentary evidence is absent.

After reviewing and explicitly accepting all unambiguous candidates in that report, apply them with:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.subject_candidates --apply-user-confirmed-candidates --replace-report
```

This separate command records per-book user-confirmation provenance and refuses stale candidate data, ambiguous candidates, and pre-existing different subjects. It skips records with no explicit subject clue. Its separate confirmation log is `data\manifests\textbook_subject_confirmation.json`; it refuses to overwrite that log. Language-medium wording such as `Tamil Medium` is not treated as a subject clue; scholarship exam papers are categorized as `Scholarship Examination (multi-subject)`, not as a language subject.

Run the bounded pilot after creating the inventory from the project root:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.pilot
```

This selects one larger usable PDF per available language and adds a scanned PDF if one exists. It writes page-level JSONL and a Unicode/OCR quality report to `data\extracted\pilot\`. PDF page references are 1-based PDF page indexes; these are not assumed to equal printed textbook page numbers. OCR is attempted only for pages without selectable text. Tesseract and its `eng`, `sin`, or `tam` trained data must be installed separately to OCR; the inventory/pilot report explicitly records when the executable is unavailable. Absence of corruption markers is only a heuristic; human review is still needed before trusting the text.

## Dataset pipeline scripts

The repeatable single-document pipeline is available for a selected textbook:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.pipeline --relative-file-path "Grade 01\English\path-to-reviewed-book.pdf" --output data\extracted\full\reviewed-book.chunks.jsonl
```

It extracts page text (optionally `--ocr` for pages without text or with missing expected Sinhala/Tamil script, or `--ocr-all-pages` to retry every page in the selected book), removes repeated edge lines, makes page-preserving chunks, detects simple English/Tamil/Sinhala chapter and lesson headings when present, validates provenance metadata, and writes both page-level JSONL and chunk JSONL. Missing chapter, lesson, subject, or other unsupported metadata remains `unknown`. Each exported chunk carries its textbook ID, relative source file path, and original 1-based PDF page number. Invalid chunks are logged and prevent a success-shaped partial export.

For a full first-pass text/OCR extraction of every PDF in the inventory, run:

```powershell
$env:PYTHONPATH = "backend"
$env:PATH = "$env:ProgramFiles\Tesseract-OCR;$env:PATH"
$env:TESSDATA_PREFIX = "$env:LOCALAPPDATA\Tesseract-OCR\tessdata"
python -m app.ingestion.batch_ocr --all --source-root data --output-dir data\extracted\full_ocr --tesseract-executable "$env:ProgramFiles\Tesseract-OCR\tesseract.exe" --tessdata-dir "$env:LOCALAPPDATA\Tesseract-OCR\tessdata"
```

The batch preflights all inventory paths and the `eng`, `sin`, and `tam` Tesseract models before processing. It extracts selectable text for every page, OCRs pages with no text in any medium, and additionally OCRs Sinhala/Tamil pages whose text layer contains no characters from the expected script. When OCR is attempted on an existing text layer, both the OCR candidate and embedded text are retained. Each book is saved to a separate page-level JSONL with a resumable batch report. Existing outputs are never overwritten; use `--resume` with the same inventory/settings after an interruption. `--limit N` runs a bounded smoke pass instead of `--all`.

This is extraction, **not manual verification**. Every page is marked `verification_status: unverified`; OCR text must be checked against the rendered source before it is trusted for RAG. This command does not generate embeddings, create ChromaDB, or integrate RAG. It processes only PDFs already listed in the inventory and does not verify their official source, subject, or edition.

Create a deterministic risk-priority queue from the completed batch without invoking a model or changing OCR outputs:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.review_queue --batch-dir data\extracted\full_ocr --output-dir data\extracted\review_queue
```

The queue ranks empty/failed pages as P0, retained-text OCR failures or missing Sinhala/Tamil script as P1, and OCR confidence below 70 as heuristic-only P2. P3 pages have no configured deterministic risk signal; they remain unverified, not approved. The output lists P0–P2 pages and writes counts for all pages. A low-risk classification is not proof of correctness. The command refuses to overwrite existing review queue files.

### Phase 2: verified OCR text to lesson-aware chunks

Start with a one-book-per-medium chunking pilot using the already extracted and manually verified page JSONL. This does not reopen PDFs, rerun OCR, or create embeddings:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.batch_chunking --limit-per-medium 1 --output-dir data\extracted\chunk_pilot
```

Review each `*.chunks.jsonl` against its source page records and inspect `chunking_report.json`. The runner refuses unverified pages, mismatched source paths/page sequences, stale verification provenance, or a non-empty output directory. Each chunk retains textbook ID, grade, subject, medium, PDF page number, current user-attested source status, and detected chapter/lesson; unsupported metadata remains `unknown`. PDF page numbers are 1-based PDF indices, not claims about printed page numbers. Repeated edge headers/footers are removed heuristically and still require quality review.

After the pilot passes human review, chunk every book into a new empty output directory:

```powershell
python -m app.ingestion.batch_chunking --all --output-dir data\extracted\full_chunks_v2
```

This prepares text and provenance only. It does not generate embeddings, create ChromaDB, or enable RAG. `data\extracted\full_chunks` is an earlier exploratory run with an over-permissive Sinhala heading detector; do not use that folder as the reviewed corpus. `full_chunks_v2` is the corrected run before subject evidence assignments and is retained as history.

After changing the canonical inventory's subject labels, regenerate the complete corpus to keep chunk metadata aligned with the inventory:

```powershell
python -m app.ingestion.batch_chunking --all --output-dir data\extracted\full_chunks_v3
```

`full_chunks_v3` contains 86 books, 7,244 user-verified OCR pages, and 7,747 chunks with the updated subject labels.

Build the multilingual embedding index from those verified chunks:

```powershell
$env:PYTHONPATH = "backend"
pip install -r backend\requirements-rag.txt
python -m app.ingestion.vector_index --chunks-dir data\extracted\full_chunks_v3 --output-dir data\index\chroma_multilingual_e5_large
```

The completed index is stored at `data\index\chroma_multilingual_e5_large` and contains 7,747 normalized, 1,024-dimension `intfloat/multilingual-e5-large` vectors. The indexer uses the E5 `passage:` prefix and ChromaDB cosine distance. Grade, subject, medium, detected lesson/chapter, source PDF path, and 1-based PDF page number are metadata; unknown values are not fabricated. The model download is cached locally. Keep the generated index local; `data\index\` is git-ignored.

### Ask a textbook-grounded question

Create or select an NVIDIA API Catalog model at [build.nvidia.com](https://build.nvidia.com/) and obtain an API key from your NVIDIA account. Copy the model ID exactly as shown by the selected model's API page. For the current local setup, the root `.env` uses `NVIDIA_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b`. Configure `NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1` and `NVIDIA_API_KEY` there as well; keep the key out of frontend configuration and never commit `.env`. Restart FastAPI after changing `.env`. The `/api/v1/learning/ask` endpoint filters by grade, subject, medium, and verified-page status, retrieves up to five passages, and sends them through NVIDIA for a grade-appropriate answer in the selected response language. When the retrieved textbook evidence supports the answer, the tutor cites its source pages. When it does not, the tutor may answer safe, age-appropriate general-knowledge questions if it is confident, and clearly says the information was not found in the selected textbook; it abstains for uncertain or unsafe questions. The tutor is prompted to teach patiently with simple steps, short imaginary everyday stories or analogies clearly distinguished from textbook facts, a recap, and a gentle check-for-understanding question. It must use only the selected language/script, including when source evidence is in a different language; mixed-script answers receive one correction attempt and are rejected with a localized message if still mixed. Generation uses NVIDIA's streamed chat-completions API internally, disables reasoning output, and asks for the required `answer`, `cited_chunk_ids`, and `abstained` JSON fields before validating citations against retrieved evidence. The endpoint returns `503` until NVIDIA credentials/model or the index is available. NVIDIA API availability, rate limits, and any trial/usage charges depend on the account and selected model; check current terms in NVIDIA API Catalog.

Under each grounded tutor answer, students can translate it into either of the other supported languages, request a fuller explanation, or get a shorter version. The `/api/v1/learning/transform-answer` endpoint preserves the answer's original grade, subject, textbook medium, and answer language. Translation is a direct, lower-temperature language conversion and does not depend on a second textbook search; fuller explanations use retrieved verified textbook passages and are unavailable when there is no supporting evidence.

If the tutor reports upstream HTTP `401`, verify that `NVIDIA_API_KEY` is a current NVIDIA API Catalog key. Upstream HTTP `403` means NVIDIA denied inference access for the request; confirm access and any required terms for the selected model in its API Catalog page, then use that page's exact model ID. A successful `/v1/models` request alone does not confirm chat-inference access.

```powershell
$body = @{
    question = "What does the textbook say about plants?"
    grade = 3
    subject = "Environmental Studies"
    medium = "English"
    answer_language = "English"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8001/api/v1/learning/ask -ContentType "application/json" -Body $body
```

The citation page is the PDF page index, not necessarily the printed page number. Official-source state in these references is a user attestation, not independent verification. Child safety instructions and model safety settings are initial safeguards, not a completed or independently evaluated child-safety system.

### Evaluate multilingual retrieval

The checked-in starter benchmark contains one source-backed case per language, with expected chunk IDs linked to user-verified OCR pages. Run it from the project root after building the local index:

```powershell
$env:PYTHONPATH = "backend"
python backend\scripts\evaluate_retrieval.py --top-k 5
```

The command reports each expected passage's rank and recall@k, returning a non-zero exit code if any expected passage is missing from the top-k results. This small set is a smoke benchmark, not a statistically representative evaluation or a measure of answer quality; expand and review it with questions across grades, subjects, lessons, and abstention cases.

OCR triage/evidence records below describe the earlier review process. The existing full corpus has already been manually attested by the user; running these commands again is not required to use the current chunks/index.

After inspecting the queue, run local Ollama vision triage on the highest-risk P0/P1 pages (P0/P1 are the default):

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.ollama_review --priority P0 --priority P1
```

The review runner checks that the selected local Ollama model has vision capability, compares each original rendered PDF page with its saved OCR text, and writes resumable results separately under `data\extracted\reviews\ollama_high_risk_round1_20261019\`. A failure is recorded as `request_failed` and causes a non-zero exit; `--resume` retries failed pages and skips completed ones. Successful results remain `ai_review_only` with `human_verified: false`; quote matching only checks whether a model-provided quote occurs in the OCR text, not whether either is correct. An empty concern list is not approval. This local model triage is not a substitute for manual verification and does not build embeddings, ChromaDB, or RAG.

After a person has compared the pages with the original PDFs, record an explicit manual-verification attestation using the exact page count they confirm:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.manual_verification --confirmed-page-count 7244
```

This updates each extracted page and any existing review-queue row to `verification_status: verified`, with `human_verified: true` and provenance that attributes the attestation to the user. It refuses a page-count mismatch and requires a complete OCR batch. The user must only run it after personally reviewing every page in scope; it records the user's confirmation and is not an independent audit by this project. Ollama result files remain historical AI-triage records and are not rewritten.

For a separate, fixed four-PDF text/image pilot (English and Tamil Grade 5, Sinhala Grade 5, and a scanned Sinhala Grade 2 PDF), run:

```powershell
$env:PYTHONPATH = "backend"
python -m app.ingestion.multimodal_pilot --output-dir data\extracted\pilot_multimodal_review
```

The command refuses to overwrite an existing output directory. It extracts selectable page text, embedded PDF images plus an image-to-page CSV manifest, selected page renderings, heuristic table candidates, and OCR status records. `find_tables()` results, nearby page text, and images require human review; no image interpretation or captions are inferred. It is a small bounded pilot, not a corpus-processing command.

### Local OCR setup

On this Windows development machine, Tesseract 5.4.0 is installed with `eng` from the verified Winget package. `sin` and `tam` language data are stored per-user under `%LOCALAPPDATA%\Tesseract-OCR\tessdata`; `TESSDATA_PREFIX` and the executable directory are added to the current user's environment. The two downloaded model files are from the official `tesseract-ocr/tessdata_best` repository and were verified against its Git blob hashes before use. Reopen PowerShell terminals after installation so the updated user environment is inherited.

OCR still needs human quality review: text recognition can return plausible but incorrect characters or numbers. The pilot records per-page OCR confidence, language-script presence, empty OCR results, and original selectable text where OCR was retried. OCR is used on image-only pages and on all pages of Sinhala/Tamil PDFs flagged for legacy-font mapping; the non-OCR embedded layer is retained separately for comparison.

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer and npm
- Tesseract OCR will be required in a later ingestion phase for scanned pages. It is not needed to run this starter application.
- Supabase and NVIDIA credentials are not needed to run the health endpoint.

## Local setup (Windows PowerShell)

From the project root:

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install -r backend\requirements-dev.txt
```

Run the backend in one terminal:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload --port 8001
```

Run the frontend in another terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`).
To test on a phone:

1. Connect the phone and development computer to the same Wi-Fi network.
2. Restart Vite after changing its host setting: stop the existing server with `Ctrl+C`, then run `npm run dev` from the `frontend` folder.
3. On Windows, run `ipconfig` and find the computer's IPv4 address under the active Wi-Fi adapter.
4. Open `http://<computer-wi-fi-ip>:5173` on the phone (for example, `http://192.168.43.53:5173`).
5. If Windows Firewall asks, allow Node.js on private networks. Do not expose the development server on a public network.

The Vite development server listens on the network and proxies `/api` requests to the backend at `http://127.0.0.1:8001`. The backend can remain bound to loopback; the phone sends API requests through Vite rather than using the phone's own `localhost`.

Install the document/RAG dependencies if they are not already installed:

```powershell
pip install -r backend\requirements-rag.txt
```

Do not add API keys to frontend environment variables. Configure real backend credentials only in the local root `.env` file (excluded from version control) or in the deployment secret manager. `.env.example` contains names and non-secret placeholders only.

## Environment variables

See [`.env.example`](./.env.example) and [`frontend/.env.example`](./frontend/.env.example). The learning-answer route needs `NVIDIA_API_KEY` and the exact `NVIDIA_MODEL` on the backend. These are not needed for OCR preparation or local vector indexing. Textbook passages are sent to NVIDIA's hosted API for generation; do not include student personal information in questions.

## Textbook coloring activity

The **Colour** page is available from its own navigation item, separate from **Activities** (practice quizzes). It lists pages matching the selected grade, subject, and textbook language only when the activity page and its preceding reference page have a recorded human-verification attestation. The API renders both pages from the listed local source PDF; it does not generate substitute artwork. For example, the currently verified Grade 1 English activity uses PDF pages 2–3 of `ABOE Activity Book.pdf`.

Students can choose a verified textbook picture, a blank drawing page, or a ruled notebook page with a red margin for writing and drawing. **Fill** colours a closed outlined region; **Draw** supports finger, stylus, or mouse; **Eraser** removes freehand marks. Undo removes the last fill, stroke, or erase action; reset clears marks while preserving the selected blank or ruled page, and the textbook's coloured reference can be revealed or hidden. Fill uses connected light pixels on the browser canvas; it is not AI image recognition and does not judge whether a chosen colour is correct. Open outlines and large/unbounded areas are rejected by Fill, while freehand strokes are not restricted to outlines. Blank, ruled, and textbook colouring are temporary in the browser and are not saved as student progress.

## Tests and checks

From the project root:

```powershell
python -m pytest backend\tests
python -m pytest backend\tests\test_coloring.py
```

Frontend production build:

```powershell
Set-Location frontend
npm run build
```

## Data handling and source verification

Do not download books in bulk or treat filenames as proof of official status. Before indexing any supplied or newly sourced PDF, Phase 2 must record its source URL or origin, edition/year where verifiable, grade, subject, medium, local file path, download status, and verification status in a maintained inventory. Missing or unverified fields must remain explicitly unknown. Keep source PDFs unchanged; generated OCR text, chunks, and indexes belong in ignored generated-data directories, not beside the source files.


$env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8001

Set-Location frontend
npm run dev