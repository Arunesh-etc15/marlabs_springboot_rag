# Python policy service with Chroma and Ollama

This service implements policy retrieval, supported answers, and TXT/PDF extraction for the Spring Boot API. Its policy source is `D:/Marlabs_Project/Python/marlabs_policydata.pdf`, not a policy JSON file. Python reads the PDF for embeddings and evidence; Spring reads that same PDF independently for citation validation. Set POLICY_FILE and CALLERS_FILE explicitly for other layouts.

Virtual environments cannot be moved with the source. Create a fresh .venv at the new location. Prefer .\.venv\Scripts\python.exe -m uvicorn to ensure the active interpreter matches the project.

## Setup on Windows

Python 3.12 and Java 17 are used for the verified local build.

```powershell
cd D:\Marlabs_Project\Python\python-service
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

An isolated environment is already prepared on this machine. To start with Ollama, install [Ollama for Windows](https://ollama.com/download/windows), then download both models:

requirements.lock.txt records the complete dependency versions used in verification; install it instead of requirements.txt to reproduce that environment.

```powershell
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

Keep Ollama running at http://localhost:11434. If the desktop application is not serving it, run ollama serve in a separate terminal.

Start Python:

```powershell
$env:POLICY_FILE = "D:\Marlabs_Project\Python\marlabs_policydata.pdf"
$env:OLLAMA_MODEL = "llama3.2:3b"
$env:OLLAMA_EMBED_MODEL = "nomic-embed-text"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal start Spring Boot:

Use the existing Postman requests against http://localhost:8080. Python's internal endpoints are on port 8000; /docs shows their contracts. /health is a liveness check, not proof that Ollama models are available.

## Provider

The application always uses Ollama. OfflineProvider and the MODEL_MODE setting
have been removed. Old MODEL_MODE environment variables are ignored. Unit tests
use test-only mocks; these are not available as a running-service mode or fallback.
Ollama must be running with both configured models installed for supported answers.

## Logging

At startup the application writes `service.log` directly in the python-service
root folder, independent of the terminal's working directory. It rotates at
5 MB and keeps three backups: service.log.1, service.log.2, and service.log.3.
The file includes startup/shutdown, model names, policy loading, HTTP status and
duration, document processing IDs, safe service error codes, and unexpected-error
tracebacks. It does not deliberately log questions, document contents, or HTTP
request/response bodies. Existing Uvicorn console output is preserved.
Logs and their backups are ignored by Git. Restart Python to enable file logging.

## Configuration Values

- OLLAMA_MODEL: llama3.2:3b; answer generation.
- OLLAMA_EMBED_MODEL: nomic-embed-text; policy and query vectors.
- OLLAMA_BASE_URL: http://localhost:11434.
- OLLAMA_TIMEOUT_SECONDS: 20 seconds per HTTP call; 2-second connection timeout.
- CHROMA_PATH: .chroma under this service.
- POLICY_FILE: ../marlabs_policydata.pdf, relative to the Python service location. Spring defaults to ../../Python/marlabs_policydata.pdf relative to its project directory. Set the same absolute path in both terminals to avoid working-directory ambiguity.
- CALLERS_FILE: the Spring Boot src/main/resources/callers.json file. Caller identity configuration remains JSON; it is not policy evidence.

Both services load this same policy file at startup. Restart both services after changing records so retrieval and citation validation use the same corpus.

The policy PDF must contain numbered records: `1. policy-id`, then `tenant | role | Approved/Draft | YYYY-MM-DD to YYYY-MM-DD`, then policy text. The readers preserve metadata and normalize line/page wrapping to spaces. Malformed records fail startup rather than silently losing access rules. No OCR is provided for the policy source, and policy JSON files are rejected. The PDF-source collection uses a separate fingerprint namespace; older JSON-source collections are left untouched and are not queried.

No separate Chroma server is required: PersistentClient stores the index locally. Indexing is lazy on the first supported question. A content fingerprint selects a new collection after policy data or embedding model changes, preventing stale policies from surviving edits. Old collections remain on disk and can be removed later. Reordering/identical duplicate records do not affect outcomes.

Spring's default Python read timeout is now 70 seconds, allowing initial indexing, query embedding, and generation. Increasing the Ollama timeout requires increasing PYTHON_READ_TIMEOUT_MS too. Larger models or a cold CPU-only model can exceed the bound and return PROVIDER_TIMEOUT. Each question/item makes at most one chat-generation call; no automatic retries or fallback calls are configured.

## Evidence and extraction

Policy records retain their IDs, tenant/role, approval state, dates, and text. Chroma metadata filters enforce tenant, role, Approved state, and inclusive-start/exclusive-end dates before retrieval results reach generation. Prompt-injection/example passages are excluded as evidence. Python rechecks retrieved metadata and only passes relevant approved quotations to Ollama.

All eligible matching passages are considered, so similarity ranking cannot discard the second conflicting allowance. Outcome decisions are deterministic; Ollama produces a schema-constrained extractive response that must exactly match authorized quotes and the required outcome. Unsupported or altered output is a technical failure, not insufficient evidence.

The application handles certification, home-office, training, travel, and wellness vocabulary. Policy values and IDs are read from the PDF, never selected by hardcoded record IDs. Date and role changes apply through metadata. Differing monetary terms or manager-approval assertions produce CONFLICT; differing unparsed terms are conservatively treated as unresolved.

Reimbursement documents are never inserted into the policy vector store. UTF-8 TXT and text-based PDFs are read locally, with a 5 MB, 20-page PDF, and 100,000-character text bound. No OCR is performed. Extraction finds benefit, currency-prefixed amounts, references, and exact source quotations. Conflicting amounts/references and multiple benefits remain null. Manager approval and claims-history limitations are shown in issues; neither service approves claims.

## Internal endpoints

POST /internal/answer: JSON {tenant, role, as_of, question}. Return {status, answer, citations}.

POST /internal/documents/analyze: multipart text fields tenant, role, as_of, batch_id, document_id and a file part named file. Return {extracted, field_evidence, policy, issues} as documented in Spring's README. Known tenant/role pairs must come from Spring caller lookup. Run this internal service on loopback; it does not implement production authentication.

Python technical failures use safe {code, message} responses: PROVIDER_TIMEOUT (504), PROVIDER_UNAVAILABLE or MODEL_UNAVAILABLE (503), INVALID_PROVIDER_RESPONSE or RETRIEVAL_ERROR or PROVIDER_ERROR (502), and EMPTY_FILE/UNREADABLE_FILE/UNSUPPORTED_FILE (422). Spring maps downstream failures and isolates individual batch failures.

## Tests and reproducible demonstration

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

From the Spring directory run .\mvnw.cmd package, then from the Python directory:

```powershell
.\.venv\Scripts\python.exe scripts/demo.py
```

The script requires running Ollama with the configured models. It starts both services on temporary free ports, sends public /answer and the supplied eight-document batch, checks seven completed results and one empty-file failure, and exercises an unreadable PDF alongside a valid item. It saves representative public JSON in demo-responses and stops its temporary services. Model failures remain visible as errors; there is no fallback provider. Sample documents and metadata are in tests/fixtures/pdf-batch.

Tests use real Chroma without model downloads and HTTPX Ollama protocol doubles. They cover access/date boundaries, conflicting/missing policies, source quotations, PDF/TXT extraction, ambiguous fields, record mutation/reordering/duplicates, prompt injection, and provider failures/no retries. The public demonstration verifies exact file duplicates, order, all eight documents, and failure isolation.

## Design limits and verification scope

The consequential choice is deterministic evidence selection and conflict detection with extractive Ollama output, instead of letting an LLM decide access, invent policy precedence, or freely paraphrase amounts. This narrows answer generation but makes quotations and failures auditable.

Vocabulary and conflict interpretation are deliberately conservative. Unrecognized benefits, unusual document formats, complex exceptions, and nuanced policy prose need additional parsing and tests. The regex examples are not a general document-understanding engine; the rules cannot establish policy eligibility or remaining allowance from absent claims history.

The tests use real Chroma with test-only provider mocks and controlled HTTPX Ollama doubles. Real llama3.2:3b/nomic-embed-text inference has also been checked locally. Removing the runnable offline demonstration is a departure from the original assessment's offline-double requirement. This implementation was created with AI assistance.

References: [Chroma metadata filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering), [Ollama embeddings](https://docs.ollama.com/api/embed), and [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).


# Git code commit steps
# Step 1: Make sure repo is initialized
git init

# Step 2: Stage and commit files
git add .
git commit -m "Initial commit"

# Step 3: Ensure branch is named main
git branch -M main

# Step 4: Push to remote
git push -u origin main
