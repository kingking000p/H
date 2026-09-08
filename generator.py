from pathlib import Path
import os
import stat
import time
import re
import sys
import requests


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_FILE = BASE_DIR / "template.sh"
ADDRESSES_FILE = BASE_DIR / "addresses.txt"
OUTPUT_FILE = BASE_DIR / "script.sh"

BATCH_SIZE = 3

# GitHub
GITHUB_OWNER = "forgotenmywin"
GITHUB_REPO = "K"
GITHUB_REF = "main"
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "main.yml")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"

# Section 2 timing
INITIAL_WAIT_SECONDS = 60
JOB_RETRY_COUNT = 24
JOB_RETRY_DELAY = 5


# ============================================================
# HELPERS
# ============================================================

def fail(message: str):
    print()
    print("ERROR:", message)
    print()
    sys.exit(1)


def github_headers():
    if not GITHUB_TOKEN:
        fail("GITHUB_TOKEN is not set")

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def validate_response(response, expected_codes=(200,)):
    if response.status_code not in expected_codes:
        body = response.text[:1000]
        fail(
            f"GitHub API error\n"
            f"HTTP: {response.status_code}\n"
            f"URL: {response.url}\n"
            f"Response: {body}"
        )


# ============================================================
# SECTION 1
# ============================================================

print("======================================")
print(" FIRST BATCH GENERATOR")
print("======================================")

# ------------------------------------------------------------
# Check files
# ------------------------------------------------------------

if not ADDRESSES_FILE.exists():
    fail(f"Missing file: {ADDRESSES_FILE}")

if not TEMPLATE_FILE.exists():
    fail(f"Missing file: {TEMPLATE_FILE}")

# ------------------------------------------------------------
# Load addresses.txt
# ------------------------------------------------------------

raw_lines = ADDRESSES_FILE.read_text(encoding="utf-8").splitlines()

records = []

for line_no, raw in enumerate(raw_lines, start=1):
    line = raw.strip()

    if not line:
        continue

    if ":" not in line:
        fail(
            f"Invalid addresses.txt format at line {line_no}: "
            f"{raw}"
        )

    index_text, address = line.split(":", 1)

    index_text = index_text.strip()
    address = address.strip()

    if not index_text.isdigit():
        fail(
            f"Invalid index at line {line_no}: "
            f"{index_text}"
        )

    if not address:
        fail(
            f"Empty address at line {line_no}"
        )

    records.append(
        {
            "index": int(index_text),
            "address": address,
        }
    )

print(f"Loaded records: {len(records)}")

if len(records) != 102:
    fail(
        f"Expected exactly 102 records, "
        f"found {len(records)}"
    )

# ------------------------------------------------------------
# Load template
# ------------------------------------------------------------

template = TEMPLATE_FILE.read_text(encoding="utf-8")

print("Loaded template: template.sh")

if "__ADDRESS1__" not in template:
    fail("Missing placeholder: __ADDRESS1__")

if "__INDEX1__" not in template:
    fail("Missing placeholder: __INDEX1__")

if "__ADDRESS2__" not in template:
    fail("Missing placeholder: __ADDRESS2__")

if "__INDEX2__" not in template:
    fail("Missing placeholder: __INDEX2__")

if "__ADDRESS3__" not in template:
    fail("Missing placeholder: __ADDRESS3__")

if "__INDEX3__" not in template:
    fail("Missing placeholder: __INDEX3__")

# ------------------------------------------------------------
# First 3 records
# ------------------------------------------------------------

batch = records[:BATCH_SIZE]

print("First batch:")

for pos, item in enumerate(batch, start=1):
    print(f"  TARGET{pos}")
    print(f"    index:   {item['index']}")
    print(f"    address: {item['address']}")

# ------------------------------------------------------------
# Replace placeholders
# ------------------------------------------------------------

generated = template

generated = generated.replace(
    "__ADDRESS1__",
    batch[0]["address"]
)
generated = generated.replace(
    "__INDEX1__",
    str(batch[0]["index"])
)

