from pathlib import Path
import os
import stat
import time
import re
import sys
import base64
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
# GITHUB CONFIG
# ============================================================

GITHUB_OWNER = "kingking000p"
GITHUB_REPO = "H"
GITHUB_REF = "main"

WORKFLOW_FILE = os.environ.get(
    "WORKFLOW_FILE",
    "main.yml"
)

# توکن اصلی برای اجرا و کنسل کردن workflow
GITHUB_TOKEN = os.environ.get(
    "GITHUB_TOKEN"
)

# توکن جدید فقط برای حذف addresses.txt
GG_TOKEN = os.environ.get(
    "GG_TOKEN"
)

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"

# ============================================================
# SECTION 2 TIMING
# ============================================================

INITIAL_WAIT_SECONDS = 60

LOG_FILE_PATH = "logs.txt"

LOG_RETRY_COUNT = 12
LOG_RETRY_DELAY = 5


# ============================================================
# HELPERS
# ============================================================

def fail(message: str):
    print()
    print("ERROR:", message)
    print()
    sys.exit(1)


def github_headers(token=None):
    """ساخت هدر برای GitHub API با توکن دلخواه"""
    if token is None:
        token = GITHUB_TOKEN
    
    if not token:
        fail(
            "GitHub token is not set"
        )

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


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
    fail(
        f"Missing file: {ADDRESSES_FILE}"
    )

if not TEMPLATE_FILE.exists():
    fail(
        f"Missing file: {TEMPLATE_FILE}"
    )


# ------------------------------------------------------------
# Load addresses.txt
# ------------------------------------------------------------

raw_lines = ADDRESSES_FILE.read_text(
    encoding="utf-8"
).splitlines()

records = []

for line_no, raw in enumerate(
    raw_lines,
    start=1
):
    line = raw.strip()

    if not line:
        continue

    if ":" not in line:
        fail(
            f"Invalid addresses.txt format at line "
            f"{line_no}: {raw}"
        )

    index_text, address = line.split(
        ":",
        1
    )

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

    records.append({
        "index": int(index_text),
        "address": address,
    })


print(
    f"Loaded records: {len(records)}"
)


if len(records) < BATCH_SIZE:
    fail(
        f"Need at least {BATCH_SIZE} records, "
        f"found {len(records)}"
    )


# ------------------------------------------------------------
# Load template
# ------------------------------------------------------------

template = TEMPLATE_FILE.read_text(
    encoding="utf-8"
)

print(
    "Loaded template: template.sh"
)


# ------------------------------------------------------------
# Verify placeholders
# ------------------------------------------------------------

required_placeholders = [
    "__ADDRESS1__",
    "__INDEX1__",
    "__ADDRESS2__",
    "__INDEX2__",
    "__ADDRESS3__",
    "__INDEX3__",
]

for placeholder in required_placeholders:
    if placeholder not in template:
        fail(
            f"Missing placeholder: {placeholder}"
        )


# ------------------------------------------------------------
# First 3 records
# ------------------------------------------------------------

batch = records[:BATCH_SIZE]

if len(batch) != 3:
    fail(
        "Could not create a complete batch of 3 records"
    )


print("First batch:")

for pos, item in enumerate(
    batch,
    start=1
):
    print(
        f"  TARGET{pos}"
    )

    print(
        f"    index:   {item['index']}"
    )

    print(
        f"    address: {item['address']}"
    )


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

print(
    f"Output: {OUTPUT_FILE}"
)

print(
    f"Size:   {OUTPUT_FILE.stat().st_size} bytes"
)


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


print(
    f"Repository : {GITHUB_OWNER}/{GITHUB_REPO}"
)

print(
    f"Workflow   : {WORKFLOW_FILE}"
)

print(
    f"Ref        : {GITHUB_REF}"
)


if not GITHUB_TOKEN:
    fail(
        "GITHUB_TOKEN is missing from Railway Variables"
    )


print(
    "GitHub Token: FOUND"
)


# ============================================================
# 2A. TRIGGER WORKFLOW
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
        headers=github_headers(),  # از توکن اصلی استفاده می‌کنه
        json=dispatch_payload,
        timeout=30,
    )

except requests.RequestException as exc:

    fail(
        f"Workflow dispatch request failed: {exc}"
    )


if dispatch_response.status_code not in (
    200,
    204,
):
    fail(
        "Workflow dispatch failed\n"
        f"HTTP: {dispatch_response.status_code}\n"
        f"Response: {dispatch_response.text[:1000]}"
    )


print(
    "Workflow dispatch: SUCCESS"
)


# ============================================================
# 2B. GET RUN ID
# ============================================================

run_id = None


