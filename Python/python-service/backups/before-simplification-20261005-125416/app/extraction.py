from io import BytesIO
from decimal import Decimal
import re
import math
from pypdf import PdfReader
from .errors import ServiceError
from .models import Extracted
from .topics import mentions

MONEY = re.compile(r"\b(INR|USD|EUR|GBP|JPY)\s+((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?)(?![0-9,]|\.[0-9])", re.I)
CURRENCY = re.compile(r"\b(INR|USD|EUR|GBP|JPY)\b", re.I)
REFERENCE = re.compile(r"\bReference:\s*([A-Za-z0-9_-]+)", re.I)


def read_document(filename, content):
    if not content:
        raise ServiceError("EMPTY_FILE", "The uploaded file is empty.", 422)
    if len(content) > 5 * 1024 * 1024:
        raise ServiceError("UPLOAD_TOO_LARGE", "The document exceeds 5 MB.", 413)
    try:
        if filename.lower().endswith(".txt"):
            text = content.decode("utf-8-sig", errors="strict")
            if "\x00" in text:
                raise ValueError("Binary content")
        elif filename.lower().endswith(".pdf"):
            pdf = PdfReader(BytesIO(content), strict=True)
            if pdf.is_encrypted or len(pdf.pages) > 20:
                raise ValueError("Encrypted or oversized PDF")
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        else:
            raise ServiceError("UNSUPPORTED_FILE", "Only UTF-8 TXT and text-based PDF files are supported.", 422)
        if not text.strip() or len(text) > 100000:
            raise ValueError("Empty or oversized text")
        return text
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError("UNREADABLE_FILE", "The file does not contain readable supported text.", 422) from exc


def extract(text):
    evidence, issues = {}, []
    benefits = mentions(text)
    benefit = next(iter(benefits)) if len(benefits) == 1 else None
    if benefit:
        evidence["benefit"] = benefits[benefit]
    else:
        issues.append("Requested benefit is missing or ambiguous.")
    money = list(MONEY.finditer(text))
    amounts = {Decimal(m.group(2).replace(",", "")) for m in money}
    currency_matches = list(CURRENCY.finditer(text))
    currencies = {m.group(1).upper() for m in currency_matches}
    amount = float(next(iter(amounts))) if len(amounts) == 1 else None
    if amount is not None and not math.isfinite(amount):
        amount = None
        issues.append("Stated amount exceeds the supported numeric range.")
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    if amount is not None:
        evidence["amount"] = list(dict.fromkeys(m.group() for m in money))
    elif amounts:
        issues.append("Conflicting stated amounts: " + ", ".join(str(a) for a in sorted(amounts)) + ".")
    else:
        issues.append("Requested amount is missing.")
    if currency:
        evidence["currency"] = list(dict.fromkeys(m.group() for m in currency_matches))
    else:
        issues.append("Currency is missing or ambiguous.")
    refs = list(REFERENCE.finditer(text))
    unique_refs = {m.group(1) for m in refs}
    reference = next(iter(unique_refs)) if len(unique_refs) == 1 else None
    if reference:
        evidence["reference"] = list(dict.fromkeys(m.group() for m in refs))
    else:
        issues.append("Reference is missing or ambiguous.")
    for quotes in evidence.values():
        if any(quote not in text for quote in quotes):
            raise ServiceError("EXTRACTION_ERROR", "Extracted evidence could not be verified.")
    return Extracted(benefit=benefit, amount=amount, currency=currency, reference=reference), evidence, issues
