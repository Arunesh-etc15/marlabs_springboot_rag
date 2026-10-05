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
    found = {}
    for topic, aliases in ALIASES.items():
        for alias in aliases:
            matches = [m.group() for m in re.finditer(r"\b" + re.escape(alias) + r"\b", text, re.I)]
            if matches:
                found[topic] = list(dict.fromkeys(matches))
                break
    return found


def is_evidence(text):
    return not bool(INJECTION.search(text))


def unsupported_scope(question, passages):
    qualifiers = ("hotel", "hotels", "flight", "flights", "meals", "taxi", "taxis",
                  "remaining balance", "remaining entitlement", "already claimed")
    lower, evidence = question.lower(), " ".join(passages).lower()
    if re.search(r"\b(paid|payable|payment|eligible|eligibility|approve|approved claim)\b", lower):
        return True
    if any(term in lower and term not in evidence for term in qualifiers):
        return True
    if re.search(r"manager\s+approval", lower) and "manager approval" not in evidence:
        return True
    if re.search(r"\b(limit|allowance|amount)\b", lower):
        return not any(re.search(r"\b(?:INR|USD|EUR|GBP|JPY)\s+\d", p) for p in passages)
    return False
