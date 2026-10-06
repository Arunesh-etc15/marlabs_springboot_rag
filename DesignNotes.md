## Decision Note

Design choice: Policy access filtering and outcome decisions are handled by application code, rather than delegated to the LLM. Policies are read from the source PDF and indexed in Chroma with tenant, role, approval status, and effective dates. Python checks model output against the evidence-backed expected result; Spring independently validates citations against the PDF.

Alternative rejected: Allowing the LLM to freely interpret retrieved text and determine eligibility or payment approval. This could introduce unsupported facts, resolve conflicts without justified precedence.

Main limitation: Topic matching, extraction, and conflict detection use conservative rules. when question wording changes it may response properly. The implementation cannot establish payment eligibility or remaining annual balance without additional evidence.

Time spent: Not recorded accurately ,but it takes roughly 3 hrs.

Unfinished work: Logging and monitoring are not implemented in all the python files .

AI assistance: AI assisted with requirements interpretation, Python implementation, PDF-source integration and documentation.