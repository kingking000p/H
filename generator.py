from pathlib import Path
import os
import stat
import sys
import time
import re
import requests

# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_FILE = BASE_DIR / "template.sh"
ADDRESSES_FILE = BASE_DIR / "addresses.txt"
OUTPUT_FILE = BASE_DIR / "script.sh"

BATCH_SIZE = 3

# ============================================================
# GITHUB CONFIG - SECTION 2
# ============================================================

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE")

GITHUB_OWNER = "forgotenmywin"
GITHUB_REPO = "K"
GITHUB_REF = "main"

GITHUB_API = "https://api.github.com"

# ============================================================
# READ 102 RECORDS
# ============================================================

def read_records():
    if not ADDRESSES_FILE.exists():
        raise SystemExit(f"ERROR: {ADDRESSES_FILE.name} not found")

    records = []

    with ADDRESSES_FILE.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()

            if not line:
                continue

            if ":" not in line:
                raise SystemExit(
                    f"ERROR: invalid format at line {line_no}: {line}"
                )

            index_text, address = line.split(":", 1)

            index_text = index_text.strip()
            address = address.strip()

            if not index_text:
                raise SystemExit(
                    f"ERROR: missing index at line {line_no}"
                )

            if not address:
                raise SystemExit(
                    f"ERROR: missing address at line {line_no}"
                )

            try:
                index = int(index_text)
            except ValueError:
                raise SystemExit(
                    f"ERROR: index is not an integer at line "
                    f"{line_no}: {index_text}"
                )

            records.append({
                "index": index,
                "address": address,
            })

    if len(records) != 102:
        raise SystemExit(
            f"ERROR: expected exactly 102 records, found {len(records)}"
        )

    return records


# ============================================================
# READ ORIGINAL TEMPLATE
# ============================================================

def read_template():
    if not TEMPLATE_FILE.exists():
        raise SystemExit(f"ERROR: {TEMPLATE_FILE.name} not found")

    return TEMPLATE_FILE.read_text(encoding="utf-8")


# ============================================================
# BUILD FIRST BATCH ONLY
# ============================================================

def build_first_batch(template, records):
    if len(records) < BATCH_SIZE:
        raise SystemExit("ERROR: fewer than 3 records available")

    first = records[0]
    second = records[1]
    third = records[2]

    replacements = {
        "__ADDRESS1__": first["address"],
        "__INDEX1__": str(first["index"]),

        "__ADDRESS2__": second["address"],
        "__INDEX2__": str(second["index"]),

        "__ADDRESS3__": third["address"],
        "__INDEX3__": str(third["index"]),
    }

    result = template

    for placeholder, value in replacements.items():
        if placeholder not in result:
            raise SystemExit(
                f"ERROR: placeholder not found in template: {placeholder}"
            )

        result = result.replace(placeholder, value)

    remaining = [
        p for p in (
            "__ADDRESS1__",
            "__INDEX1__",
            "__ADDRESS2__",
            "__INDEX2__",
            "__ADDRESS3__",
            "__INDEX3__",
        )
        if p in result
    ]

    if remaining:
        raise SystemExit(
            f"ERROR: unresolved placeholders: {remaining}"
        )

    return result


# ============================================================
# WRITE script.sh
# ============================================================

def write_output(content):
    OUTPUT_FILE.write_text(content, encoding="utf-8")

    current_mode = OUTPUT_FILE.stat().st_mode

    OUTPUT_FILE.chmod(
        current_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )


# ============================================================
# SECTION 2
# GITHUB AUTH
# ============================================================

def github_headers():
    if not GITHUB_TOKEN:
        raise SystemExit(
            "ERROR: GITHUB_TOKEN Railway Variable is not set"
        )

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ============================================================
# SECTION 2
# TRIGGER WORKFLOW
# ============================================================