if dispatch_response.status_code == 200:

    try:

        dispatch_json = (
            dispatch_response.json()
        )

    except ValueError:

        fail(
            "GitHub returned HTTP 200 "
            "but response was not JSON"
        )

    run_id = dispatch_json.get(
        "workflow_run_id"
    )

    if run_id:

        print(
            f"Workflow Run ID: {run_id}"
        )

    else:

        print(
            "Workflow Run ID: not returned"
        )


else:

    # --------------------------------------------------------
    # Fallback for HTTP 204
    # --------------------------------------------------------

    print(
        "Dispatch returned 204."
    )

    print(
        "Finding newest workflow run..."
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
                headers=github_headers(),  # از توکن اصلی استفاده می‌کنه
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

                runs_json = (
                    runs_response.json()
                )

            except ValueError:

                time.sleep(2)
                continue


            workflow_runs = (
                runs_json.get(
                    "workflow_runs",
                    []
                )
            )


            if workflow_runs:

                run_id = (
                    workflow_runs[0].get(
                        "id"
                    )
                )

                if run_id:
                    break


        time.sleep(2)


    if run_id:

        print(
            f"Workflow Run ID: {run_id}"
        )

    else:

        print(
            "Workflow Run ID: not found"
        )


# ============================================================
# 2C. WAIT 60 SECONDS
# ============================================================

print(
    "Waiting 60 seconds for logs.txt..."
)


remaining = INITIAL_WAIT_SECONDS


while remaining > 0:

    print(
        f"  {remaining} seconds remaining..."
    )

    sleep_for = min(
        10,
        remaining
    )

    time.sleep(
        sleep_for
    )

    remaining -= sleep_for


print(
    "60 seconds completed."
)


# ============================================================
# 2D. READ logs.txt FROM GITHUB REPOSITORY
# ============================================================

print("======================================")
print(" READING logs.txt")
print("======================================")


logs_url = (
    f"{GITHUB_API}/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}/contents/"
    f"{LOG_FILE_PATH}"
)


logs_json = None


for attempt in range(
    1,
    LOG_RETRY_COUNT + 1
):

    print(
        f"Checking logs.txt "
        f"(attempt {attempt}/{LOG_RETRY_COUNT})..."
    )


    try:

        logs_response = requests.get(
            logs_url,
            headers=github_headers(),  # از توکن اصلی استفاده می‌کنه
            params={
                "ref": GITHUB_REF
            },
            timeout=30,
        )

    except requests.RequestException as exc:

        print(
            f"Request error: {exc}"
        )

        if attempt < LOG_RETRY_COUNT:

            time.sleep(
                LOG_RETRY_DELAY
            )

        continue


    if logs_response.status_code == 200:

        try:

            logs_json = (
                logs_response.json()
            )

        except ValueError:

            print(
                "Invalid JSON response."
            )

            if attempt < LOG_RETRY_COUNT:

                time.sleep(
                    LOG_RETRY_DELAY
                )

            continue

        break


    if logs_response.status_code == 404:

        print(
            "logs.txt not found yet."
        )

    else:

        print(
            f"GitHub HTTP "
            f"{logs_response.status_code}"
        )

        print(
            logs_response.text[:500]
        )


    if attempt < LOG_RETRY_COUNT:

        time.sleep(
            LOG_RETRY_DELAY
        )


if logs_json is None:

    fail(
        "Could not retrieve logs.txt"
    )


# ============================================================
# 2E. DECODE logs.txt
# ============================================================

if logs_json.get("type") != "file":

    fail(
        "logs.txt is not a regular file"
    )


encoded_content = logs_json.get(
    "content"
)


if not encoded_content:

    fail(
        "logs.txt has no content"
    )


try:

    logs_text = base64.b64decode(
        encoded_content
    ).decode(
        "utf-8",
        errors="replace"
    )

except Exception as exc:

    fail(
        f"Could not decode logs.txt: {exc}"
    )


print(
    f"logs.txt loaded: "
    f"{len(logs_text)} characters"
)


# ============================================================
# 2F. FIND REMOTE_URL
# ============================================================

remote_url_match = re.search(
    r"(?m)^\s*REMOTE_URL\s*=\s*(https://[^\s]+)\s*$",
    logs_text
)


# ============================================================
# 2G. FIND API_TOKEN
# ============================================================

api_token_match = re.search(
    r"(?m)^\s*API_TOKEN\s*=\s*([A-Za-z0-9_-]{20,})\s*$",
    logs_text
)


print("======================================")
print(" LOG SEARCH RESULTS")
print("======================================")


# ------------------------------------------------------------
# Remote URL
# ------------------------------------------------------------

if remote_url_match:

    remote_url = (
        remote_url_match.group(1)
        .strip()
    )

    endpoint = (
        remote_url.rstrip("/")
        + "/command"
    )

    print(
        "Endpoint: FOUND"
    )

    print(
        f"Endpoint URL: {endpoint}"
    )

else:

    remote_url = None
    endpoint = None

    print(
        "Endpoint: NOT FOUND"
    )


# ------------------------------------------------------------
# Token
# ------------------------------------------------------------

if api_token_match:
    token_value = api_token_match.group(1).strip()
    print(
        "Token: FOUND"
    )
else:
    token_value = None
    print(
        "Token: NOT FOUND"
    )


# ============================================================
# 2H. EXECUTE BOTH REQUESTS (via requests)
# ============================================================

if endpoint and token_value:

    print("======================================")
    print(" EXECUTING STEP 1: SEND SCRIPT")
    print("======================================")

    try:
        with open("script.sh", "rb") as f:
            script_bytes = f.read()
        b64_data = base64.b64encode(script_bytes).decode('ascii')
    except Exception as e:
        print(f"ERROR: Could not read/encode script.sh: {e}")
        sys.exit(1)

    payload1 = {
        "command": f"echo '{b64_data}' > /tmp/script.b64"
    }

    try:
        response1 = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token_value}",
                "Content-Type": "application/json"
            },
            json=payload1,
            timeout=60
        )
    except requests.RequestException as e:
        print(f"ERROR: Step 1 request failed: {e}")
        sys.exit(1)

    print()
    print("=== STEP 1 RESULT ===")
    print(f"Status code: {response1.status_code}")
    if response1.text:
        print("Response:")
        print(response1.text.strip())
    else:
        print("Response: (empty)")
    print("=====================")
    print()

    print("======================================")
    print(" EXECUTING STEP 2: RUN SCRIPT")
    print("======================================")

    payload2 = {
        "command": "base64 -d /tmp/script.b64 | bash"
    }

    try:
        response2 = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token_value}",
                "Content-Type": "application/json"
            },
            json=payload2,
            timeout=600
        )
    except requests.RequestException as e:
        print(f"ERROR: Step 2 request failed: {e}")
        sys.exit(1)

    print()
    print("=== STEP 2 RESULT ===")
    print(f"Status code: {response2.status_code}")
    if response2.text:
        print("Response:")
        print(response2.text.strip())
    else:
        print("Response: (empty)")
    print("=====================")
    print()

    print("======================================")
    print(" SUMMARY OF REQUESTS SENT")
    print("======================================")
    print("Step 1 (send script):")
    print(f"  POST {endpoint}")
    print(f"  Authorization: Bearer {token_value}")
    print(f"  Payload: {payload1}")
    print()
    print("Step 2 (run script):")
    print(f"  POST {endpoint}")
    print(f"  Authorization: Bearer {token_value}")
    print(f"  Payload: {payload2}")
    print("======================================")