generated = generated.replace(
    "__ADDRESS2__",
    batch[1]["address"]
)
generated = generated.replace(
    "__INDEX2__",
    str(batch[1]["index"])
)

generated = generated.replace(
    "__ADDRESS3__",
    batch[2]["address"]
)
generated = generated.replace(
    "__INDEX3__",
    str(batch[2]["index"])
)

# ------------------------------------------------------------
# Write generated script
# ------------------------------------------------------------

OUTPUT_FILE.write_text(
    generated,
    encoding="utf-8"
)

OUTPUT_FILE.chmod(
    OUTPUT_FILE.stat().st_mode | stat.S_IXUSR
)

print("======================================")
print("GENERATED FILE")
print("======================================")
print(f"Output: {OUTPUT_FILE}")
print(f"Size:   {OUTPUT_FILE.stat().st_size} bytes")

print("======================================")
print("GENERATED TARGETS")
print("======================================")
print(
    f"ADDRESS1 = {batch[0]['address']}"
)
print(
    f"INDEX1   = {batch[0]['index']}"
)
print(
    f"ADDRESS2 = {batch[1]['address']}"
)
print(
    f"INDEX2   = {batch[1]['index']}"
)
print(
    f"ADDRESS3 = {batch[2]['address']}"
)
print(
    f"INDEX3   = {batch[2]['index']}"
)

print("======================================")
print("SECTION 1 COMPLETE")
print("======================================")


# ============================================================
# SECTION 2
# ============================================================

print("======================================")
print(" SECTION 2 - GITHUB WORKFLOW")
print("======================================")

print(f"Repository : {GITHUB_OWNER}/{GITHUB_REPO}")
print(f"Workflow   : {WORKFLOW_FILE}")
print(f"Ref        : {GITHUB_REF}")

if not GITHUB_TOKEN:
    fail("GITHUB_TOKEN is missing from Railway Variables")

print("GitHub Token: FOUND")


# ============================================================
# 2A. TRIGGER WORKFLOW AND GET EXACT RUN ID
# ============================================================

dispatch_url = (
    f"{GITHUB_API}/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/"
    f"workflows/{WORKFLOW_FILE}/dispatches"
)

dispatch_payload = {
    "ref": GITHUB_REF,
    "return_run_details": True,
}

try:
    dispatch_response = requests.post(
        dispatch_url,
        headers=github_headers(),
        json=dispatch_payload,
        timeout=30,
    )
except requests.RequestException as exc:
    fail(f"Workflow dispatch request failed: {exc}")

if dispatch_response.status_code not in (200, 204):
    fail(
        f"Workflow dispatch failed\n"
        f"HTTP: {dispatch_response.status_code}\n"
        f"Response: {dispatch_response.text[:1000]}"
    )

print("Workflow dispatch: SUCCESS")


# ============================================================
# 2B. READ RUN ID DIRECTLY FROM DISPATCH RESPONSE
# ============================================================

run_id = None

if dispatch_response.status_code == 200:
    try:
        dispatch_json = dispatch_response.json()
    except ValueError:
        fail(
            "GitHub returned HTTP 200 but response was not JSON"
        )

    run_id = dispatch_json.get("workflow_run_id")

    if not run_id:
        fail(
            "GitHub returned 200 but workflow_run_id was missing"
        )

else:
    # Compatibility fallback:
    # If GitHub ever returns 204, find the newest matching run.
    print(
        "Dispatch returned 204; "
        "using fallback Run-ID discovery..."
    )

    runs_url = (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/"
        f"workflows/{WORKFLOW_FILE}/runs"
    )

    deadline = time.time() + 30

    while time.time() < deadline:
        try:
            runs_response = requests.get(
                runs_url,
                headers=github_headers(),
                params={
                    "branch": GITHUB_REF,
                    "per_page": 10,
                },
                timeout=30,
            )
        except requests.RequestException:
            time.sleep(2)
            continue

        if runs_response.status_code == 200:
            try:
                runs_json = runs_response.json()
            except ValueError:
                time.sleep(2)
                continue

            workflow_runs = runs_json.get(
                "workflow_runs",
                []
            )

            if workflow_runs:
                run_id = workflow_runs[0].get("id")

                if run_id:
                    break

        time.sleep(2)

    if not run_id:
        fail(
            "Could not determine workflow Run ID"
        )

