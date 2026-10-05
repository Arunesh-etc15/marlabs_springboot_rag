
Deployment: I would use Azure Container Apps for stateless Spring Boot APIs and Python workers, Service Bus for asynchronous processing, PostgreSQL for job state, and encrypted Blob Storage for documents, in an approved region. Ollama would run on a private VM, with GPU capacity justified by benchmarks. I would replace replica-local Chroma storage with centrally managed vector service.

First changes: Long-running submissions would return HTTP 202 with a job ID and an authenticated status endpoint. Workers would use bounded concurrency and queue backpressure.  A timeout from the approval system would mean “outcome unknown,” not “approval failed”; I would not blindly retry an action that might already have succeeded. 

Security risks: Replace spoofable caller headers with validated identity tokens and server-side authorization. Enforce tenant isolation on documents, jobs, vectors, and results. Keep internal services private, use TLS, managed secrets, least-privilege access, upload validation, and malware scanning. Minimize personal information sent to the model, define retention/deletion rules, and exclude sensitive payloads from logs. Prompt injection and accidental cross-tenant disclosure remain major risks.

Operational risks: Monitor queue age, processing latency, model failures, approval ambiguity, and duplicate actions. Add redacted correlation IDs, audit trails, health checks, alerts, tested backups, and rollback procedures. Benchmark question variations and preserve evidence validation rather than weakening it to suppress model errors.