else:

    print("======================================")
    print(" SECTION 2 FAILED")
    print("======================================")

    if not endpoint:
        print("Reason: REMOTE_URL was not found.")
    if not token_value:
        print("Reason: API_TOKEN was not found.")


# ============================================================
# 2I. DELETE logs.txt FROM GITHUB (با توکن اصلی)
# ============================================================

if endpoint and token_value:

    print("======================================")
    print(" DELETING logs.txt")
    print("======================================")

    file_sha = logs_json.get("sha")

    if not file_sha:
        print("WARNING: logs.txt SHA not found.")
    else:
        delete_payload = {
            "message": "Delete temporary logs.txt",
            "sha": file_sha,
            "branch": GITHUB_REF,
        }

        try:
            delete_response = requests.delete(
                logs_url,
                headers=github_headers(),  # از توکن اصلی استفاده می‌کنه
                json=delete_payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            print(f"WARNING: Could not delete logs.txt: {exc}")
        else:
            if delete_response.status_code == 200:
                print("logs.txt deleted successfully.")
            else:
                print("WARNING: Could not delete logs.txt.")
                print(f"HTTP: {delete_response.status_code}")

else:

    print("======================================")
    print(" logs.txt KEPT FOR DEBUGGING")
    print("======================================")
    print("Because Endpoint and Token were not both found,")
    print("logs.txt was NOT deleted.")


# ============================================================
# 2J. CANCEL SERVER (SEND CANCEL COMMAND)
# ============================================================

if endpoint and token_value:
    print("======================================")
    print(" CANCELLING SERVER")
    print("======================================")

    cancel_payload = {
        "command": "cancel"
    }

    try:
        cancel_response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token_value}",
                "Content-Type": "application/json"
            },
            json=cancel_payload,
            timeout=60
        )
    except requests.RequestException as exc:
        print(f"WARNING: Could not cancel server: {exc}")
    else:
        print(f"Cancel server status code: {cancel_response.status_code}")
        if cancel_response.text:
            print("Cancel server response:")
            print(cancel_response.text.strip())
        else:
            print("Cancel server response: (empty)")
