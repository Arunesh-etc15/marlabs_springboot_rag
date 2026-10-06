# Marlabs Spring Boot Policy API

The public Java API receives policy questions and reimbursement documents,
resolves a simulated caller identity, delegates analysis to Python, and validates
returned policy citations against the same source PDF.

This is a local assessment implementation, not a production approval system.
It does not approve claims, calculate remaining allowance, or issue payments.

## Components

- Java 17, Spring Boot 3.5.14, Maven Wrapper, and Apache PDFBox 3.0.8.
- Spring public API: `http://localhost:8080`.
- Python internal API: `http://127.0.0.1:8000`.
- Ollama: `http://localhost:11434`, using `llama3.2:3b` and `nomic-embed-text`.
- Python maintains the persistent Chroma index; Spring does not connect to Chroma.
- Policy source: `D:/Marlabs_Project/Python/marlabs_policydata.pdf`.

```text
Client -> Spring controller -> caller lookup -> Python HTTP gateway
       -> Python extraction/retrieval + Chroma/Ollama
       -> Spring PDF citation validation -> public JSON response
```

## Start the Services

Install Java 17 and prepare the Python service's virtual environment. The Maven
Wrapper downloads Maven and dependencies when needed; internet access is required
unless they are already cached. The examples below use the current Windows layout.

### 1. Ollama

Ensure Ollama is serving requests and both models are installed:

```powershell
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

If Ollama is not already running, run `ollama serve` in a separate terminal.

### 2. Python

```powershell
cd D:\Marlabs_Project\Python\python-service
$env:POLICY_FILE = "D:\Marlabs_Project\Python\marlabs_policydata.pdf"
$env:CALLERS_FILE = "D:\Marlabs_Project\SpringBoot\spring-api\src\main\resources\callers.json"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Python always uses Ollama; the selectable offline provider has been removed.
`MODEL_MODE` is no longer used. The current Python `/health` endpoint is disabled;
the internal API documentation is available at `http://127.0.0.1:8000/docs`.

### 3. Spring Boot

```powershell
cd D:\Marlabs_Project\SpringBoot\spring-api
$env:POLICY_FILE = "D:\Marlabs_Project\Python\marlabs_policydata.pdf"
$env:PYTHON_BASE_URL = "http://127.0.0.1:8000"
.\mvnw.cmd spring-boot:run
```

Alternatively, build and run the packaged application:

```powershell
.\mvnw.cmd package
java -jar target\policy-api-0.0.1-SNAPSHOT.jar
```

Set `POLICY_FILE` to an absolute path in both service terminals. Spring loads the
PDF at startup, including when running tests. Restart both services after changing
the PDF so retrieval and validation use the same records.

## Configuration

- `PORT`: public API port; default `8080`.
- `PYTHON_BASE_URL`: Python address; default `http://localhost:8000`.
- `PYTHON_CONNECT_TIMEOUT_MS`: default `2000` milliseconds.
- `PYTHON_READ_TIMEOUT_MS`: default `70000` milliseconds.
- `POLICY_FILE`: default `../../Python/marlabs_policydata.pdf`, relative to the
  Spring process working directory. An absolute override is recommended.
- Upload limits: `5 MB` per file and `25 MB` per complete multipart request.
- JSON uses `snake_case`; unknown JSON properties are rejected.

Increase the Spring read timeout if Python legitimately needs longer. A larger
Spring timeout does not increase Python's separate Ollama timeout.

## Caller Identity

Every public request requires `X-Caller-Id`. The registry is
`src/main/resources/callers.json`:

- `atlas-employee-01`: Atlas employee.
- `atlas-contractor-01`: Atlas contractor.
- `boreal-employee-01`: Boreal employee.

Missing or unknown callers return HTTP 401. Tenant and role come from this lookup,
not the public JSON body or uploaded document. This header simulates authenticated
identity; it is not production authentication.

## POST /answer

Content type: `application/json`.

```json
{
  "question": "What is my annual certification reimbursement limit?",
  "as_of": "2026-09-21"
}
```

From the folder containing this README and its bundled `examples`:

```powershell
curl.exe -X POST "http://localhost:8080/answer" `
  -H "X-Caller-Id: atlas-employee-01" `
  -H "Content-Type: application/json" `
  --data-binary "@examples/answer.json"
