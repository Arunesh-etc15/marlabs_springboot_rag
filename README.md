# Python policy service with Chroma and Ollama

This service implements policy retrieval, supported answers, and TXT/PDF extraction for the Spring Boot API. Its policy source is `"path"/marlabs_policydata.pdf`, not a policy JSON file. Python reads the PDF for embeddings and evidence; Spring reads that same PDF independently for citation validation. Set POLICY_FILE and CALLERS_FILE explicitly for other layouts.

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
$env:OLLAMA_MODEL = "llama3.2:3b"
$env:OLLAMA_EMBED_MODEL = "nomic-embed-text"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal start Spring Boot:

Use the existing Postman requests against http://localhost:8080. Python's internal endpoints are on port 8000; /docs shows their contracts. /health is a liveness check, not proof that Ollama models are available.

## Configuration Values

- OLLAMA_MODEL: llama3.2:3b; answer generation.
- OLLAMA_EMBED_MODEL: nomic-embed-text; policy and query vectors.
- OLLAMA_BASE_URL: http://localhost:11434.
- OLLAMA_TIMEOUT_SECONDS: 20 seconds per HTTP call; 2-second connection timeout.
- CHROMA_PATH: .chroma under this service.
- POLICY_FILE: ../marlabs_policydata.pdf, relative to the Python service location. Spring defaults to ../../Python/marlabs_policydata.pdf relative to its project directory. Set the same absolute path in both terminals to avoid working-directory ambiguity.
- CALLERS_FILE: the Spring Boot src/main/resources/callers.json file. Caller identity configuration remains JSON; it is not policy evidence.

Both services load this same policy file at startup. Restart both services after changing records so retrieval and citation validation use the same corpus.

The policy PDF must contain numbered records: `1. policy-id`, then `tenant | role | Approved/Draft | YYYY-MM-DD to YYYY-MM-DD`, then policy text. The readers preserve metadata and normalize line/page wrapping to spaces. Malformed records fail startup rather than silently losing access rules. No OCR is provided for the policy source, and policy JSON files are rejected. The PDF-source collection uses a separate fingerprint namespace.

No separate Chroma server is required: PersistentClient stores the index locally. Indexing is lazy on the first supported question. A content fingerprint selects a new collection after policy data or embedding model changes, preventing stale policies from surviving edits.

Spring's default Python read timeout is now 70 seconds, allowing initial indexing, query embedding, and generation. Increasing the Ollama timeout requires increasing PYTHON_READ_TIMEOUT_MS too. Larger models or a cold CPU-only model can exceed the bound and return PROVIDER_TIMEOUT. No automatic retries or fallback calls are configured.

## Start Here

Functions in order:

1. `main.py`: `create_app()` and the `/internal/answer` route.
2. `service.py`: `PolicyService.answer()`.
3. `store.py`: `PolicyStore.retrieve()`.
4. `providers.py`: `embed()` and `generate()`.

These are functions and methods, not separate applications. FastAPI calls the
route function; that function calls the service; the service calls the store and
provider.

## A Question From Start to Finish

Suppose Spring sends a question about certification reimbursement with an Atlas
employee context and an `as_of` date.

1. `main.py` receives the JSON and checks that tenant and role are known.
2. `topics.py` recognizes the certification topic.
3. `store.py` searches only approved policies matching the tenant, role, and date.
4. `service.py` prepares citations and checks for conflicting policy terms.
5. `providers.py` sends the question and evidence to Ollama.
6. Pydantic validates the response structure. Spring separately checks citations.

An unknown topic, no matching policy, or unsupported scope can return
`INSUFFICIENT_EVIDENCE` before Ollama is called.

## Startup Versus Requests

Startup reads settings, caller identities, and the policy PDF, then opens Chroma.
The first policy search creates embeddings if that collection needs indexing.
Later searches reuse the collection and embed each new question.

The PDF is the source of policy records. JSON serialization inside `store.py`
only helps calculate the collection name; it does not create a policy JSON file.

## Uploaded Documents

Spring manages the batch and sends Python one document at a time.
`extraction.py` reads its TXT or text-based PDF content and extracts benefit,
amount, currency, and reference using rules. `service.py` then searches policies
for the recognized benefit and adds human-review warnings. This does not approve
a claim or payment.

## Python Concepts Used Here

- `class`: groups related data and functions. `PolicyStore` groups Chroma work.
- `self`: the current object. `self.provider` is that object's Ollama connection.
- `__init__`: runs when an object is created and saves its dependencies.
- `dict`: named values, such as `{"tenant": "Atlas"}`.
- `list`: ordered values, such as a list of citations.
- `set`: distinct values, useful for detecting different amounts.
- `return`: sends a result back to the caller.
- `raise`: stops the operation with an error.
- `try/except`: handles failures such as a disconnected Ollama service.
- `with`: manages a resource, such as a file or lock, and releases it afterward.
- `@app.post`: tells FastAPI which function handles a POST endpoint.
- `BaseModel`: Pydantic's way to define JSON fields and validate their types.
- `yield` in the lifespan function: separates startup from shutdown cleanup.

## Remaining Files

`config.py` reads environment settings and file paths. `policy_source.py` parses
numbered records from the policy PDF. `models.py` defines data structures.
`errors.py` defines service errors. `logging_config.py` configures `service.log`.
`__init__.py` marks `app` as a Python package.

## Important Limitations

Schema validation does not prove an answer is correct. The exact comparison
between the model response and the expected answer has been removed. Citation
checks remain, but do not prove every statement in the answer text.
Scanned PDFs need OCR, which this implementation does not provide.

## Run Tests

From the `python-service` folder with its virtual environment activated:

```powershell
python -m pytest tests -q
```

Specifying `tests` avoids collecting old test files in the backups folder.


# Git code commit steps
Step 1: Make sure repo is initialized
git init

Step 2: Stage and commit files
git add .
git commit -m "Initial commit"

Step 3: Ensure branch is named main
git branch -M main

Step 4: Push to remote
git push -u origin main
