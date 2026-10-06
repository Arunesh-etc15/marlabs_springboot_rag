"""Business flow for answering questions and analyzing documents."""

import re
from decimal import Decimal
from .extraction import MONEY, extract, read_document
from .models import Analysis, Answer, Citation
from .topics import mentions, unsupported_scope


def conflict(records):
    """Detect differing money values, approval rules, or unresolved policy terms."""
    assertions = {}
    for policy in records:
        for topic in mentions(policy.text):
            text = policy.text.lower()
            values = MONEY.findall(policy.text)
            if values:
                for currency, amount in values:
                    key = (topic, "money")
                    value = (currency.upper(), Decimal(amount.replace(",", "")))
                    if key not in assertions:
                        assertions[key] = set()
                    assertions[key].add(value)
            elif "manager approval" in text:
                key = (topic, "manager_approval")
                if re.search(r"not\s+required", text):
                    value = "not required"
                else:
                    value = "required"
                if key not in assertions:
                    assertions[key] = set()
                assertions[key].add(value)
            else:
                # Differing unparsed terms remain unresolved instead of choosing one.
                key = (topic, "terms")
                value = " ".join(text.split())
                if key not in assertions:
                    assertions[key] = set()
                assertions[key].add(value)
    for values in assertions.values():
        if len(values) > 1:
            return True
    return False


class PolicyService:
    def __init__(self, store, provider):
        self.store = store
        self.provider = provider

    def answer(self, context, question):
        """Find policies, prepare an outcome, and ask Ollama for a structured answer."""
        # 1. Recognize which benefit the question is about.
        topics = mentions(question)
        if not topics:
            return Answer(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])
        # 2. Search for approved policies for this caller and date.
        records = self.store.retrieve(context, question, topics)
        if not records:
            return Answer(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])
        policy_texts = []
        for policy in records:
            policy_texts.append(policy.text)
        # 3. Do not answer questions the policy text cannot support.
        if unsupported_scope(question, policy_texts):
            return Answer(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])
        # 4. Keep the source ID and quotation for every policy.
        citations = []
        unique_texts = []
        for policy in records:
            citations.append(Citation(chunk_id=policy.id, quote=policy.text))
            if policy.text not in unique_texts:
                unique_texts.append(policy.text)

        # 5. Prepare the evidence-backed outcome for the model prompt.
        if conflict(records):
            expected = Answer(status="CONFLICT", answer=None, citations=citations)
        else:
            expected = Answer(
                status="ANSWERED",
                answer=" ".join(unique_texts),
                citations=citations,
            )

        # 6. Ask Ollama. The expected outcome is guidance, not an equality check.
        return self.provider.generate(question, records, expected)

    def analyze(self, context, filename, content):
        """Extract document fields, then reuse answer() for its recognized benefit."""
        # First read the uploaded file, then extract fields with rules.
        document_text = read_document(filename, content)
        extracted, evidence, issues = extract(document_text)
        policy = None
        if extracted.benefit:
            question = "What policy applies to " + extracted.benefit + "?"
            policy = self.answer(context, question)
        if policy:
            if policy.status == "CONFLICT":
                issues.append("Applicable policies conflict; a human must resolve the disagreement.")
            elif policy.status == "INSUFFICIENT_EVIDENCE":
                issues.append("There is insufficient approved policy evidence for this benefit.")
            if policy.status != "INSUFFICIENT_EVIDENCE":
                issues.append("Policy terms do not establish expense eligibility or a payable amount.")
                has_annual_limit = False
                for citation in policy.citations:
                    if "annual" in citation.quote.lower():
                        has_annual_limit = True
                        break
                if has_annual_limit:
                    issues.append("Claims history is unavailable; an annual limit does not establish remaining balance.")
        issues.append("Human review is required; no claim has been approved.")
        return Analysis(extracted=extracted, field_evidence=evidence, policy=policy, issues=issues)
