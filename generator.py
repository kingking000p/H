from pathlib import Path
import os
import stat
import time
import re
import sys
import base64
import requests
import datetime
import json


# ============================================================
# LOGGING SETUP
# ============================================================

def log_info(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [INFO] {message}")
    sys.stdout.flush()


def log_error(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [ERROR] {message}")
    sys.stdout.flush()


def log_debug(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [DEBUG] {message}")
    sys.stdout.flush()


def log_separator(char="=", length=38):
    log_info(char * length)


def log_warning(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [WARNING] {message}")
    sys.stdout.flush()


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

GITHUB_OWNER = "forgotenmywin"
GITHUB_REPO = "K"
GITHUB_REF = "main"

WORKFLOW_FILE = os.environ.get(
    "WORKFLOW_FILE",
    "main.yml"
)

GITHUB_TOKEN = os.environ.get(
    "GITHUB_TOKEN"
)

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
    log_error(message)
    sys.exit(1)


def github_headers():
    if not GITHUB_TOKEN:
        fail("GITHUB_TOKEN is not set")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    return headers


def delete_used_addresses_from_github(addresses_to_remove):
    log_separator()
    log_info("DELETING USED ADDRESSES FROM GITHUB")
    log_separator()
    
    addresses_url = "https://api.github.com/repos/kingking000p/H/contents/addresses.txt"
    
    if not GG_TOKEN:
        log_error("GG_TOKEN is not set, skipping deletion")
        return False
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GG_TOKEN}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    
    try:
        response = requests.get(addresses_url, headers=headers)
        if response.status_code != 200:
            log_error(f"Could not fetch addresses.txt - {response.status_code}")
            return False
            
        file_data = response.json()
        current_content = base64.b64decode(file_data["content"]).decode("utf-8")
        file_sha = file_data["sha"]
        
    except Exception as e:
        log_error(f"Reading file error: {e}")
        return False
    
    lines = current_content.splitlines()
    new_lines = []
    removed_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        should_remove = False
        for addr in addresses_to_remove:
            if addr in line:
                should_remove = True
                removed_count += 1
                break
                
        if not should_remove:
            new_lines.append(line)
    
    if removed_count == 0:
        log_info("No matching addresses found to remove")
        return True
    
    new_content = "\n".join(new_lines)
    encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("ascii")
    
    payload = {
        "message": f"Removed {removed_count} used addresses",
        "content": encoded_content,
        "sha": file_sha,
        "branch": "main"
    }
    
    try:
        response = requests.put(addresses_url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            log_info(f"✅ Removed {removed_count} addresses from GitHub")
            log_info(f"   Remaining addresses: {len(new_lines)}")
            return True
        else:
            log_error(f"Uploading failed: {response.status_code}")
            return False
    except Exception as e:
        log_error(f"Upload error: {e}")
        return False


def cancel_workflow(run_id):
    log_separator()
    log_info("CANCELLING WORKFLOW (SHUTTING DOWN SERVER)")
    log_separator()
    
    if not run_id:
        log_error("No run_id provided, cannot cancel workflow")
        return False
    
    if not GITHUB_TOKEN:
        log_error("GITHUB_TOKEN is not set, cannot cancel workflow")
        return False
    
    cancel_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}/cancel"
    
    log_info(f"Cancelling workflow run: {run_id}")
    
    try:
        response = requests.post(
            cancel_url,
            headers=github_headers(),
            timeout=30
        )
        
        if response.status_code == 202:
            log_info("✅ Workflow cancelled successfully! Server is shutting down.")
            return True
        elif response.status_code == 409:
            log_info("⚠️ Workflow already completed or cannot be cancelled.")
            return True
        else:
            log_error(f"Failed to cancel workflow: {response.status_code}")
            return False
            
    except requests.RequestException as e:
        log_error(f"Cancel request failed: {e}")
        return False


def check_if_script_successful(response_text):
    """
    بررسی میکند که اسکریپت با موفقیت اجرا شده یا خطای faucet budget خورده
    """
    if not response_text:
        return False, "empty_response"
    
    response_lower = response_text.lower()
    
    # بررسی خطای faucet budget
    if "faucet hourly budget used up" in response_lower:
        return False, "faucet_budget"
    
    if "try again shortly" in response_lower:
        return False, "faucet_budget"
    
    # بررسی موفقیت - اگر حداقل یکی از اینا باشه یعنی کار کرده
    success_indicators = [
        "claim successful",
        "receive successful", 
        "block hash",
        "balance:",
        "total:",
        "done"
    ]
    
    for indicator in success_indicators:
        if indicator in response_lower:
            return True, "success"
    
    # اگر هیچکدوم نبود
    return False, "unknown"


# ============================================================
# SECTION 1
# ============================================================

log_separator()
log_info("FIRST BATCH GENERATOR")
log_separator()

if not ADDRESSES_FILE.exists():
    fail(f"Missing file: {ADDRESSES_FILE}")

if not TEMPLATE_FILE.exists():
    fail(f"Missing file: {TEMPLATE_FILE}")

log_info("✅ All required files found")

# Load addresses
raw_lines = ADDRESSES_FILE.read_text(encoding="utf-8").splitlines()
records = []

for line_no, raw in enumerate(raw_lines, start=1):
    line = raw.strip()
    if not line:
        continue
    if ":" not in line:
        fail(f"Invalid addresses.txt format at line {line_no}: {raw}")
    index_text, address = line.split(":", 1)
    index_text = index_text.strip()
    address = address.strip()
    if not index_text.isdigit():
        fail(f"Invalid index at line {line_no}: {index_text}")
    if not address:
        fail(f"Empty address at line {line_no}")
    records.append({"index": int(index_text), "address": address})

log_info(f"Loaded records: {len(records)}")

if len(records) < BATCH_SIZE:
    fail(f"Need at least {BATCH_SIZE} records, found {len(records)}")

# Load template
template = TEMPLATE_FILE.read_text(encoding="utf-8")
log_info("Loaded template: template.sh")

# Verify placeholders
required_placeholders = ["__ADDRESS1__", "__INDEX1__", "__ADDRESS2__", "__INDEX2__", "__ADDRESS3__", "__INDEX3__"]
for placeholder in required_placeholders:
    if placeholder not in template:
        fail(f"Missing placeholder: {placeholder}")

# First 3 records
batch = records[:BATCH_SIZE]
if len(batch) != 3:
    fail("Could not create a complete batch of 3 records")

log_info("First batch:")
for pos, item in enumerate(batch, start=1):
    log_info(f"  TARGET{pos}")
    log_info(f"    index:   {item['index']}")
    log_info(f"    address: {item['address']}")

# Replace placeholders
generated = template
generated = generated.replace("__ADDRESS1__", batch[0]["address"])
generated = generated.replace("__INDEX1__", str(batch[0]["index"]))
generated = generated.replace("__ADDRESS2__", batch[1]["address"])
generated = generated.replace("__INDEX2__", str(batch[1]["index"]))
generated = generated.replace("__ADDRESS3__", batch[2]["address"])
generated = generated.replace("__INDEX3__", str(batch[2]["index"]))

# Write generated script
OUTPUT_FILE.write_text(generated, encoding="utf-8")
OUTPUT_FILE.chmod(OUTPUT_FILE.stat().st_mode | stat.S_IXUSR)

log_separator()
log_info("GENERATED FILE")
log_separator()
log_info(f"Output: {OUTPUT_FILE}")
log_info(f"Size:   {OUTPUT_FILE.stat().st_size} bytes")

log_separator()
log_info("GENERATED TARGETS")
log_separator()
log_info(f"ADDRESS1 = {batch[0]['address']}")
log_info(f"INDEX1   = {batch[0]['index']}")
log_info(f"ADDRESS2 = {batch[1]['address']}")
log_info(f"INDEX2   = {batch[1]['index']}")
log_info(f"ADDRESS3 = {batch[2]['address']}")
log_info(f"INDEX3   = {batch[2]['index']}")

log_separator()
log_info("SECTION 1 COMPLETE")
log_separator()


# ============================================================
# SECTION 2
# ============================================================

log_separator()
log_info("SECTION 2 - GITHUB WORKFLOW")
log_separator()

log_info(f"Repository : {GITHUB_OWNER}/{GITHUB_REPO}")
log_info(f"Workflow   : {WORKFLOW_FILE}")
log_info(f"Ref        : {GITHUB_REF}")

if not GITHUB_TOKEN:
    fail("GITHUB_TOKEN is missing from Railway Variables")

log_info("GitHub Token: FOUND")


# ============================================================
# 2A. TRIGGER WORKFLOW
# ============================================================

log_info("Triggering GitHub workflow...")

dispatch_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"

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
    fail(f"Workflow dispatch failed\nHTTP: {dispatch_response.status_code}\nResponse: {dispatch_response.text[:1000]}")

log_info("Workflow dispatch: SUCCESS")


# ============================================================
# 2B. GET RUN ID
# ============================================================

run_id = None

if dispatch_response.status_code == 200:
    try:
        dispatch_json = dispatch_response.json()
    except ValueError:
        fail("GitHub returned HTTP 200 but response was not JSON")

    run_id = dispatch_json.get("workflow_run_id")
    if run_id:
        log_info(f"Workflow Run ID: {run_id}")
    else:
        log_error("Workflow Run ID: not returned")
else:
    log_info("Dispatch returned 204. Finding newest workflow run...")
    runs_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
    deadline = time.time() + 30

    while time.time() < deadline:
        try:
            runs_response = requests.get(
                runs_url,
                headers=github_headers(),
                params={"branch": GITHUB_REF, "per_page": 10},
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

            workflow_runs = runs_json.get("workflow_runs", [])
            if workflow_runs:
                run_id = workflow_runs[0].get("id")
                if run_id:
                    break
        time.sleep(2)

    if run_id:
        log_info(f"Workflow Run ID: {run_id}")
    else:
        log_error("Workflow Run ID: not found")


# ============================================================
# 2C. WAIT 60 SECONDS
# ============================================================

log_info("Waiting 60 seconds for logs.txt...")
remaining = INITIAL_WAIT_SECONDS

while remaining > 0:
    log_info(f"  {remaining} seconds remaining...")
    sleep_for = min(10, remaining)
    time.sleep(sleep_for)
    remaining -= sleep_for

log_info("60 seconds completed.")


# ============================================================
# 2D. READ logs.txt FROM GITHUB REPOSITORY
# ============================================================

log_separator()
log_info("READING logs.txt")
log_separator()

logs_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{LOG_FILE_PATH}"
logs_json = None

for attempt in range(1, LOG_RETRY_COUNT + 1):
    log_info(f"Checking logs.txt (attempt {attempt}/{LOG_RETRY_COUNT})...")
    try:
        logs_response = requests.get(
            logs_url,
            headers=github_headers(),
            params={"ref": GITHUB_REF},
            timeout=30,
        )
    except requests.RequestException as exc:
        log_error(f"Request error: {exc}")
        if attempt < LOG_RETRY_COUNT:
            time.sleep(LOG_RETRY_DELAY)
        continue

    if logs_response.status_code == 200:
        try:
            logs_json = logs_response.json()
        except ValueError:
            log_error("Invalid JSON response.")
            if attempt < LOG_RETRY_COUNT:
                time.sleep(LOG_RETRY_DELAY)
            continue
        break

    if logs_response.status_code == 404:
        log_error("logs.txt not found yet.")
    else:
        log_error(f"GitHub HTTP {logs_response.status_code}")

    if attempt < LOG_RETRY_COUNT:
        time.sleep(LOG_RETRY_DELAY)

if logs_json is None:
    fail("Could not retrieve logs.txt")


# ============================================================
# 2E. DECODE logs.txt
# ============================================================

if logs_json.get("type") != "file":
    fail("logs.txt is not a regular file")

encoded_content = logs_json.get("content")
if not encoded_content:
    fail("logs.txt has no content")

try:
    logs_text = base64.b64decode(encoded_content).decode("utf-8", errors="replace")
except Exception as exc:
    fail(f"Could not decode logs.txt: {exc}")

log_info(f"logs.txt loaded: {len(logs_text)} characters")


# ============================================================
# 2F. FIND REMOTE_URL
# ============================================================

remote_url_match = re.search(r"(?m)^\s*REMOTE_URL\s*=\s*(https://[^\s]+)\s*$", logs_text)


# ============================================================
# 2G. FIND API_TOKEN
# ============================================================

api_token_match = re.search(r"(?m)^\s*API_TOKEN\s*=\s*([A-Za-z0-9_-]{20,})\s*$", logs_text)


log_separator()
log_info("LOG SEARCH RESULTS")
log_separator()

if remote_url_match:
    remote_url = remote_url_match.group(1).strip()
    endpoint = remote_url.rstrip("/") + "/command"
    log_info("Endpoint: FOUND")
    log_info(f"Endpoint URL: {endpoint}")
else:
    remote_url = None
    endpoint = None
    log_error("Endpoint: NOT FOUND")

if api_token_match:
    token_value = api_token_match.group(1).strip()
    log_info("Token: FOUND")
else:
    token_value = None
    log_error("Token: NOT FOUND")


# ============================================================
# 2H. EXECUTE BOTH REQUESTS
# ============================================================

script_successful = False
script_status = "unknown"
faucet_budget_error = False
timeout_occurred = False

if endpoint and token_value:

    log_separator()
    log_info("EXECUTING STEP 1: SEND SCRIPT")
    log_separator()

    try:
        with open("script.sh", "rb") as f:
            script_bytes = f.read()
        b64_data = base64.b64encode(script_bytes).decode('ascii')
    except Exception as e:
        log_error(f"Could not read/encode script.sh: {e}")
        sys.exit(1)

    payload1 = {"command": f"echo '{b64_data}' > /tmp/script.b64"}

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
        log_error(f"Step 1 request failed: {e}")
        sys.exit(1)

    log_info("=== STEP 1 RESULT ===")
    log_info(f"Status code: {response1.status_code}")

    log_separator()
    log_info("EXECUTING STEP 2: RUN SCRIPT")
    log_separator()
    log_info("⏱️ Timeout set to 600 seconds (10 minutes)")
    log_info("⏳ Waiting for script execution... (this may take a while)")

    payload2 = {"command": "base64 -d /tmp/script.b64 | bash"}

    start_time = time.time()
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
    except requests.Timeout:
        log_error("⏱️ STEP 2 TIMEOUT! Script took longer than 600 seconds.")
        timeout_occurred = True
        script_successful = False
        script_status = "timeout"
    except requests.RequestException as e:
        log_error(f"Step 2 request failed: {e}")
        script_successful = False
        script_status = "request_failed"
    else:
        elapsed_time = time.time() - start_time
        log_info(f"⏱️ Execution time: {elapsed_time:.2f} seconds")
        
        log_info("=== STEP 2 RESULT ===")
        log_info(f"Status code: {response2.status_code}")
        
        if response2.status_code == 200:
            response_text = response2.text if response2.text else ""
            
            # بررسی موفقیت اسکریپت
            is_success, status = check_if_script_successful(response_text)
            script_successful = is_success
            script_status = status
            
            if is_success:
                log_info("✅ Script executed successfully!")
            elif status == "faucet_budget":
                log_warning("⚠️ Faucet hourly budget used up - addresses will NOT be deleted")
                faucet_budget_error = True
            else:
                log_warning(f"⚠️ Script execution status: {status} - addresses will NOT be deleted")
        else:
            log_error(f"❌ Script execution failed with status code: {response2.status_code}")
            script_successful = False
            script_status = f"http_{response2.status_code}"

else:
    log_separator()
    log_error("SECTION 2 FAILED")
    log_separator()


# ============================================================
# 2I. DELETE logs.txt
# ============================================================

if endpoint and token_value:
    log_separator()
    log_info("DELETING logs.txt")
    log_separator()

    file_sha = logs_json.get("sha")
    if file_sha:
        delete_payload = {
            "message": "Delete temporary logs.txt",
            "sha": file_sha,
            "branch": GITHUB_REF,
        }
        try:
            delete_response = requests.delete(
                logs_url,
                headers=github_headers(),
                json=delete_payload,
                timeout=30,
            )
            if delete_response.status_code == 200:
                log_info("✅ logs.txt deleted successfully.")
            else:
                log_error(f"Could not delete logs.txt: {delete_response.status_code}")
        except requests.RequestException as exc:
            log_error(f"Could not delete logs.txt: {exc}")


# ============================================================
# 2J. DELETE USED ADDRESSES FROM GITHUB (ONLY IF SUCCESSFUL) 🔥
# ============================================================

log_separator()
log_info("CHECKING SCRIPT STATUS BEFORE DELETING ADDRESSES")
log_separator()

log_info(f"Script successful: {script_successful}")
log_info(f"Script status: {script_status}")
log_info(f"Timeout occurred: {timeout_occurred}")
log_info(f"Faucet budget error: {faucet_budget_error}")

# 🔥 شرط اصلی: فقط اگر اسکریپت با موفقیت اجرا شده باشه
if script_successful:
    log_info("✅ Script was successful! Deleting used addresses from GitHub...")
    
    used_addresses = [
        batch[0]["address"],
        batch[1]["address"],
        batch[2]["address"]
    ]
    
    delete_used_addresses_from_github(used_addresses)
    
else:
    log_warning("⚠️ Script was NOT successful! Addresses will NOT be deleted.")
    
    if timeout_occurred:
        log_warning("   Reason: Timeout occurred during script execution")
    elif faucet_budget_error:
        log_warning("   Reason: Faucet hourly budget used up")
    else:
        log_warning(f"   Reason: Script status = {script_status}")


# ============================================================
# 2K. CANCEL WORKFLOW (SHUT DOWN SERVER)
# ============================================================

log_separator()
log_info("SHUTTING DOWN SERVER...")
log_separator()

if run_id and GITHUB_TOKEN:
    cancel_workflow(run_id)
else:
    log_error("Cannot cancel workflow: missing run_id or GITHUB_TOKEN")


# ============================================================
# FINAL
# ============================================================

log_separator()
log_info("✅ ALL DONE!")
log_separator()

log_info(f"Final status:")
log_info(f"  - Script executed: {script_successful}")
log_info(f"  - Script status: {script_status}")
log_info(f"  - Timeout: {timeout_occurred}")
log_info(f"  - Faucet budget error: {faucet_budget_error}")
log_info(f"  - Addresses deleted: {script_successful}")

log_separator()
