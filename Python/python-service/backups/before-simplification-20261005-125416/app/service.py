import re
from decimal import Decimal
from .extraction import MONEY, extract, read_document
from .models import Analysis, Answer, Citation
from .topics import mentions, unsupported_scope


def conflict(records):
    assertions = {}
    for p in records:
        for topic in mentions(p.text):
            text = p.text.lower()
            values = MONEY.findall(p.text)
            if values:
                for currency, amount in values:
                    assertions.setdefault((topic, "money"), set()).add(
                        (currency.upper(), Decimal(amount.replace(",", "")))
                    )
            elif "manager approval" in text:
                assertions.setdefault((topic, "manager_approval"), set()).add(
                    "not required" if re.search(r"not\s+required", text) else "required"
                )
            else:
                # Differing unparsed terms remain unresolved instead of choosing one.
                assertions.setdefault((topic, "terms"), set()).add(" ".join(text.split()))
    return any(len(values) > 1 for values in assertions.values())


class PolicyService:
    def __init__(self, store, provider):
        self.store, self.provider = store, provider

    def answer(self, context, question):
        topics = mentions(question)
        if not topics:
            return Answer(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])
        records = self.store.retrieve(context, question, topics)
        if not records or unsupported_scope(question, [p.text for p in records]):
            return Answer(status="INSUFFICIENT_EVIDENCE", answer=None, citations=[])
        citations = [Citation(chunk_id=p.id, quote=p.text) for p in records]
        has_conflict = conflict(records)
        expected = Answer(status="CONFLICT" if has_conflict else "ANSWERED",
                          answer=None if has_conflict else " ".join(dict.fromkeys(p.text for p in records)),
                          citations=citations)
        return self.provider.generate(question, records, expected)

    def analyze(self, context, filename, content):
        text = read_document(filename, content)
        extracted, evidence, issues = extract(text)
        policy = self.answer(context, "What policy applies to " + extracted.benefit + "?") if extracted.benefit else None
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