```

In Postman, select **Body > raw > JSON** and use the body above. Expected response
when both services and models respond successfully:

```json
{
  "status": "ANSWERED",
  "answer": "The annual certification reimbursement limit for employees is INR 25000.",
  "citations": [
    {
      "chunk_id": "atlas-cert-current",
      "quote": "The annual certification reimbursement limit for employees is INR 25000."
    }
  ]
}
```

The three policy outcomes normally return HTTP 200:

- `ANSWERED`: supported answer and source citations.
- `INSUFFICIENT_EVIDENCE`: null answer and no citations.
- `CONFLICT`: null answer and citations identifying conflicting policies.

For Atlas employees, a home-office allowance question on `2026-09-21` produces
`CONFLICT`; a gym-membership policy question produces `INSUFFICIENT_EVIDENCE`.
Certification on `2026-05-31` uses the historical INR 40000 policy.

## POST /batches

Content type: `multipart/form-data`. The endpoint is `/batches`, not `/batch`.
Use exactly one `metadata` part with content type `application/json`, and one or
more repeated parts named `files`. Each file must match one manifest filename.

Example `batch.json`:

```json
{
  "batch_id": "readme-demo-01",
  "as_of": "2026-09-21",
  "documents": [
    { "document_id": "request-01", "filename": "request-01.txt" }
  ]
}
```

Example `request-01.txt`:

```text
Reference: CERT-101
I request certification reimbursement of INR 18000 for a completed cloud certification.
```

```powershell
curl.exe -X POST "http://localhost:8080/batches" `
  -H "X-Caller-Id: atlas-employee-01" `
  -F "metadata=@examples/batch.json;type=application/json" `
  -F "files=@examples/request-01.txt"
```

### Postman Upload

1. Select **POST** `http://localhost:8080/batches`.
2. Add the header `X-Caller-Id: atlas-employee-01`.
3. Select **Body > form-data**.
4. Add `metadata`, choose **File**, and select the bundled `batch.json`.
   Set this part's content type to `application/json`.
5. Add `files`, choose **File**, and select `request-01.txt`.
6. Remove any manually added overall `Content-Type`. Postman generates the
   multipart header and boundary. Do not send this endpoint as a raw JSON body.

When uploading a different document, update the filename inside the actual
metadata file and reselect it. Editing Postman's raw body does not change that file.
For multiple documents, include one manifest entry per file and repeat `files`.
Document IDs and filenames must be unique, with exact case-sensitive matching.

### Batch Results

The sample should produce `total: 1`, `completed: 1`, `failed: 0`, with:

- Benefit `certification`, amount `18000`, currency `INR`, reference `CERT-101`.
- `field_evidence` containing exact document quotes for extracted fields.
- Policy outcome `ANSWERED` and the INR 25000 annual-limit evidence.
- `review_required: true` and `error: null`.

Results follow manifest order and are processed sequentially. Exact byte-for-byte
duplicates receive `duplicate_of` pointing to the earliest earlier document ID,
but are still processed separately. Empty or unsupported files fail individually;
one failed document does not stop the remaining valid items. Missing/ambiguous
fields remain null and can still yield a completed analysis.

A batch can return HTTP 200 with failed items. Inspect `summary.failed` and each
item's `processing_status` and `error`. A completed analysis is not claim approval.

## Policy Source and Validation

The source PDF must contain numbered policy records with an ID line, a metadata
line, and policy text. The metadata format is:

```text
1. atlas-cert-current
Atlas | employee | Approved | 2026-06-01 to 2027-01-01
The annual certification reimbursement limit for employees is INR 25000.
```

Spring uses `PolicyPdfSource` and PDFBox to read these records. PDF line/page
wrapping is normalized to spaces. Invalid records, conflicting duplicate IDs,
unreadable sources, and invalid effective intervals prevent startup. This reader
does not perform OCR. Policy JSON files are not used for validation.

`ResponseValidator` checks citation IDs, exact quotation substrings, tenant, role,
approved status, and dates against the loaded PDF. The effective start is inclusive
and the end is exclusive. Known injection/example text is excluded by rules.
It also checks response structure and consistency between extracted values and
their evidence fields. Spring does not independently re-extract document text.

Python handles topic matching, policy relevance, conflict detection, and extraction
quote verification. It requires generated answers to match the computed expected
outcome. Uploaded reimbursement documents never become authoritative policy data.

