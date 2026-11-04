"""Code execution through a Judge0 server. Nothing runs on this application server.
If JUDGE0_URL is not set, execution is reported as unavailable. Success is never simulated."""
import os

import httpx

LANGUAGES = {"python": 71, "java": 62, "c": 50, "cpp": 54}  # Judge0 CE defaults; verify against your instance's /languages
MAX_SOURCE = 20_000
MAX_STDIN = 5_000


class ExecutionUnavailable(Exception):
    pass


def execute(language: str, source: str, stdin: str = "") -> dict:
    base = os.getenv("JUDGE0_URL", "").strip()
    if not base:
        raise ExecutionUnavailable("The code execution service is not configured.")
    headers = {"X-Auth-Token": os.environ["JUDGE0_AUTH_TOKEN"]} if os.getenv("JUDGE0_AUTH_TOKEN") else {}
    try:
        r = httpx.post(f"{base.rstrip('/')}/submissions", params={"base64_encoded": "false", "wait": "true"},
                       json={"source_code": source, "language_id": LANGUAGES[language], "stdin": stdin,
                             "cpu_time_limit": 5, "memory_limit": 128000},
                       headers=headers, timeout=30)
    except httpx.HTTPError:
        raise ExecutionUnavailable("The code execution service could not be reached.")
    if r.status_code >= 400:
        raise ExecutionUnavailable("The code execution service returned an error.")
    d = r.json()
    status = d.get("status") or {}
    return {"stdout": d.get("stdout") or "", "stderr": d.get("stderr") or "", "compile_output": d.get("compile_output") or "",
            "status": status.get("description", ""), "status_id": status.get("id"), "time": d.get("time"), "memory": d.get("memory")}
