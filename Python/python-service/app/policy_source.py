"""Read the numbered policy records directly from the source PDF."""

import re
from pathlib import Path

from pypdf import PdfReader

from .models import Policy


RECORD_HEADER = re.compile(r"(?m)^[ \t]*[0-9]+\.[ \t]+([A-Za-z0-9_-]+)[ \t]*$")
METADATA = re.compile(
    r"([^|]+)\|([^|]+)\|\s*(Approved|Draft)\s*\|\s*"
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})\s+to\s+([0-9]{4}-[0-9]{2}-[0-9]{2})"
)


def load_pdf_policies(path):
    """Extract readable PDF text; never fall back to policy JSON."""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("POLICY_FILE must point to a policy PDF, not JSON.")

    with path.open("rb") as source:
        pdf = PdfReader(source, strict=True)
        if pdf.is_encrypted:
            raise ValueError("The policy PDF must not be encrypted.")
        pages = []
        for page in pdf.pages:
            pages.append(page.extract_text() or "")

    # Join pages before parsing: a policy can continue onto the next page.
    return parse_policy_text("\n".join(pages))


def parse_policy_text(text):
    """Parse ID, access/date metadata, and policy text without using an LLM."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    headers = list(RECORD_HEADER.finditer(text))
    if not headers or text[:headers[0].start()].strip():
        raise ValueError("The PDF must contain numbered policy records with metadata.")

    policies_by_id = {}
    for position, header in enumerate(headers):
        end = headers[position + 1].start() if position + 1 < len(headers) else len(text)
        block = text[header.end():end].strip()
        lines = block.splitlines()
        metadata = METADATA.fullmatch(lines[0].strip()) if lines else None
        if metadata is None:
            raise ValueError(f"Missing or invalid policy metadata for {header.group(1)}.")
        if not metadata.group(1).strip() or not metadata.group(2).strip():
            raise ValueError("Policy tenant and role cannot be blank.")

        # PDF line/page wrapping is formatting, not part of the logical quotation.
        policy_text = " ".join(" ".join(lines[1:]).split())
        policy = Policy(
            id=header.group(1),
            tenant=metadata.group(1).strip(),
            role=metadata.group(2).strip(),
            approval_state=metadata.group(3),
            effective_from=metadata.group(4),
            effective_to=metadata.group(5),
            text=policy_text,
        )
        if policy.id in policies_by_id and policies_by_id[policy.id] != policy:
            raise ValueError("Policy IDs must not identify different records.")
        policies_by_id[policy.id] = policy

    return sorted(policies_by_id.values(), key=lambda policy: policy.id)