print(f"Workflow Run ID: {run_id}")


# ============================================================
# 2C. WAIT EXACTLY 60 SECONDS
# ============================================================

print("Waiting 60 seconds for workflow logs...")

for remaining in range(
    INITIAL_WAIT_SECONDS,
    0,
    -10
):
    print(
        f"  {remaining} seconds remaining..."
    )
    sleep_for = min(10, remaining)
    time.sleep(sleep_for)

print("60 seconds completed.")


# ============================================================
# 2D. FIND JOBS FOR THIS EXACT RUN
# ============================================================

jobs_url = (
    f"{GITHUB_API}/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/"
    f"runs/{run_id}/jobs"
)

job = None

print("Searching for job in this Run...")

for attempt in range(
    1,
    JOB_RETRY_COUNT + 1
):
    try:
        jobs_response = requests.get(
            jobs_url,
            headers=github_headers(),
            params={
                "filter": "all",
                "per_page": 100,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        print(
            f"  Job request failed "
            f"(attempt {attempt}/{JOB_RETRY_COUNT}): {exc}"
        )
        time.sleep(JOB_RETRY_DELAY)
        continue

    if jobs_response.status_code == 200:
        try:
            jobs_json = jobs_response.json()
        except ValueError:
            print(
                f"  Invalid JSON from jobs endpoint "
                f"(attempt {attempt}/{JOB_RETRY_COUNT})"
            )
            time.sleep(JOB_RETRY_DELAY)
            continue

        jobs = jobs_json.get("jobs", [])

        if jobs:
            # Prefer the known job name "debug"
            debug_jobs = [
                item
                for item in jobs
                if item.get("name") == "debug"
            ]

            if debug_jobs:
                job = debug_jobs[0]
            else:
                job = jobs[0]

            break

        print(
            f"  No job yet "
            f"(attempt {attempt}/{JOB_RETRY_COUNT})"
        )

    else:
        print(
            f"  Jobs API HTTP {jobs_response.status_code} "
            f"(attempt {attempt}/{JOB_RETRY_COUNT})"
        )

    time.sleep(JOB_RETRY_DELAY)


if not job:
    fail(
        "Could not find a job for the workflow Run"
    )

job_id = job.get("id")
job_name = job.get("name")
job_status = job.get("status")
job_conclusion = job.get("conclusion")

print("Job found:")
print(f"  Job ID      : {job_id}")
print(f"  Job name    : {job_name}")
print(f"  Job status  : {job_status}")
print(f"  Conclusion  : {job_conclusion}")


# ============================================================
# 2E. DOWNLOAD JOB LOG
# ============================================================

job_logs_url = (
    f"{GITHUB_API}/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/"
    f"jobs/{job_id}/logs"
)

logs_text = None

print("Retrieving Job logs...")

for attempt in range(
    1,
    JOB_RETRY_COUNT + 1
):
    try:
        log_response = requests.get(
            job_logs_url,
            headers=github_headers(),
            allow_redirects=False,
            timeout=30,
        )
    except requests.RequestException as exc:
        print(
            f"  Log request failed "
            f"(attempt {attempt}/{JOB_RETRY_COUNT}): {exc}"
        )
        time.sleep(JOB_RETRY_DELAY)
        continue

    # GitHub returns a redirect to the actual log file.
    if log_response.status_code == 302:
        location = log_response.headers.get("Location")

        if not location:
            print(
                "  HTTP 302 received but Location header "
                "was missing"
            )
            time.sleep(JOB_RETRY_DELAY)
            continue

        try:
            download_response = requests.get(
                location,
                timeout=30,
            )
        except requests.RequestException as exc:
            print(
                f"  Log download failed "
                f"(attempt {attempt}/{JOB_RETRY_COUNT}): {exc}"
            )
            time.sleep(JOB_RETRY_DELAY)
            continue

        if download_response.status_code == 200:
            logs_text = download_response.text
            break

        print(
            f"  Signed log URL returned "
            f"HTTP {download_response.status_code}"
        )

    elif log_response.status_code == 200:
        logs_text = log_response.text
        break

    else:
        print(
            f"  Log endpoint HTTP "
            f"{log_response.status_code} "
            f"(attempt {attempt}/{JOB_RETRY_COUNT})"
        )

    time.sleep(JOB_RETRY_DELAY)


if logs_text is None:
    fail(
        "Could not retrieve workflow job logs "
        "after all retries"
    )


print(
    f"Retrieved logs: {len(logs_text)} characters"
)


# ============================================================
# 2F. FIND ENDPOINT + TOKEN
# ============================================================

# Endpoint format expected from your workflow:
# API:
# https://something.trycloudflare.com/command

endpoint_match = re.search(
    r"(?m)^\s*API:\s*(https://[^\s]+/command)\s*$",
    logs_text,
)

# Token format:
# TOKEN:
# abcdefghijkl....
token_match = re.search(
    r"(?m)^\s*TOKEN:\s*([A-Za-z0-9_-]{20,})\s*$",
    logs_text,
)

print("======================================")
print(" LOG SEARCH RESULTS")
print("======================================")

if endpoint_match:
    endpoint = endpoint_match.group(1).strip()

    print("Endpoint: FOUND")
    print(f"Endpoint URL: {endpoint}")
else:
    endpoint = None
    print("Endpoint: NOT FOUND")

if token_match:
    workflow_token = token_match.group(1).strip()

    print("Token: FOUND")
    print(
        "Token value: [REDACTED]"
    )
else:
    workflow_token = None
    print("Token: NOT FOUND")


# ============================================================
# 2G. PRINT CURL TEMPLATE ONLY
#     NO CURL IS EXECUTED
#     NO SCRIPT IS EXECUTED
# ============================================================

if endpoint and workflow_token:

    print("======================================")
    print(" FOUND — CURL COMMANDS")
    print("======================================")

    print("curl -X POST "
          f"\"{endpoint}\" \\")
    print("  -H "
          "\"Authorization: Bearer <WORKFLOW_TOKEN>\" \\")
    print("  -H "
          "\"Content-Type: application/json\" \\")
    print("  -d "
          "'{\"command\":\"whoami && id\"}'")

    print()
    print("For script.sh:")
    print()

    print("B64=$(base64 -w0 /app/script.sh)")

    print(
        "curl -X POST "
        f"\"{endpoint}\" \\"
    )
    print(
        "  -H "
        "\"Authorization: Bearer <WORKFLOW_TOKEN>\" \\"
    )
    print(
        "  -H "
        "\"Content-Type: application/json\" \\"
    )
    print(
        "  -d "
        "'{\"command\":\"echo '$B64' > /tmp/script.b64\"}'"
    )

    print()

    print(
        "curl -X POST "
        f"\"{endpoint}\" \\"
    )
    print(
        "  -H "
        "\"Authorization: Bearer <WORKFLOW_TOKEN>\" \\"
    )
    print(
        "  -H "
        "\"Content-Type: application/json\" \\"
    )
    print(
        "  -d "
        "'{\"command\":\"base64 -d /tmp/script.b64 | bash\"}' \\"
    )
    print(
        "  --max-time 300"
    )

    print("======================================")
    print("SECTION 2 COMPLETE")
    print("======================================")

else:
    print("======================================")
    print("SECTION 2 FAILED")
    print("======================================")

    if not endpoint:
        print("Reason: API endpoint was not found.")

    if not workflow_token:
        print("Reason: workflow token was not found.")

    sys.exit(1)