else:
    print("Cannot cancel server: endpoint or token missing.")


# ============================================================
# 2K. CANCEL GITHUB WORKFLOW RUN (با توکن اصلی)
# ============================================================

if run_id:
    print("======================================")
    print(" CANCELLING GITHUB WORKFLOW RUN")
    print("======================================")

    cancel_url = (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/"
        f"{run_id}/cancel"
    )

    try:
        cancel_response = requests.post(
            cancel_url,
            headers=github_headers(),  # از توکن اصلی استفاده می‌کنه
            timeout=30
        )
    except requests.RequestException as exc:
        print(f"WARNING: Could not cancel workflow: {exc}")
    else:
        if cancel_response.status_code == 202:
            print(f"Workflow run {run_id} cancelled successfully.")
        else:
            print(f"WARNING: Could not cancel workflow run {run_id}.")
            print(f"HTTP: {cancel_response.status_code}")
            print(f"Response: {cancel_response.text[:500]}")
else:
    print("No run_id available to cancel.")


# ============================================================
# 2L. REMOVE USED ADDRESSES FROM GITHUB (با GG_TOKEN)
# ============================================================

print("======================================")
print(" REMOVING USED ADDRESSES FROM GITHUB")
print("======================================")

# چک کردن وجود GG_TOKEN
if not GG_TOKEN:
    print("WARNING: GG_TOKEN is not set. Skipping GitHub addresses update.")
else:
    # 1. آدرس‌های باقی‌مانده رو به صورت متن آماده کن
    remaining_records = records[BATCH_SIZE:]
    new_content = ""
    for rec in remaining_records:
        new_content += f"{rec['index']}:{rec['address']}\n"

    # 2. encode به base64
    new_content_b64 = base64.b64encode(new_content.encode('utf-8')).decode('ascii')

    # 3. دریافت SHA فایل فعلی (برای آپدیت) با GG_TOKEN
    file_sha = None
    addresses_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/addresses.txt"
    try:
        print(f"Fetching current addresses.txt from: {addresses_url}")
        print("Using GG_TOKEN for this operation...")
        get_file_resp = requests.get(
            addresses_url,
            headers=github_headers(GG_TOKEN),  # از توکن جدید استفاده می‌کنه
            params={"ref": GITHUB_REF},
            timeout=30
        )
        if get_file_resp.status_code == 200:
            file_sha = get_file_resp.json().get("sha")
            print(f"✅ Got addresses.txt SHA: {file_sha[:8]}...")
        else:
            print(f"WARNING: Could not get addresses.txt from GitHub. HTTP: {get_file_resp.status_code}")
            print(f"Response: {get_file_resp.text[:200]}")
    except Exception as e:
        print(f"WARNING: Could not get file SHA: {e}")

    if file_sha:
        # 4. آپدیت فایل در GitHub با GG_TOKEN
        update_payload = {
            "message": f"Remove used addresses (batch of {BATCH_SIZE})",
            "content": new_content_b64,
            "sha": file_sha,
            "branch": GITHUB_REF,
        }
        try:
            update_response = requests.put(
                addresses_url,
                headers=github_headers(GG_TOKEN),  # از توکن جدید استفاده می‌کنه
                json=update_payload,
                timeout=30
            )
            if update_response.status_code in (200, 201):
                print(f"✅ Removed {BATCH_SIZE} used addresses from GitHub.")
                print(f"Remaining addresses: {len(remaining_records)}")
            else:
                print(f"WARNING: Could not update addresses.txt in GitHub.")
                print(f"HTTP: {update_response.status_code}")
                print(f"Response: {update_response.text[:500]}")
        except Exception as e:
            print(f"WARNING: Could not update addresses.txt: {e}")
    else:
        print("WARNING: Could not get SHA for addresses.txt, skipping GitHub update.")

# همچنین فایل محلی را هم آپدیت می‌کنیم (برای هماهنگی)
remaining_records = records[BATCH_SIZE:]
if remaining_records:
    with open(ADDRESSES_FILE, "w", encoding="utf-8") as f:
        for rec in remaining_records:
            f.write(f"{rec['index']}:{rec['address']}\n")
    print(f"Local addresses.txt updated. Remaining: {len(remaining_records)}")
else:
    with open(ADDRESSES_FILE, "w", encoding="utf-8") as f:
        f.write("")
    print("All addresses have been used. Local addresses.txt is now empty.")


# ============================================================
# FINAL
# ============================================================

print("======================================")

if endpoint and token_value:
    print("SECTION 2 COMPLETE")
else:
    print("SECTION 2 FINISHED WITHOUT MATCH")

print("======================================")
