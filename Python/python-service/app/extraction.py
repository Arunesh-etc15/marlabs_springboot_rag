"""Read TXT/PDF documents and extract fields using rules, not the LLM."""

from io import BytesIO
from decimal import Decimal
import re
import math
from pypdf import PdfReader
from .errors import ServiceError
from .models import Extracted
from .topics import mentions

# Currency + correctly grouped digits + optional cents; reject partial bad numbers.
MONEY = re.compile(
    r"\b(INR|USD|EUR|GBP|JPY)\s+"
    r"((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?)"
    r"(?![0-9,]|\.[0-9])",
    re.I,
)
CURRENCY = re.compile(r"\b(INR|USD|EUR|GBP|JPY)\b", re.I)
REFERENCE = re.compile(r"\bReference:\s*([A-Za-z0-9_-]+)", re.I)
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_TEXT_CHARACTERS = 100000


def read_document(filename, content):
    """Return readable text, or a safe error for unsupported/unreadable files."""
    if not content:
        raise ServiceError("EMPTY_FILE", "The uploaded file is empty.", 422)
    if len(content) > MAX_FILE_BYTES:
        raise ServiceError("UPLOAD_TOO_LARGE", "The document exceeds 5 MB.", 413)
    try:
        if filename.lower().endswith(".txt"):
            text = content.decode("utf-8-sig", errors="strict")
            if "\x00" in text:
                raise ValueError("Binary content")
        elif filename.lower().endswith(".pdf"):
            pdf = PdfReader(BytesIO(content), strict=True)
            if pdf.is_encrypted or len(pdf.pages) > MAX_PDF_PAGES:
                raise ValueError("Encrypted or oversized PDF")
            page_texts = []
            for page in pdf.pages:
                page_texts.append(page.extract_text() or "")
            text = "\n".join(page_texts)
        else:
            raise ServiceError("UNSUPPORTED_FILE", "Only UTF-8 TXT and text-based PDF files are supported.", 422)
        if not text.strip() or len(text) > MAX_TEXT_CHARACTERS:
            raise ValueError("Empty or oversized text")
        return text
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError("UNREADABLE_FILE", "The file does not contain readable supported text.", 422) from exc


def extract(text):
    """Keep only unambiguous values and their exact supporting document quotes."""
    evidence = {}
    issues = []

    # Benefit: accept exactly one recognized topic.
    benefits = mentions(text)
    benefit = None
    if len(benefits) == 1:
        benefit_names = list(benefits.keys())
        benefit = benefit_names[0]
    if benefit:
        evidence["benefit"] = benefits[benefit]
    else:
        issues.append("Requested benefit is missing or ambiguous.")
    # Amount: repeated equal numbers are fine; differing numbers stay unresolved.
    money_matches = list(MONEY.finditer(text))
    amounts = set()
    for match in money_matches:
        number = match.group(2).replace(",", "")
        amounts.add(Decimal(number))

    currency_matches = list(CURRENCY.finditer(text))
    currencies = set()
    for match in currency_matches:
        currency_name = match.group(1).upper()
        currencies.add(currency_name)
    amount = None
    if len(amounts) == 1:
        unique_amounts = list(amounts)
        amount = float(unique_amounts[0])
    if amount is not None and not math.isfinite(amount):
        amount = None
        issues.append("Stated amount exceeds the supported numeric range.")
    if amount is not None:
        evidence["amount"] = matching_quotes(money_matches)
    elif amounts:
        amount_labels = []
        for value in sorted(amounts):
            amount_labels.append(str(value))
        issues.append("Conflicting stated amounts: " + ", ".join(amount_labels) + ".")
    else:
        issues.append("Requested amount is missing.")
    # Currency is independent: an ambiguous amount can still have a known currency.
    currency = None
    if len(currencies) == 1:
        unique_currencies = list(currencies)
        currency = unique_currencies[0]
    if currency:
        evidence["currency"] = matching_quotes(currency_matches)
    else:
        issues.append("Currency is missing or ambiguous.")
    reference_matches = list(REFERENCE.finditer(text))
    references = set()
    for match in reference_matches:
        references.add(match.group(1))
    reference = None
    if len(references) == 1:
        unique_references = list(references)
        reference = unique_references[0]
    if reference:
        evidence["reference"] = matching_quotes(reference_matches)
    else:
        issues.append("Reference is missing or ambiguous.")
    for quotes in evidence.values():
        for quote in quotes:
            if quote not in text:
                raise ServiceError("EXTRACTION_ERROR", "Extracted evidence could not be verified.")
    extracted = Extracted(
        benefit=benefit,
        amount=amount,
        currency=currency,
        reference=reference,
    )
    return extracted, evidence, issues


def matching_quotes(matches):
    """Keep exact regex matches once, in their original document order."""
    quotes = []
    for match in matches:
        quote = match.group()
        if quote not in quotes:
            quotes.append(quote)
    return quotes
