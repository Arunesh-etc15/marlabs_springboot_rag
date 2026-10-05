from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.policy_source import load_pdf_policies, parse_policy_text


SOURCE = Path(__file__).parent / "fixtures/policy-source.pdf"
RECORD = (
    "1. atlas-cert-current\n"
    "Atlas | employee | Approved | 2026-06-01 to 2027-01-01\n"
    "The annual certification reimbursement limit for employees is INR 25000."
)


def test_real_pdf_has_all_records_and_cross_page_policy():
    records = load_pdf_policies(SOURCE)
    policies = {policy.id: policy for policy in records}
    assert len(records) == 12
    assert policies["atlas-cert-current"].text.endswith("INR 25000.")
    assert policies["atlas-travel-current"].text == (
        "Employees may claim rail travel for approved business trips."
    )
    assert "every allowance" in policies["atlas-injection-example"].text
    assert policies["atlas-cert-draft"].approval_state == "Draft"


def test_wrapped_policy_quotes_are_normalized_consistently():
    records = parse_policy_text(RECORD.replace("employees is", "employees\n\n is"))
    assert records[0].text == RECORD.splitlines()[-1]


def test_identical_duplicate_ids_are_deduplicated():
    assert len(parse_policy_text(RECORD + "\n" + RECORD)) == 1


def test_conflicting_duplicate_ids_are_rejected():
    with pytest.raises(ValueError, match="different records"):
        parse_policy_text(RECORD + "\n" + RECORD.replace("25000", "27000"))


@pytest.mark.parametrize("text", [
    "", "Unstructured policy text.",
    "Unrecognized preamble\n" + RECORD,
    RECORD.replace(" | employee |", " | |"),
    RECORD.replace("Approved", "Unknown"),
    RECORD.replace("2026-06-01", "2026-02-30"),
    RECORD.replace("2027-01-01", "2026-01-01"),
    "\n".join(RECORD.splitlines()[:2]),
])
def test_bad_policy_records_fail_closed(text):
    with pytest.raises(ValueError):
        parse_policy_text(text)


def test_policy_json_is_not_accepted(tmp_path):
    path = tmp_path / "policies.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="PDF, not JSON"):
        load_pdf_policies(path)


def test_scanned_or_empty_pdf_is_not_accepted_without_ocr(tmp_path):
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(path)
    with pytest.raises(ValueError, match="numbered policy records"):
        load_pdf_policies(path)


def test_encrypted_policy_pdf_is_rejected(tmp_path):
    path = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    writer.write(path)
    with pytest.raises(ValueError, match="encrypted"):
        load_pdf_policies(path)