## Python HTTP Contract

- `POST /internal/answer`: JSON fields `tenant`, `role`, `as_of`, `question`;
  returns `status`, `answer`, and `citations`.
- `POST /internal/documents/analyze`: multipart text fields `tenant`, `role`,
  `as_of`, `batch_id`, `document_id`, plus a file part named `file`; returns
  `extracted`, `field_evidence`, `policy`, and `issues`.

`HttpPythonGateway` uses Spring `RestClient`. It makes one HTTP call per question
or document with configured connection/read timeouts and no automatic retries.

## Errors and Troubleshooting

Public error responses have the shape `{ "code": "...", "message": "..." }`.

- HTTP 400 `INVALID_REQUEST`: invalid fields/date, manifest mismatch, duplicate
  filenames, or missing/extra multipart parts.
- HTTP 401 `INVALID_CALLER`: missing or unrecognized caller identity.
- HTTP 413 `UPLOAD_TOO_LARGE`: multipart upload limit exceeded.
- HTTP 415 `UNSUPPORTED_MEDIA_TYPE`: wrong request or metadata-part content type.
- HTTP 502 `INVALID_PROVIDER_RESPONSE`: malformed Python JSON or invalid response
  structure, citations, or caller/date evidence.
- HTTP 502 `PROVIDER_ERROR`: Python returned a non-success HTTP response.
- HTTP 503 `PROVIDER_UNAVAILABLE`: Java could not connect to Python.
- HTTP 504 `PROVIDER_TIMEOUT`: the Java-to-Python connection/read timed out.

The current gateway does not preserve Python's detailed error codes. For example,
Python's `INVALID_PROVIDER_RESPONSE` or `MODEL_UNAVAILABLE` can appear publicly as
`PROVIDER_ERROR`. Check Python's logs or call its internal endpoint for details.
An unreadable PDF detected by Python can likewise appear as a failed batch item
with a generic provider error. Spring-detected empty and unsupported uploads use
`EMPTY_FILE` and `UNSUPPORTED_FILE` respectively.

If only one uploaded filename works, check the attached metadata file: it must
list the actual filename. If Postman returns 415, remove leftover raw-body
`Content-Type` headers and let it create the multipart boundary. Hover over file
attachment warnings to check whether Postman can access the selected files.

## Tests

From the Spring project directory:

```powershell
$env:POLICY_FILE = "D:\Marlabs_Project\Python\marlabs_policydata.pdf"
.\mvnw.cmd test
```

Spring tests mock the Python gateway and do not need running Python or Ollama.
The Spring application-context tests still need the configured readable policy
PDF. Tests cover caller scope, date boundaries, response shapes, citation checks,
PDF records, manifests, duplicates, ambiguous fields, failure isolation, multipart
HTTP handling, and gateway errors. The PDF-source implementation previously passed
20 Spring tests; this README update does not change application code.

Unit tests alone do not establish model reliability. Actual LLM calls can fail
strict output validation when question wording changes.

## Logging

Spring currently logs to its console; no Spring log file is configured in
`application.yml`. Batch messages include sanitized batch/document IDs, status,
and error code rather than document contents.

Python writes a separate rotating log file at
`D:/Marlabs_Project/Python/python-service/service.log`. It records request status
and duration, lifecycle events, and errors. It rotates at 5 MB with three backups.

## Main Source Files

- `PolicyController.java`: public routes, input/date checks, caller resolution.
- `CallerRegistry.java`: registered caller identity lookup.
- `BatchService.java`: manifest validation, ordered processing, duplicates,
  per-document failure isolation, and summary construction.
- `HttpPythonGateway.java`: HTTP calls to Python and dependency-error mapping.
- `ResponseValidator.java`: returned fields and policy-citation validation.
- `PolicyPdfSource.java`: source PDF parsing and known non-evidence screening.
- `ApiModels.java`: request/response records.
- `ApiExceptionHandler.java`: safe public HTTP error responses.

## Limitations and AI Assistance

The simulated identity header is not secure authentication. Processing is
synchronous, with no persistent job queue, approval-system integration, malware
scanning, or production access controls. Topic/injection rules are conservative,
and strict model-output matching is sensitive to question wording. Human review
is always required. Production deployment needs a separate security and capacity
review.

AI assisted with requirements interpretation, integration and documentation. 
Development time was not recorded accurately.
