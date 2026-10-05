# Spring Boot public API

This is the first service for the Marlabs assessment. Java 17 is required. The included Maven wrapper downloads Maven on its first run. Spring Boot 3.5.7 is pinned to a version available in the local development cache.

## Run

From this directory:

```powershell
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
```

The public API runs at http://localhost:8080. Set PORT to change it. Tests run without Python, a model provider, or API keys. Runtime requests require the Python service described below; until it is built, valid requests return a dependency error.

On macOS/Linux use ./mvnw instead. An installed Maven can also run the same goals. Framework references: [Spring Boot requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html) and [Spring REST clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html).

Configuration:
- PYTHON_BASE_URL: http://localhost:8000
- PYTHON_CONNECT_TIMEOUT_MS: 2000
- PYTHON_READ_TIMEOUT_MS: 10000
- Upload limit: 5 MB per file, 25 MB per request.

## Caller identity

X-Caller-Id simulates authenticated identity for this exercise. The lookup is in src/main/resources/callers.json. Only atlas-employee-01, atlas-contractor-01, and boreal-employee-01 are accepted. Tenant and role are never read from employee documents or public request bodies. Unknown JSON properties are rejected.

## Public requests

```powershell
curl.exe -X POST http://localhost:8080/answer -H "X-Caller-Id: atlas-employee-01" -H "Content-Type: application/json" --data-binary "@examples/answer.json"
curl.exe -X POST http://localhost:8080/batches -H "X-Caller-Id: atlas-employee-01" -F "metadata=@examples/batch.json;type=application/json" -F "files=@examples/request-01.txt"
```

POST /answer accepts question and as_of. Dates must be valid YYYY-MM-DD dates. Business responses use status ANSWERED, INSUFFICIENT_EVIDENCE, or CONFLICT, an answer string or null, and citations [{chunk_id, quote}].

POST /batches accepts exactly one JSON metadata part and repeated files parts. Metadata contains batch_id, as_of, and documents [{document_id, filename}]. Unique IDs and filenames are required. Each file must match one manifest entry. Results follow manifest order.

Each result contains:
- document_id; processing_status: COMPLETED or FAILED.
- extracted: {benefit, amount, currency, reference}; unresolved values are null. amount is a JSON number.
- field_evidence: a map from supported field names to arrays of source quotes; unsupported fields are omitted.
- policy: the /answer response, or null when benefit is unknown or processing failed.
- review_required: always true; issues: an array of review reasons.
- duplicate_of: the earliest earlier document ID with identical file bytes, or null. Duplicates remain separate results.
- error: {code, message} on failure, otherwise null.

Failed items have extracted and policy null, and field_evidence {}. Summary contains total, completed, and failed. Empty or unsupported files fail individually. Ambiguity is a completed result requiring review. The API never approves or pays claims.

## Python service contract for the next step

POST /internal/answer, application/json:
```json
{"tenant":"Atlas","role":"employee","as_of":"2026-09-21","question":"What is my annual certification reimbursement limit?"}
```
Return the public answer shape.

POST /internal/documents/analyze, multipart/form-data: text parts tenant, role, as_of, batch_id, document_id; one file part named file. Return:
```json
{
  "extracted": {"benefit":"certification","amount":18000,"currency":"INR","reference":"CERT-101"},
  "field_evidence": {
    "benefit":["certification reimbursement"],
    "amount":["INR 18000"],
    "currency":["INR 18000"],
    "reference":["Reference: CERT-101"]
  },
  "policy": {
    "status":"ANSWERED",
    "answer":"The annual certification reimbursement limit is INR 25000.",
    "citations":[{"chunk_id":"atlas-cert-current","quote":"The annual certification reimbursement limit for employees is INR 25000."}]
  },
  "issues":["Claims history is unavailable; remaining balance and payable amount are unknown."]
}
```

Python must filter eligible policies BEFORE generation, assess relevance, detect conflicts, validate extraction quotes against document text, expose missing/ambiguous fields in issues, and make at most one model generation attempt per item/question with no retries. Spring verifies response structure, citation quotations, and caller/date eligibility against its copy of policies.json. Semantic support and extraction accuracy require the Python implementation and are not established by Spring's structural checks.

The prompt-injection example in policies.json is preserved as untrusted source data. Its text is not an application instruction. Eligibility alone does not make it relevant policy evidence.

## Errors

Whole-request errors return {code, message}:
- 400 INVALID_REQUEST: bad input, dates, manifest, or missing/extra parts.
- 401 INVALID_CALLER: missing or unknown caller header.
- 413 UPLOAD_TOO_LARGE; 415 UNSUPPORTED_MEDIA_TYPE.
- 502 INVALID_PROVIDER_RESPONSE: malformed JSON or invalid response structure/citations.
- 502 PROVIDER_ERROR: downstream non-success response.
- 503 PROVIDER_UNAVAILABLE: connection failure.
- 504 PROVIDER_TIMEOUT: connection/read timeout.

Batch items use the same provider error codes plus EMPTY_FILE, UNREADABLE_FILE, and UNSUPPORTED_FILE. The batch returns 200 even if individual items fail. No retries are configured. Logs include batch ID, document ID, status, and error code, without document contents.

## Current verification and limits

Automated tests cover caller context, invalid dates, identity claims, outcome shapes, eligible/verbatim citations, effective date boundaries, manifest failures, duplicates, empty files, ambiguity, failure isolation, actual HTTP timeout, unavailable dependency, and malformed JSON.

The Python service, actual PDF/TXT extraction, model behavior, and full supplied eight-file demonstration are the next implementation step. Tests do not yet establish end-to-end policy relevance or reimbursement extraction correctness. This service is intended for local use with the simulated caller header.
