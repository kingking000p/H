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
    """چاپ پیام اطلاعات با timestamp"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [INFO] {message}")
    sys.stdout.flush()  # 🔥 فلاش کردن خروجی


def log_error(message):
    """چاپ پیام خطا با timestamp"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [ERROR] {message}")
    sys.stdout.flush()  # 🔥 فلاش کردن خروجی


def log_debug(message):
    """چاپ پیام دیباگ با timestamp"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [DEBUG] {message}")
    sys.stdout.flush()  # 🔥 فلاش کردن خروجی


def log_separator(char="=", length=38):
    """چاپ خط جداکننده"""
    log_info(char * length)


def log_request_details(method, url, headers=None, payload=None, response=None):
    """نمایش جزئیات کامل درخواست و پاسخ"""
    log_debug(f"--- REQUEST DETAILS ---")
    log_debug(f"Method: {method}")
    log_debug(f"URL: {url}")
    if headers:
        # مخفی کردن توکن‌ها
        safe_headers = headers.copy()
        if "Authorization" in safe_headers:
            auth = safe_headers["Authorization"]
            if len(auth) > 20:
                safe_headers["Authorization"] = auth[:15] + "..." + auth[-5:]
        log_debug(f"Headers: {json.dumps(safe_headers, indent=2)}")
    if payload:
        # مخفی کردن اطلاعات حساس در payload
        safe_payload = payload.copy()
        if "command" in safe_payload and len(str(safe_payload["command"])) > 100:
            safe_payload["command"] = str(safe_payload["command"])[:50] + "... (truncated)"
        log_debug(f"Payload: {json.dumps(safe_payload, indent=2)}")
    if response is not None:
        log_debug(f"Response Status: {response.status_code}")
        if response.text and len(response.text) < 500:
            log_debug(f"Response Body: {response.text[:200]}...")
        elif response.text:
            log_debug(f"Response Body: {response.text[:200]}... (truncated)")
    log_debug(f"--- END REQUEST ---")


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

# توکن برای مخزن addresses.txt
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
    log_debug("GitHub headers created successfully")
    return headers


def delete_used_addresses_from_github(addresses_to_remove):
    """
    سه آدرس استفاده شده رو از فایل addresses.txt توی گیت‌هاب حذف می‌کنه
    """
    log_separator()
    log_info("DELETING USED ADDRESSES FROM GITHUB")
    log_separator()
    
    # آدرس فایل توی گیت‌هاب
    addresses_url = "https://api.github.com/repos/kingking000p/H/contents/addresses.txt"
    
    if not GG_TOKEN:
        log_error("GG_TOKEN is not set, skipping deletion")
        return False
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GG_TOKEN}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    
    log_debug(f"Fetching addresses.txt from: {addresses_url}")
    
    # ۱. گرفتن فایل فعلی و SHA اون
    try:
        response = requests.get(addresses_url, headers=headers)
        log_request_details("GET", addresses_url, headers, response=response)
        
        if response.status_code != 200:
            log_error(f"Could not fetch addresses.txt - {response.status_code}")
            return False
            
        file_data = response.json()
        current_content = base64.b64decode(file_data["content"]).decode("utf-8")
        file_sha = file_data["sha"]
        
        log_debug(f"File SHA: {file_sha[:8]}...")
        log_debug(f"Current content length: {len(current_content)} characters")
        
    except Exception as e:
        log_error(f"Reading file error: {e}")
        return False
    
    # ۲. حذف سه آدرس از محتوا
    lines = current_content.splitlines()
    new_lines = []
    removed_count = 0
    
    log_debug(f"Processing {len(lines)} lines...")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # چک می‌کنیم که آیا این خط یکی از آدرس‌های مورد نظره؟
        should_remove = False
        for addr in addresses_to_remove:
            if addr in line:  # آدرس توی خط هست
                should_remove = True
                removed_count += 1
                log_debug(f"Removing address: {addr[:20]}...")
                break
                
        if not should_remove:
            new_lines.append(line)
    
    # اگه چیزی برای حذف نبود
    if removed_count == 0:
        log_info("No matching addresses found to remove")
        return True
    
    # ۳. آپلود فایل جدید
    new_content = "\n".join(new_lines)
    encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("ascii")
    
    log_debug(f"New content length: {len(new_content)} characters")
    log_debug(f"Removed count: {removed_count}")
    
    payload = {
        "message": f"Removed {removed_count} used addresses",
        "content": encoded_content,
        "sha": file_sha,
        "branch": "main"
    }
    
    log_debug(f"Uploading new file to: {addresses_url}")
    
    try:
        response = requests.put(addresses_url, headers=headers, json=payload)
        log_request_details("PUT", addresses_url, headers, payload, response)
        
        if response.status_code in [200, 201]:
            log_info(f"✅ Removed {removed_count} addresses from GitHub")
            log_info(f"   Remaining addresses: {len(new_lines)}")
            return True
        else:
            log_error(f"Uploading failed: {response.status_code}")
            log_error(f"Response: {response.text[:500]}")
            return False
    except Exception as e:
        log_error(f"Upload error: {e}")
        return False


# ============================================================
# SECTION 1
# ============================================================

log_separator()
log_info("FIRST BATCH GENERATOR")
log_separator()


# ------------------------------------------------------------
# Check files
# ------------------------------------------------------------

log_debug(f"Checking files in: {BASE_DIR}")

if not ADDRESSES_FILE.exists():
    fail(f"Missing file: {ADDRESSES_FILE}")

if not TEMPLATE_FILE.exists():
    fail(f"Missing file: {TEMPLATE_FILE}")

log_info(f"✅ All required files found")


# ------------------------------------------------------------
# Load addresses.txt
# ------------------------------------------------------------

log_debug(f"Loading addresses from: {ADDRESSES_FILE}")

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


log_info(f"Loaded records: {len(records)}")


# بررسی می‌کنیم حداقل BATCH_SIZE رکورد وجود داشته باشد
if len(records) < BATCH_SIZE:
    fail(
        f"Need at least {BATCH_SIZE} records, "
        f"found {len(records)}"
    )


# ------------------------------------------------------------
# Load template
# ------------------------------------------------------------

log_debug(f"Loading template from: {TEMPLATE_FILE}")

template = TEMPLATE_FILE.read_text(
    encoding="utf-8"
)

log_info("Loaded template: template.sh")


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

log_debug("All placeholders verified")


# ------------------------------------------------------------
# First 3 records
# ------------------------------------------------------------

batch = records[:BATCH_SIZE]

if len(batch) != 3:
    fail(
        "Could not create a complete batch of 3 records"
    )


log_info("First batch:")

for pos, item in enumerate(
    batch,
    start=1
):
    log_info(f"  TARGET{pos}")
    log_info(f"    index:   {item['index']}")
    log_info(f"    address: {item['address']}")


# ------------------------------------------------------------
# Replace placeholders
# ------------------------------------------------------------

log_debug("Replacing placeholders in template...")

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

log_debug(f"Writing generated script to: {OUTPUT_FILE}")

OUTPUT_FILE.write_text(
    generated,
    encoding="utf-8"
)

OUTPUT_FILE.chmod(
    OUTPUT_FILE.stat().st_mode | stat.S_IXUSR
)


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

dispatch_url = (
    f"{GITHUB_API}/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/"
    f"workflows/{WORKFLOW_FILE}/dispatches"
)


dispatch_payload = {
    "ref": GITHUB_REF,
    "return_run_details": True,
}

log_debug(f"Dispatch URL: {dispatch_url}")
log_debug(f"Payload: {json.dumps(dispatch_payload)}")


try:
    dispatch_response = requests.post(
        dispatch_url,
        headers=github_headers(),
        json=dispatch_payload,
        timeout=30,
    )
    log_request_details("POST", dispatch_url, github_headers(), dispatch_payload, dispatch_response)

except requests.RequestException as exc:
    fail(f"Workflow dispatch request failed: {exc}")


if dispatch_response.status_code not in (200, 204):
    fail(
        "Workflow dispatch failed\n"
        f"HTTP: {dispatch_response.status_code}\n"
        f"Response: {dispatch_response.text[:1000]}"
    )


log_info("Workflow dispatch: SUCCESS")


# ============================================================
# 2B. GET RUN ID
# ============================================================

log_debug("Getting workflow run ID...")

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

    # --------------------------------------------------------
    # Fallback for HTTP 204
    # --------------------------------------------------------

    log_info("Dispatch returned 204. Finding newest workflow run...")

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


logs_url = (
    f"{GITHUB_API}/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}/contents/"
    f"{LOG_FILE_PATH}"
)

log_debug(f"Logs URL: {logs_url}")

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
        log_debug(logs_response.text[:500])

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

log_debug("Searching for REMOTE_URL in logs...")

remote_url_match = re.search(
    r"(?m)^\s*REMOTE_URL\s*=\s*(https://[^\s]+)\s*$",
    logs_text
)


# ============================================================
# 2G. FIND API_TOKEN
# ============================================================

log_debug("Searching for API_TOKEN in logs...")

api_token_match = re.search(
    r"(?m)^\s*API_TOKEN\s*=\s*([A-Za-z0-9_-]{20,})\s*$",
    logs_text
)


log_separator()
log_info("LOG SEARCH RESULTS")
log_separator()


# ------------------------------------------------------------
# Remote URL
# ------------------------------------------------------------

if remote_url_match:

    remote_url = remote_url_match.group(1).strip()

    endpoint = remote_url.rstrip("/") + "/command"

    log_info("Endpoint: FOUND")
    log_info(f"Endpoint URL: {endpoint}")

else:

    remote_url = None
    endpoint = None

    log_error("Endpoint: NOT FOUND")


# ------------------------------------------------------------
# Token
# ------------------------------------------------------------

if api_token_match:
    token_value = api_token_match.group(1).strip()
    log_info("Token: FOUND")
    log_debug(f"Token: {token_value[:10]}...{token_value[-5:]}")
else:
    token_value = None
    log_error("Token: NOT FOUND")


# ============================================================
# 2H. EXECUTE BOTH REQUESTS (via requests)
# ============================================================

if endpoint and token_value:

    log_separator()
    log_info("EXECUTING STEP 1: SEND SCRIPT")
    log_separator()

    # ---- مرحله 1: ارسال script.sh ----
    try:
        with open("script.sh", "rb") as f:
            script_bytes = f.read()
        b64_data = base64.b64encode(script_bytes).decode('ascii')
        log_debug(f"Script encoded: {len(b64_data)} characters")
    except Exception as e:
        log_error(f"Could not read/encode script.sh: {e}")
        sys.exit(1)

    payload1 = {
        "command": f"echo '{b64_data}' > /tmp/script.b64"
    }

    try:
        log_debug(f"Sending script to: {endpoint}")
        response1 = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token_value}",
                "Content-Type": "application/json"
            },
            json=payload1,
            timeout=60
        )
        log_request_details("POST", endpoint, {"Authorization": f"Bearer {token_value[:10]}..."}, payload1, response1)
    except requests.RequestException as e:
        log_error(f"Step 1 request failed: {e}")
        sys.exit(1)

    # گزارش مرحله 1
    log_info("=== STEP 1 RESULT ===")
    log_info(f"Status code: {response1.status_code}")
    if response1.text:
        log_info("Response:")
        log_info(response1.text.strip())
    else:
        log_info("Response: (empty)")
    log_info("=====================")

    # ---- مرحله 2: اجرای اسکریپت (با timeout 600 ثانیه = ۱۰ دقیقه) ----
    log_separator()
    log_info("EXECUTING STEP 2: RUN SCRIPT")
    log_separator()
    log_info("⏱️ Timeout set to 600 seconds (10 minutes)")
    log_info("⏳ Waiting for script execution... (this may take a while)")

    payload2 = {
        "command": "base64 -d /tmp/script.b64 | bash"
    }

    start_time = time.time()

    try:
        response2 = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token_value}",
                "Content-Type": "application/json"
            },
            json=payload2,
            timeout=600  # 🔥 ۱۰ دقیقه
        )
    except requests.RequestException as e:
        log_error(f"Step 2 request failed: {e}")
        sys.exit(1)

    elapsed_time = time.time() - start_time
    log_info(f"⏱️ Execution time: {elapsed_time:.2f} seconds")

    # گزارش مرحله 2
    log_info("=== STEP 2 RESULT ===")
    log_info(f"Status code: {response2.status_code}")
    if response2.text:
        log_info("Response:")
        log_info(response2.text.strip())
    else:
        log_info("Response: (empty)")
    log_info("=====================")

    # ---- چاپ خلاصه‌ی هر دو درخواست ----
    log_separator()
    log_info("SUMMARY OF REQUESTS SENT")
    log_separator()
    log_info("Step 1 (send script):")
    log_info(f"  POST {endpoint}")
    log_info(f"  Authorization: Bearer {token_value[:10]}...{token_value[-5:]}")
    log_info(f"  Payload: {payload1}")
    log_info("")
    log_info("Step 2 (run script):")
    log_info(f"  POST {endpoint}")
    log_info(f"  Authorization: Bearer {token_value[:10]}...{token_value[-5:]}")
    log_info(f"  Payload: {payload2}")
    log_info(f"  Timeout: 600 seconds")
    log_separator()

else:

    log_separator()
    log_error("SECTION 2 FAILED")
    log_separator()

    if not endpoint:
        log_error("Reason: REMOTE_URL was not found.")
    if not token_value:
        log_error("Reason: API_TOKEN was not found.")


# ============================================================
# 2I. DELETE logs.txt ONLY AFTER SUCCESSFUL MATCH
# ============================================================

if endpoint and token_value:

    log_separator()
    log_info("DELETING logs.txt")
    log_separator()

    file_sha = logs_json.get("sha")

    if not file_sha:
        log_error("WARNING: logs.txt SHA not found.")
    else:
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
            log_request_details("DELETE", logs_url, github_headers(), delete_payload, delete_response)
        except requests.RequestException as exc:
            log_error(f"WARNING: Could not delete logs.txt: {exc}")
        else:
            if delete_response.status_code == 200:
                log_info("✅ logs.txt deleted successfully.")
            else:
                log_error(f"WARNING: Could not delete logs.txt. HTTP: {delete_response.status_code}")

else:

    log_separator()
    log_info("logs.txt KEPT FOR DEBUGGING")
    log_separator()
    log_error("Because Endpoint and Token were not both found,")
    log_error("logs.txt was NOT deleted.")


# ============================================================
# 2J. DELETE USED ADDRESSES FROM GITHUB
# ============================================================

# لیست آدرس‌هایی که استفاده شدن
used_addresses = [
    batch[0]["address"],
    batch[1]["address"],
    batch[2]["address"]
]

# حذف از گیت‌هاب
delete_used_addresses_from_github(used_addresses)


# ============================================================
# FINAL
# ============================================================

log_separator()

if endpoint and token_value:
    log_info("✅ SECTION 2 COMPLETE")
else:
    log_error("SECTION 2 FINISHED WITHOUT MATCH")

log_separator()
