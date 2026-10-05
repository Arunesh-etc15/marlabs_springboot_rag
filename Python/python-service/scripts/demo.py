"""Run both services temporarily and save public API demonstration responses."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT.parent if (ROOT.parent / "spring-api").is_dir() else ROOT.parent.parent / "SpringBoot"
EXAMPLES = ROOT / "tests/fixtures/pdf-batch"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(url, process, method="get", body=None):
    deadline = time.monotonic() + 30
    with httpx.Client(trust_env=False, timeout=1) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("A demonstration service exited before startup.")
            try:
                response = client.request(method, url, json=body)
                if response.status_code in (200, 401):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
    raise RuntimeError("Service startup timed out.")


def main():
    argparse.ArgumentParser(description="Run the public API demo using Ollama.").parse_args()
    java = shutil.which("java")
    jar = DATA_ROOT / "spring-api/target/policy-api-0.0.1-SNAPSHOT.jar"
    if not java or not jar.exists():
        raise RuntimeError("Java and the packaged Spring Boot JAR are required; run the Maven package goal first.")
    # Resolve the actual JVM rather than a Windows launcher that spawns another process.
    java_info = subprocess.run([java, "-XshowSettings:properties", "-version"],
                               capture_output=True, text=True, check=True)
    match = re.search(r"^\s*java.home\s*=\s*(.+)$", java_info.stderr, re.MULTILINE)
    if match:
        candidate = Path(match.group(1).strip()) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if candidate.exists():
            java = str(candidate)
    children = []
    output = ROOT / "demo-responses"
    output.mkdir(exist_ok=True)
    headers = {"X-Caller-Id": "atlas-employee-01"}
    question = {"question": "What is my annual certification reimbursement limit?", "as_of": "2026-09-21"}
    py_port, java_port = free_port(), free_port()
    python_url, public_url = f"http://127.0.0.1:{py_port}", f"http://127.0.0.1:{java_port}"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    # Windows may briefly retain memory-mapped Chroma files after the child exits.
    with tempfile.TemporaryDirectory(prefix="policy-demo-", ignore_cleanup_errors=True) as cache:
        try:
            env = dict(os.environ, CHROMA_PATH=cache)
            python = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(py_port)],
                cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            children.append(python)
            wait_ready(python_url + "/health", python)
            spring = subprocess.Popen(
                [java, "-jar", str(jar), f"--server.port={java_port}",
                 f"--python.base-url={python_url}", "--python.read-timeout-ms=70000"],
                cwd=jar.parent.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            children.append(spring)
            wait_ready(public_url + "/answer", spring, "post", question)
            with httpx.Client(base_url=public_url, trust_env=False, timeout=600) as client:
                response = client.post("/answer", headers=headers, json=question)
                response.raise_for_status()
                answer = response.json()
                (output / "answer.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
                manifest = json.loads((EXAMPLES / "batch.json").read_text())
                files = [("metadata", ("batch.json", json.dumps(manifest), "application/json"))]
                for entry in manifest["documents"]:
                    file = EXAMPLES / entry["filename"]
                    files.append(("files", (file.name, file.read_bytes(),
                                           "application/pdf" if file.suffix == ".pdf" else "text/plain")))
                response = client.post("/batches", headers=headers, files=files)
                response.raise_for_status()
                batch = response.json()
                (output / "batch.json").write_text(json.dumps(batch, indent=2), encoding="utf-8")
                assert batch["summary"] == {"total": 8, "completed": 7, "failed": 1}
                results = batch["results"]
                assert results[1]["policy"]["status"] == "CONFLICT"
                assert results[2]["extracted"]["amount"] is None
                assert results[3]["policy"]["status"] == "INSUFFICIENT_EVIDENCE"
                assert results[4]["policy"]["citations"][0]["chunk_id"] == "atlas-cert-current"
                assert results[5]["duplicate_of"] == "request-01"
                assert results[7]["error"]["code"] == "EMPTY_FILE"
                assert all(r["review_required"] for r in results)
                unreadable = dict(manifest, batch_id="failure-isolation", documents=[
                    {"document_id": "bad", "filename": "bad.pdf"},
                    {"document_id": "good", "filename": "good.txt"}])
                response = client.post("/batches", headers=headers, files=[
                    ("metadata", ("batch.json", json.dumps(unreadable), "application/json")),
                    ("files", ("bad.pdf", b"not a PDF", "application/pdf")),
                    ("files", ("good.txt", (EXAMPLES / "request-01.txt").read_bytes(), "text/plain"))])
                response.raise_for_status()
                mixed = response.json()
                assert mixed["summary"] == {"total": 2, "completed": 1, "failed": 1}
                assert mixed["results"][0]["processing_status"] == "FAILED"
                (output / "unreadable-mixed-batch.json").write_text(json.dumps(mixed, indent=2), encoding="utf-8")
                print("Provider: Ollama", "Answer:", answer["status"], "Batch:", batch["summary"])
                print("Saved responses:", output)
        finally:
            for process in reversed(children):
                if os.name == "nt" and process.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
