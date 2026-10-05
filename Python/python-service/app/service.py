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
                    assertions.setdefault(key, set()).add(value)
            elif "manager approval" in text:
                key = (topic, "manager_approval")
                if re.search(r"not\s+required", text):
                    value = "not required"
                else:
                    value = "required"
                assertions.setdefault(key, set()).add(value)
            else:
                # Differing unparsed terms remain unresolved instead of choosing one.
                assertions.setdefault((topic, "terms"), set()).add(" ".join(text.split()))
    for values in assertions.values():
        if len(values) > 1:
            return True
    return False


class PolicyService:
    def __init__(self, store, provider):
        self.store = store
        self.provider = provider

    def answer(self, context, question):
        """Retrieve evidence, decide the outcome, and verify the model response."""
        topics = mentions(question)
        if not topics:
            return Answer(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])
        records = self.store.retrieve(context, question, topics)
        if not records or unsupported_scope(question, [p.text for p in records]):
            return Answer(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])
        citations = []
        unique_texts = []
        for policy in records:
            citations.append(Citation(chunk_id=policy.id, quote=policy.text))
            if policy.text not in unique_texts:
                unique_texts.append(policy.text)

        if conflict(records):
            expected = Answer(status="CONFLICT", answer=None, citations=citations)
        else:
            expected = Answer(
                status="ANSWERED",
                answer=" ".join(unique_texts),
                citations=citations,
            )

        # Ollama must reproduce this evidence-backed outcome, not invent a decision.
        return self.provider.generate(question, records, expected)

    def analyze(self, context, filename, content):
        """Extract document fields, then reuse answer() for its recognized benefit."""
        text = read_document(filename, content)
        extracted, evidence, issues = extract(text)
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
                if any("annual" in c.quote.lower() for c in policy.citations):
                    issues.append("Claims history is unavailable; an annual limit does not establish remaining balance.")
        issues.append("Human review is required; no claim has been approved.")
        return Analysis(extracted=extracted, field_evidence=evidence, policy=policy, issues=issues)
