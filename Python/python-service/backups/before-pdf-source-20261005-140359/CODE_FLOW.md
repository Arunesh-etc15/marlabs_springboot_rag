# Reading the Python Service

Start with the application files in this order. Tests and the demo script are
supporting tools, not part of the request-processing path.

## 1. config.py: settings and paths

`Settings.from_env()` chooses model names, timeout, and file locations.
Your folder layout defaults to `D:/Marlabs_Project/SpringBoot/policies.json`.
`POLICY_FILE` can override that path. The generation model is `llama3.2:3b`;
the embedding model is `nomic-embed-text`.

## 2. main.py: startup and HTTP routes

`create_app()` loads the caller registry. At startup, `lifespan()` creates
the provider, reads policies with `load_policies()`, and creates the store
and business service. At shutdown, it closes the provider's HTTP client.

`/internal/answer` validates the caller context and delegates to
`PolicyService.answer()`. `/internal/documents/analyze` reads the uploaded
file and delegates to `PolicyService.analyze()`.

## 3. models.py and errors.py: data and errors

Pydantic models define the request/response fields and reject unexpected fields.
`ServiceError` carries a safe error code, message, and HTTP status. The route
error handler turns it into JSON. A timeout is not a policy outcome.

## 4. store.py: source JSON and Chroma

`load_policies()` reads JSON, validates policy records, rejects inconsistent
duplicate IDs, and sorts records by ID.

`_ensure_index()` lazily embeds the source policy text and upserts IDs, text,
vectors, and metadata into Chroma. Existing complete indexes are reused.
The collection name depends on source contents and embedding-model identity;
changing either creates a different collection without deleting the old one.

`retrieve()` filters tenant, role, approval state, effective date, and evidence
flag before querying. It retrieves all eligible records so vector ranking does
not hide a conflict. It then checks the returned records and recognized topics.
Dates include `effective_from` and exclude `effective_to`.

## 5. topics.py and service.py: policy decisions

`mentions()` recognizes the assessment's known benefit aliases.
`unsupported_scope()` rejects questions the evidence cannot support.
These are rule-based checks, not unrestricted natural-language understanding.

`answer()` finds topics, retrieves policies, checks unsupported scopes, builds
exact citations, and checks conflicts. It returns insufficient evidence without
calling the generation model when evidence is missing or the scope is unsupported.
Otherwise, it asks the provider to reproduce the computed answer or conflict.

## 6. providers.py: Ollama calls

`embed()` calls `/api/embed` and validates the numeric vectors.
`generate()` calls `/api/chat`, validates the JSON schema, and requires the result
to equal the expected outcome. The LLM does not freely choose policy terms.
`OfflineProvider` is a deterministic test double, not a production LLM.

## 7. extraction.py: uploaded documents

`read_document()` reads UTF-8 TXT or text-based PDF. It does not perform OCR.
`extract()` handles benefit, amount, currency, and reference in separate steps.
Missing/ambiguous values stay null. `matching_quotes()` keeps exact source quotes.

`analyze()` uses those fields, calls the same policy-answer flow for a recognized
benefit, and adds human-review issues. Documents are not indexed as policy evidence.
The service never approves a claim or computes a payable amount.

## Public request path

Postman -> Spring Boot -> Python route -> PolicyService -> Chroma/Ollama
-> Python response -> Spring citation validation -> Postman.

Spring Boot still owns public caller resolution, batch ordering, duplicate
detection, per-document failure isolation, and the final public response.
