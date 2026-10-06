"""Recognize the assessment's benefit topics and unsupported question scopes."""

import re

ALIASES = {
    "certification": ("certification reimbursement", "certification", "certifications"),
    "home-office": ("home-office allowance", "home-office", "home office", "desk and chair"),
    "training": ("external training", "training"),
    "travel": ("rail travel", "rail", "travel", "train fare"),
    "wellness": ("gym membership", "wellness", "gym"),
}
INJECTION = re.compile(
    r"system\s+message|ignore\s+(?:all\s+)?(?:prior\s+)?rules|ignore\s+(?:the\s+)?caller"
    r"|prompt[- ]injection|not\s+policy", re.I
)


def mentions(text):
    """Return each recognized topic and the exact words supporting it."""
    found = {}
    for topic, aliases in ALIASES.items():
        for alias in aliases:
            pattern = r"\b" + re.escape(alias) + r"\b"
            matches = []
            for match in re.finditer(pattern, text, re.I):
                matches.append(match.group())
            if matches:
                unique_matches = []
                for matched_text in matches:
                    if matched_text not in unique_matches:
                        unique_matches.append(matched_text)
                found[topic] = unique_matches
                break
    return found


def is_evidence(text):
    """Exclude text matching the known instruction-like phrases above."""
    return INJECTION.search(text) is None


def unsupported_scope(question, passages):
    """Check whether the question asks for information outside these policies."""
    qualifiers = ("hotel", "hotels", "flight", "flights", "meals", "taxi", "taxis",
                  "remaining balance", "remaining entitlement", "already claimed")
    lower = question.lower()
    evidence = " ".join(passages).lower()
    if re.search(r"\b(paid|payable|payment|eligible|eligibility|approve|approved claim)\b", lower):
        return True
    for term in qualifiers:
        if term in lower and term not in evidence:
            return True
    if re.search(r"manager\s+approval", lower) and "manager approval" not in evidence:
        return True
    if re.search(r"\b(limit|allowance|amount)\b", lower):
        for passage in passages:
            if re.search(r"\b(?:INR|USD|EUR|GBP|JPY)\s+\d", passage):
                return False
        return True
    return False