def trigger_workflow():

    if not WORKFLOW_FILE:
        raise SystemExit(
            "ERROR: WORKFLOW_FILE Railway Variable is not set"
        )

    url = (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/"
        f"{WORKFLOW_FILE}/dispatches"
    )

    print()
    print("======================================")
    print(" SECTION 2 - GITHUB WORKFLOW")
    print("======================================")
    print()

    print(f"Repository : {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"Workflow   : {WORKFLOW_FILE}")
    print(f"Ref        : {GITHUB_REF}")
    print("GitHub Token: FOUND")
    print()

    response = requests.post(
        url,
        headers=github_headers(),
        json={
            "ref": GITHUB_REF
        },
        timeout=30,
    )

    if response.status_code not in (201, 204):
        raise SystemExit(
            "ERROR: workflow dispatch failed\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text[:500]}"
        )

    print("Workflow dispatch: SUCCESS")
    print()


# ============================================================
# SECTION 2
# FIND NEWEST WORKFLOW RUN
# ============================================================

def find_latest_run():

    url = (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/"
        f"{WORKFLOW_FILE}/runs"
    )

    response = requests.get(
        url,
        headers=github_headers(),
        params={
            "per_page": 10
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise SystemExit(
            "ERROR: could not retrieve workflow runs\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text[:500]}"
        )

    data = response.json()
    runs = data.get("workflow_runs", [])

    if not runs:
        raise SystemExit(
            "ERROR: no workflow runs found"
        )

    run = runs[0]

    run_id = run.get("id")

    if not run_id:
        raise SystemExit(
            "ERROR: workflow run ID was not found"
        )

    print(f"Workflow Run ID: {run_id}")

    return run_id


# ============================================================
# SECTION 2
# WAIT 60 SECONDS
# ============================================================

def wait_60_seconds():

    print()
    print("Waiting 60 seconds for workflow logs...")
    print()

    for remaining in range(60, 0, -1):

        if remaining % 10 == 0 or remaining <= 5:
            print(f"  {remaining} seconds remaining...")

        time.sleep(1)

    print()
    print("60 seconds completed.")
    print()


# ============================================================
# SECTION 2
# GET WORKFLOW LOGS
# ============================================================

def get_workflow_logs(run_id):

    url = (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/"
        f"{run_id}/logs"
    )

    response = requests.get(
        url,
        headers=github_headers(),
        allow_redirects=True,
        timeout=60,
    )

    if response.status_code != 200:
        raise SystemExit(
            "ERROR: could not retrieve workflow logs\n"
            f"HTTP: {response.status_code}"
        )

    content_type = response.headers.get(
        "content-type",
        ""
    ).lower()

    print(
        f"Workflow logs retrieved "
        f"(content-type: {content_type})"
    )

    return response.content


# ============================================================
# SECTION 2
# SEARCH LOGS
# ============================================================

def find_endpoint_and_token(log_bytes):

    # GitHub returns a ZIP archive from the run-logs endpoint.
    # We inspect the archive without executing anything.

    import io
    import zipfile

    try:
        archive = zipfile.ZipFile(
            io.BytesIO(log_bytes)
        )
    except zipfile.BadZipFile:
        raise SystemExit(
            "ERROR: GitHub logs response was not a valid ZIP archive"
        )

    combined = []

    for name in archive.namelist():

        try:
            data = archive.read(name)
            text = data.decode(
                "utf-8",
                errors="replace"
            )

            combined.append(
                f"\n===== {name} =====\n{text}"
            )

        except Exception:
            continue

    logs = "\n".join(combined)

    if not logs.strip():
        raise SystemExit(
            "ERROR: workflow logs are empty"
        )

    # --------------------------------------------------------
    # Prefer the section containing:
    # REAL PTY TERMINAL ONLINE
    # --------------------------------------------------------

    marker = "REAL PTY TERMINAL ONLINE"

    section = logs

    marker_pos = logs.find(marker)

    if marker_pos >= 0:
        section = logs[
            marker_pos:
            marker_pos + 20000
        ]

    # --------------------------------------------------------
    # Find API endpoint
    # --------------------------------------------------------

    endpoint_match = re.search(
        r"API:\s*(https://[^\s]+/command)",
        section,
        re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Find TOKEN line
    # --------------------------------------------------------

    token_match = re.search(
        r"(?m)^TOKEN:\s*([A-Za-z0-9_-]{20,})\s*$",
        section,
    )

    endpoint = (
        endpoint_match.group(1)
        if endpoint_match
        else None
    )

    token_found = bool(token_match)

    print()
    print("======================================")
    print(" LOG SEARCH RESULT")
    print("======================================")
    print()

    if endpoint:
        print("Endpoint: FOUND")
        print(f"Endpoint URL: {endpoint}")
    else:
        print("Endpoint: NOT FOUND")

    if token_found:
        print("Workflow Token: FOUND")
        print("Workflow Token: [REDACTED]")
    else:
        print("Workflow Token: NOT FOUND")

    print()

    if endpoint and token_found:
        print("STATUS: SUCCESS")
        print()
        print(
            "Endpoint and Token were found in "
            "the workflow logs."
        )

        print()
        print(
            "No curl command was executed."
        )
        print(
            "No remote command was executed."
        )
        print(
            "script.sh was not executed."
        )

        return True

    print("STATUS: FAILED")
    return False


# ============================================================
# SECTION 2 MAIN
# ============================================================

def section_two():

    # Check credentials before doing the API work.
    if not GITHUB_TOKEN:
        raise SystemExit(
            "ERROR: GITHUB_TOKEN is not set in Railway Variables"
        )

    if not WORKFLOW_FILE:
        raise SystemExit(
            "ERROR: WORKFLOW_FILE is not set in Railway Variables"
        )

    trigger_workflow()

    # The workflow stays running, so we do NOT wait for completion.
    run_id = find_latest_run()

    wait_60_seconds()

    logs = get_workflow_logs(run_id)

    success = find_endpoint_and_token(logs)

    if not success:
        raise SystemExit(
            "ERROR: Endpoint/Token could not be found "
            "in the workflow logs."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("======================================")
    print(" FIRST BATCH GENERATOR")
    print("======================================")
    print()

    # --------------------------------------------------------
    # SECTION 1
    # --------------------------------------------------------

    records = read_records()
    print(f"Loaded records: {len(records)}")

    template = read_template()
    print(f"Loaded template: {TEMPLATE_FILE.name}")
    print()

    first_batch = records[:3]

    print("First batch:")

    for n, item in enumerate(first_batch, start=1):
        print(f"  TARGET{n}")
        print(f"    index:   {item['index']}")
        print(f"    address: {item['address']}")
        print()

    script = build_first_batch(
        template,
        records
    )

    write_output(script)

    if not OUTPUT_FILE.exists():
        raise SystemExit(
            "ERROR: script.sh was not created"
        )

    if OUTPUT_FILE.stat().st_size == 0:
        raise SystemExit(
            "ERROR: script.sh is empty"
        )

    print("======================================")
    print("GENERATED FILE")
    print("======================================")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Size:   {OUTPUT_FILE.stat().st_size} bytes")
    print()

    print("======================================")
    print("GENERATED TARGETS")
    print("======================================")
    print()

    for n, item in enumerate(first_batch, start=1):
        print(f"ADDRESS{n} = {item['address']}")
        print(f"INDEX{n}   = {item['index']}")
        print()

    print("======================================")
    print("SECTION 1 COMPLETE")
    print("======================================")
    print()

    # --------------------------------------------------------
    # SECTION 2
    # --------------------------------------------------------

    section_two()

    print()
    print("======================================")
    print(" ALL TEST STEPS COMPLETE")
    print("======================================")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
