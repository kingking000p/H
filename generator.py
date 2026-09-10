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
MAX_ADDRESSES_TO_PROCESS = 30
ENABLE_SEND_AND_RUN = True
BLACKLIST_FILE = BASE_DIR / "blacklist.txt"


# ============================================================
# GITHUB CONFIG
# ============================================================

GITHUB_OWNER = "forgotenmywin"
GITHUB_REPO = "K"
GITHUB_REF = "main"
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE", "main.yml")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GG_TOKEN = os.environ.get("GG_TOKEN")
GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"

LOGS_DIR = "logs"


# ============================================================
# TIMING
# ============================================================

INITIAL_WAIT_SECONDS = 180
LOG_RETRY_COUNT = 20
LOG_RETRY_DELAY = 5
RUN_ID_WAIT_SECONDS = 5
RUN_ID_MAX_RETRIES = 5
TRIGGER_DELAY_SECONDS = 15
ENDPOINT_CHECK_RETRIES = 5
ENDPOINT_CHECK_DELAY = 20

SCRIPT_EXECUTION_WAIT = 180
RESULT_CHECK_RETRIES = 10
RESULT_CHECK_DELAY = 10

# 🔥 timeout کوتاه برای دستورات ساده
QUICK_CMD_TIMEOUT = 15
# 🔥 timeout برای شروع اسکریپت (setsid سریع برمی‌گرده)
START_SCRIPT_TIMEOUT = 20


# ============================================================
# HELPERS
# ============================================================

def fail(message: str):
    log_error(message)
    sys.exit(1)


def github_headers():
    if not GITHUB_TOKEN:
        fail("GITHUB_TOKEN is not set")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def gg_headers():
    if not GG_TOKEN:
        fail("GG_TOKEN is not set")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GG_TOKEN}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def load_blacklist():
    if not BLACKLIST_FILE.exists():
        return []
    try:
        content = BLACKLIST_FILE.read_text(encoding="utf-8")
        return [line.strip() for line in content.splitlines() if line.strip()]
    except:
        return []


def save_to_blacklist(addresses):
    current_blacklist = load_blacklist()
    new_addresses = [addr for addr in addresses if addr not in current_blacklist]
    if not new_addresses:
        return
    with open(BLACKLIST_FILE, "a", encoding="utf-8") as f:
        for addr in new_addresses:
            f.write(addr + "\n")
    log_warning(f"⚠️ Added {len(new_addresses)} addresses to blacklist")


def check_endpoint_alive(endpoint, token):
    base_url = endpoint.replace("/command", "")
    try:
        response = requests.get(
            base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        if response.status_code == 200:
            return True, response.text[:100]
        else:
            return False, f"HTTP {response.status_code}"
    except requests.RequestException as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def wait_for_endpoint_alive(endpoint, token, max_retries=None, delay=None):
    if max_retries is None:
        max_retries = ENDPOINT_CHECK_RETRIES
    if delay is None:
        delay = ENDPOINT_CHECK_DELAY
    
    for attempt in range(1, max_retries + 1):
        is_alive, info = check_endpoint_alive(endpoint, token)
        if is_alive:
            log_info(f"✅ Endpoint is alive! (attempt {attempt})")
            return True
        log_warning(f"⚠️ Endpoint not alive (attempt {attempt}/{max_retries}): {info}")
        if attempt < max_retries:
            time.sleep(delay)
    
    return False


def send_command_to_server(endpoint, token, command, timeout=30):
    """🔥 ارسال دستور به سرور"""
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"command": command},
            timeout=timeout
        )
        return response
    except Exception as e:
        log_error(f"send_command_to_server failed: {e}")
        return None


# ============================================================
# DELETE USED ADDRESSES
# ============================================================

def delete_used_addresses_from_github(addresses_to_remove):
    log_separator()
    log_info("DELETING USED ADDRESSES FROM GITHUB (using GG_TOKEN)")
    log_separator()
    addresses_url = "https://api.github.com/repos/kingking000p/H/contents/addresses.txt"
    if not GG_TOKEN:
        log_error("GG_TOKEN is not set, skipping deletion")
        return False
    headers = gg_headers()
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


# ============================================================
# WORKFLOW HELPERS
# ============================================================

def cancel_workflow(run_id):
    if not run_id or not GITHUB_TOKEN:
        return False
    cancel_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}/cancel"
    try:
        response = requests.post(cancel_url, headers=github_headers(), timeout=30)
        if response.status_code == 202:
            log_info(f"✅ Workflow {run_id} cancelled successfully!")
            return True
        elif response.status_code == 409:
            log_info(f"⚠️ Workflow {run_id} already completed.")
            return True
        else:
            log_error(f"Failed to cancel workflow: {response.status_code}")
            return False
    except Exception as e:
        log_error(f"Cancel request failed: {e}")
        return False


def check_if_script_successful(response_text):
    if not response_text:
        return False, "empty_response"
    response_lower = response_text.lower()
    if "faucet hourly budget used up" in response_lower:
        return False, "faucet_budget"
    if "try again shortly" in response_lower:
        return False, "faucet_budget"
    success_indicators = ["claim successful", "receive successful", "block hash", "balance:", "total:", "done"]
    for indicator in success_indicators:
        if indicator in response_lower:
            return True, "success"
    return False, "unknown"


def generate_script_for_batch(batch, batch_index):
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    generated = template
    generated = generated.replace("__ADDRESS1__", batch[0]["address"])
    generated = generated.replace("__INDEX1__", str(batch[0]["index"]))
    generated = generated.replace("__ADDRESS2__", batch[1]["address"])
    generated = generated.replace("__INDEX2__", str(batch[1]["index"]))
    generated = generated.replace("__ADDRESS3__", batch[2]["address"])
    generated = generated.replace("__INDEX3__", str(batch[2]["index"]))
    script_file = BASE_DIR / f"script_{batch_index}.sh"
    script_file.write_text(generated, encoding="utf-8")
    script_file.chmod(script_file.stat().st_mode | stat.S_IXUSR)
    return script_file


def trigger_workflow_with_inputs(batch_id):
    dispatch_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    dispatch_payload = {
        "ref": GITHUB_REF,
        "inputs": {"batch_id": str(batch_id)},
        "return_run_details": True
    }
    
    log_debug(f"[BATCH {batch_id}] POST {dispatch_url}")
    log_debug(f"[BATCH {batch_id}] Payload: {dispatch_payload}")
    
    try:
        response = requests.post(
            dispatch_url,
            headers=github_headers(),
            json=dispatch_payload,
            timeout=30
        )
        log_debug(f"[BATCH {batch_id}] Response: HTTP {response.status_code}")
        
        run_id_from_response = None
        
        if response.status_code == 200:
            try:
                resp_json = response.json()
                run_id_from_response = resp_json.get("workflow_run_id")
                if run_id_from_response:
                    log_debug(f"[BATCH {batch_id}] workflow_run_id from response: {run_id_from_response}")
            except Exception as e:
                log_debug(f"[BATCH {batch_id}] Could not parse response JSON: {e}")
        
        if response.status_code not in (200, 204):
            log_error(f"[BATCH {batch_id}] Response body: {response.text[:500]}")
        
        return response, run_id_from_response
        
    except requests.RequestException as e:
        log_error(f"[BATCH {batch_id}] Request exception: {e}")
        return None, None
    except Exception as e:
        log_error(f"[BATCH {batch_id}] Unexpected exception: {e}")
        return None, None


def get_latest_unique_run_id(existing_run_ids):
    runs_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
    try:
        response = requests.get(
            runs_url,
            headers=github_headers(),
            params={"branch": GITHUB_REF, "per_page": 20},
            timeout=30
        )
        if response.status_code == 200:
            runs = response.json().get("workflow_runs", [])
            for run in runs:
                run_id = run.get("id")
                if run_id and run_id not in existing_run_ids:
                    return run_id
    except Exception as e:
        log_error(f"Error getting unique run_id: {e}")
    return None


# ============================================================
# READ ENDPOINT CONFIGS
# ============================================================

def get_all_txt_files():
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{LOGS_DIR}"
    try:
        response = requests.get(url, headers=github_headers(), timeout=30)
        if response.status_code == 200:
            files = response.json()
            return [f for f in files if f["name"].endswith(".txt")]
        elif response.status_code == 404:
            log_warning(f"⚠️ Pوشه {LOGS_DIR}/ پیدا نشد")
            return []
        else:
            log_error(f"Could not list contents of {LOGS_DIR}: HTTP {response.status_code}")
            return []
    except Exception as e:
        log_error(f"Error listing contents of {LOGS_DIR}: {e}")
        return []


def get_file_content(file_name):
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{LOGS_DIR}/{file_name}"
    try:
        response = requests.get(url, headers=github_headers(), params={"ref": GITHUB_REF}, timeout=30)
        if response.status_code == 200:
            data = response.json()
            encoded = data.get("content")
            if encoded:
                return base64.b64decode(encoded).decode("utf-8", errors="replace"), data.get("sha")
        else:
            log_error(f"Could not read {file_name}: HTTP {response.status_code}")
    except Exception as e:
        log_error(f"Error reading {file_name}: {e}")
    return None, None


def extract_endpoint_and_token(content):
    remote_url_match = re.search(r"(?m)^\s*REMOTE_URL\s*=\s*(https://[^\s]+)\s*$", content)
    api_token_match = re.search(r"(?m)^\s*API_TOKEN\s*=\s*([A-Za-z0-9_-]{20,})\s*$", content)
    endpoint = None
    token = None
    if remote_url_match:
        remote_url = remote_url_match.group(1).strip()
        endpoint = remote_url.rstrip("/") + "/command"
    if api_token_match:
        token = api_token_match.group(1).strip()
    return endpoint, token


def get_endpoint_configs(valid_run_ids=None):
    all_files = get_all_txt_files()
    
    if valid_run_ids:
        valid_run_ids_str = [str(rid) for rid in valid_run_ids]
        filtered_files = []
        for f in all_files:
            for rid_str in valid_run_ids_str:
                if rid_str in f["name"]:
                    filtered_files.append(f)
                    break
        
        if filtered_files:
            log_info(f"📊 Filtered: {len(filtered_files)} files match current Run IDs")
            all_files = filtered_files
        else:
            log_warning(f"⚠️ No files match current Run IDs")
            all_files = []
    
    def sort_key(f):
        name = f["name"]
        match = re.search(r"batch-(\d+)", name)
        if match:
            return (0, int(match.group(1)))
        return (2, name)
    
    sorted_files = sorted(all_files, key=sort_key)
    
    configs = []
    for file_info in sorted_files:
        file_name = file_info["name"]
        content, _ = get_file_content(file_name)
        if content:
            endpoint, token = extract_endpoint_and_token(content)
            if endpoint and token:
                batch_match = re.search(r"batch-(\d+)", file_name)
                batch_id_in_file = int(batch_match.group(1)) if batch_match else None
                
                run_match = re.search(r"run-(\d+)", file_name)
                run_id_in_file = run_match.group(1) if run_match else None
                
                log_info(f"✅ Found config: {LOGS_DIR}/{file_name} (batch_id: {batch_id_in_file}, run_id: {run_id_in_file})")
                configs.append({
                    "file_name": file_name,
                    "endpoint": endpoint,
                    "token": token,
                    "sha": file_info.get("sha"),
                    "batch_id_in_file": batch_id_in_file,
                    "run_id_in_file": run_id_in_file
                })
    
    log_info(f"📊 Total endpoint configs found: {len(configs)}")
    return configs


def get_config_for_batch_id(configs, batch_id):
    for config in configs:
        if config["batch_id_in_file"] == batch_id:
            return config
    return None


def delete_all_txt_files():
    log_separator()
    log_info("🗑️ DELETING ALL .txt FILES FROM REPOSITORY K")
    log_separator()
    deleted_count = 0
    failed_count = 0
    
    try:
        url_logs = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{LOGS_DIR}"
        response = requests.get(url_logs, headers=github_headers(), params={"ref": GITHUB_REF}, timeout=30)
        if response.status_code == 200:
            files = response.json()
            txt_files = [f for f in files if f["name"].endswith(".txt")]
            log_info(f"Found {len(txt_files)} .txt files in {LOGS_DIR}/")
            for file_info in txt_files:
                file_name = file_info["name"]
                file_path = f"{LOGS_DIR}/{file_name}"
                file_sha = file_info.get("sha")
                if not file_sha:
                    failed_count += 1
                    continue
                delete_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{file_path}"
                delete_payload = {"message": f"Delete {file_path}", "sha": file_sha, "branch": GITHUB_REF}
                try:
                    del_resp = requests.delete(delete_url, headers=github_headers(), json=delete_payload, timeout=30)
                    if del_resp.status_code == 200:
                        log_info(f"✅ Deleted {file_path}")
                        deleted_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    log_warning(f"⚠️ Error deleting {file_path}: {e}")
                    failed_count += 1
    except Exception as e:
        log_warning(f"⚠️ Error listing {LOGS_DIR}/: {e}")
    
    try:
        url_root = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/"
        response = requests.get(url_root, headers=github_headers(), params={"ref": GITHUB_REF}, timeout=30)
        if response.status_code == 200:
            files = response.json()
            txt_files = [f for f in files if f["name"].endswith(".txt")]
            log_info(f"Found {len(txt_files)} .txt files in root/")
            for file_info in txt_files:
                file_name = file_info["name"]
                file_sha = file_info.get("sha")
                if not file_sha:
                    failed_count += 1
                    continue
                delete_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{file_name}"
                delete_payload = {"message": f"Delete {file_name}", "sha": file_sha, "branch": GITHUB_REF}
                try:
                    del_resp = requests.delete(delete_url, headers=github_headers(), json=delete_payload, timeout=30)
                    if del_resp.status_code == 200:
                        log_info(f"✅ Deleted {file_name}")
                        deleted_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    log_warning(f"⚠️ Error deleting {file_name}: {e}")
                    failed_count += 1
    except Exception as e:
        log_warning(f"⚠️ Error listing root: {e}")
    
    log_separator()
    log_info(f"📊 Deletion summary: {deleted_count} deleted, {failed_count} failed")
    log_separator()


# ============================================================
# SECTION 1 - LOAD AND SPLIT ADDRESSES
# ============================================================

log_separator()
log_info("ADDRESS BATCH GENERATOR")
log_separator()

if not ADDRESSES_FILE.exists():
    fail(f"Missing file: {ADDRESSES_FILE}")
if not TEMPLATE_FILE.exists():
    fail(f"Missing file: {TEMPLATE_FILE}")

log_info("✅ All required files found")

raw_lines = ADDRESSES_FILE.read_text(encoding="utf-8").splitlines()
records = []
for line_no, raw in enumerate(raw_lines, start=1):
    line = raw.strip()
    if not line:
        continue
    if ":" not in line:
        fail(f"Invalid format at line {line_no}: {raw}")
    index_text, address = line.split(":", 1)
    index_text = index_text.strip()
    address = address.strip()
    if not index_text.isdigit():
        fail(f"Invalid index at line {line_no}: {index_text}")
    if not address:
        fail(f"Empty address at line {line_no}")
    records.append({"index": int(index_text), "address": address})

log_info(f"Loaded records: {len(records)}")

first_30_records = records[:MAX_ADDRESSES_TO_PROCESS]
log_info(f"✅ Using first {len(first_30_records)} addresses")

address_batches = [first_30_records[i:i+BATCH_SIZE] for i in range(0, len(first_30_records), BATCH_SIZE)]
if address_batches and len(address_batches[-1]) < BATCH_SIZE:
    log_warning(f"⚠️ Last batch has only {len(address_batches[-1])} addresses (skipping)")
    address_batches = address_batches[:-1]

total_address_batches = len(address_batches)
log_info(f"✅ Total address batches: {total_address_batches} (each with {BATCH_SIZE} addresses)")


# ============================================================
# STEP 0: CLEAN UP OLD LOG FILES
# ============================================================

log_separator()
log_info("🗑️ STEP 0: CLEANING UP OLD LOG FILES BEFORE START")
log_separator()

delete_all_txt_files()


# ============================================================
# STEP 1: TURN ON ALL SERVERS
# ============================================================

log_separator()
log_info(f"🔥 STEP 1: TURNING ON {total_address_batches} SERVERS SEQUENTIALLY")
log_separator()

log_info("📝 Generating scripts for all batches...")
for idx, batch in enumerate(address_batches, start=1):
    script_file = generate_script_for_batch(batch, idx)
    log_info(f"   ✅ Script {idx}: {script_file.name} ({script_file.stat().st_size} bytes)")

log_info(f"🔥 Triggering {total_address_batches} workflows ONE BY ONE...")

batch_run_ids = {}
used_run_ids = set()

for idx in range(1, total_address_batches + 1):
    log_info(f"[BATCH {idx}] 🔥 Triggering workflow...")
    
    response, direct_run_id = trigger_workflow_with_inputs(idx)
    
    if response and response.status_code in (200, 204):
        log_info(f"[BATCH {idx}] ✅ Workflow triggered (HTTP {response.status_code})")
        
        if direct_run_id:
            batch_run_ids[idx] = direct_run_id
            used_run_ids.add(direct_run_id)
            log_info(f"[BATCH {idx}] 📌 Run ID (from response): {direct_run_id}")
        else:
            log_info(f"[BATCH {idx}] ⏳ Waiting {RUN_ID_WAIT_SECONDS}s for GitHub to register the run...")
            time.sleep(RUN_ID_WAIT_SECONDS)
            
            run_id = None
            for attempt in range(1, RUN_ID_MAX_RETRIES + 1):
                run_id = get_latest_unique_run_id(used_run_ids)
                if run_id:
                    break
                log_warning(f"[BATCH {idx}] ⚠️ Attempt {attempt}/{RUN_ID_MAX_RETRIES}: No unique Run ID yet, waiting...")
                time.sleep(RUN_ID_WAIT_SECONDS)
            
            if run_id:
                batch_run_ids[idx] = run_id
                used_run_ids.add(run_id)
                log_info(f"[BATCH {idx}] 📌 Run ID (latest unique): {run_id}")
            else:
                log_error(f"[BATCH {idx}] ❌ Could not get unique Run ID after {RUN_ID_MAX_RETRIES} attempts")
    else:
        status_code = response.status_code if response else "None"
        log_error(f"[BATCH {idx}] ❌ Failed to trigger workflow (HTTP {status_code})")
    
    if idx < total_address_batches:
        log_info(f"[BATCH {idx}] ⏳ Waiting {TRIGGER_DELAY_SECONDS}s before next batch...")
        time.sleep(TRIGGER_DELAY_SECONDS)

log_separator()
log_info("📌 RUN ID SUMMARY:")
for idx in sorted(batch_run_ids.keys()):
    log_info(f"   Batch {idx}: Run ID = {batch_run_ids[idx]}")

all_run_ids = list(batch_run_ids.values())
if len(all_run_ids) != len(set(all_run_ids)):
    log_warning("⚠️ Duplicate Run IDs detected!")
else:
    log_info("✅ All Run IDs are unique!")

log_separator()
log_info(f"✅ {len(batch_run_ids)}/{total_address_batches} servers triggered successfully")
log_separator()


# ============================================================
# STEP 2: WAIT FOR SERVERS TO START
# ============================================================

log_separator()
log_info(f"⏳ STEP 2: WAITING {INITIAL_WAIT_SECONDS} SECONDS FOR SERVERS TO START")
log_separator()

remaining = INITIAL_WAIT_SECONDS
while remaining > 0:
    log_info(f"  {remaining} seconds remaining...")
    sleep_for = min(10, remaining)
    time.sleep(sleep_for)
    remaining -= sleep_for

log_info("✅ Wait completed. Servers should be ready now.")


# ============================================================
# STEP 3: READ logs/ DIRECTORY
# ============================================================

log_separator()
log_info(f"📖 STEP 3: READING ENDPOINT CONFIGS FROM {LOGS_DIR}/")
log_separator()

current_run_ids = list(batch_run_ids.values())
log_info(f"📌 Valid Run IDs for this execution: {current_run_ids}")

endpoint_configs = []
for attempt in range(1, LOG_RETRY_COUNT + 1):
    log_info(f"📖 Attempt {attempt}/{LOG_RETRY_COUNT}: Reading configs...")
    endpoint_configs = get_endpoint_configs(valid_run_ids=current_run_ids)
    
    if len(endpoint_configs) >= total_address_batches:
        log_info(f"✅ Found enough configs: {len(endpoint_configs)}")
        break
    
    if attempt < LOG_RETRY_COUNT:
        log_warning(f"⚠️ Only {len(endpoint_configs)}/{total_address_batches} configs found. Retrying in {LOG_RETRY_DELAY}s...")
        time.sleep(LOG_RETRY_DELAY)

if not endpoint_configs:
    log_warning("⚠️ No endpoint configs found for current Run IDs.")
else:
    log_info(f"✅ Found {len(endpoint_configs)} endpoint configs")
    log_info("📋 Config mapping (batch_id_in_file → file_name):")
    for config in endpoint_configs:
        log_info(f"   batch-{config['batch_id_in_file']} → {config['file_name']}")


# ============================================================
# STEP 3.5: CHECK IF ENDPOINTS ARE ALIVE
# ============================================================

log_separator()
log_info("🔍 STEP 3.5: CHECKING IF ENDPOINTS ARE ALIVE")
log_separator()

alive_configs = []
for config in endpoint_configs:
    log_info(f"🔍 Checking endpoint for {config['file_name']}...")
    log_info(f"   Endpoint: {config['endpoint']}")
    
    is_alive = wait_for_endpoint_alive(
        config['endpoint'],
        config['token'],
        max_retries=ENDPOINT_CHECK_RETRIES,
        delay=ENDPOINT_CHECK_DELAY
    )
    
    if is_alive:
        log_info(f"   ✅ Endpoint is ALIVE")
        alive_configs.append(config)
    else:
        log_error(f"   ❌ Endpoint is NOT reachable after {ENDPOINT_CHECK_RETRIES} attempts")

endpoint_configs = alive_configs

if not endpoint_configs:
    log_error("❌ No alive endpoints found!")
else:
    log_info(f"✅ {len(endpoint_configs)} alive endpoints ready")


# ============================================================
# STEP 4: MATCH BATCHES WITH CONFIGS
# ============================================================

log_separator()
log_info("🔗 STEP 4: MATCHING BATCHES WITH ENDPOINT CONFIGS")
log_info("   (matching by batch_id_in_file, NOT by list index)")
log_separator()

log_info(f"Address batches: {total_address_batches}")
log_info(f"Endpoint configs: {len(endpoint_configs)}")

batch_config_pairs = []
for idx in range(1, total_address_batches + 1):
    config = get_config_for_batch_id(endpoint_configs, idx)
    if config:
        batch_config_pairs.append((idx, config))
        log_info(f"✅ Batch {idx} matched with config from {config['file_name']} (batch_id_in_file={config['batch_id_in_file']})")
    else:
        log_warning(f"⚠️ No config found for Batch {idx}")

if not batch_config_pairs:
    log_error("❌ No processable batches (no matching configs)")
    for idx, run_id in batch_run_ids.items():
        cancel_workflow(run_id)
    fail("No matching configs available for processing")

log_info(f"✅ Will process {len(batch_config_pairs)} batches")


# ============================================================
# STEP 5: PROCESS BATCHES
# ============================================================

log_separator()
log_info(f"🚀 STEP 5: PROCESSING {len(batch_config_pairs)} BATCHES SEQUENTIALLY")
log_separator()
log_info(f"Send & Run Enabled: {ENABLE_SEND_AND_RUN}")


def process_single_batch(batch_index, batch, config, run_id):
    """
    🔥 پردازش یک batch با endpoint/token مخصوص خودش
    """
    batch_result = {
        "batch": batch_index,
        "run_id": run_id,
        "endpoint": None,
        "token": None,
        "successful": False,
        "status": "unknown",
        "error": None,
        "addresses": [item["address"] for item in batch]
    }
    
    try:
        log_separator()
        log_info(f"[BATCH {batch_index}] 🚀 Starting... (config from {config['file_name']})")
        log_separator()
        
        for pos, item in enumerate(batch, start=1):
            log_info(f"[BATCH {batch_index}]   TARGET{pos}: index={item['index']}, address={item['address'][:30]}...")
        
        token_masked = f"{config['token'][:10]}...{config['token'][-5:]}" if len(config['token']) > 15 else config['token']
        log_info(f"[BATCH {batch_index}] 🔑 Token: {token_masked}")
        log_info(f"[BATCH {batch_index}] 🌐 Endpoint: {config['endpoint']}")
        log_info(f"[BATCH {batch_index}] 📁 Config file: {LOGS_DIR}/{config['file_name']}")
        
        script_file = BASE_DIR / f"script_{batch_index}.sh"
        if not script_file.exists():
            script_file = generate_script_for_batch(batch, batch_index)
        
        endpoint = config["endpoint"]
        token = config["token"]
        batch_result["endpoint"] = endpoint
        batch_result["token"] = token
        
        script_successful = False
        script_status = "unknown"
        
        if ENABLE_SEND_AND_RUN:
            log_separator()
            log_info(f"[BATCH {batch_index}] 🚀 Sending and running script...")
            log_separator()
            
            # خواندن اسکریپت
            try:
                with open(script_file, "rb") as f:
                    script_bytes = f.read()
                b64_data = base64.b64encode(script_bytes).decode('ascii')
            except Exception as e:
                log_error(f"[BATCH {batch_index}] Could not read/encode script: {e}")
                batch_result["error"] = "Script read error"
                save_to_blacklist(batch_result["addresses"])
                return batch_result
            
            # === STEP A: ارسال اسکریپت ===
            log_info(f"[BATCH {batch_index}] 📤 STEP A: Uploading script...")
            upload_cmd = f"cat > /tmp/script_{batch_index}.b64 << 'B64EOF'\n{b64_data}\nB64EOF\necho 'UPLOADED'"
            
            response1 = send_command_to_server(endpoint, token, upload_cmd, timeout=60)
            
            if not response1 or response1.status_code != 200:
                status = response1.status_code if response1 else "None"
                log_error(f"[BATCH {batch_index}] STEP A failed: HTTP {status}")
                batch_result["error"] = "Step A failed"
                save_to_blacklist(batch_result["addresses"])
                return batch_result
            
            log_info(f"[BATCH {batch_index}] ✅ STEP A: HTTP {response1.status_code}")
            
            # تأیید آپلود
            check_upload = send_command_to_server(endpoint, token, f"ls -la /tmp/script_{batch_index}.b64", timeout=QUICK_CMD_TIMEOUT)
            if check_upload and check_upload.status_code == 200:
                log_info(f"[BATCH {batch_index}] 📁 Upload check: {check_upload.text[:200]}")
            
            # === STEP B: اجرای اسکریپت با setsid (کاملاً جدا از PTY) ===
            log_info(f"[BATCH {batch_index}] 🚀 STEP B: Starting script with setsid...")
            
            # پاک کردن فایل‌های قبلی
            cleanup_cmd = f"rm -f /tmp/result_{batch_index}.txt /tmp/done_{batch_index}.flag /tmp/exit_code_{batch_index}.txt"
            send_command_to_server(endpoint, token, cleanup_cmd, timeout=QUICK_CMD_TIMEOUT)
            
            # 🔥 دستور setsid - کاملاً از PTY جدا می‌شه
            bg_command = (
                f"cd /tmp && "
                f"base64 -d /tmp/script_{batch_index}.b64 > /tmp/script_{batch_index}.sh && "
                f"chmod +x /tmp/script_{batch_index}.sh && "
                f"setsid bash -c '"
                f"bash /tmp/script_{batch_index}.sh > /tmp/result_{batch_index}.txt 2>&1; "
                f"echo $? > /tmp/exit_code_{batch_index}.txt; "
                f"touch /tmp/done_{batch_index}.flag"
                f"' < /dev/null > /dev/null 2>&1 & "
                f"disown; "
                f"echo 'STARTED'"
            )
            
            log_debug(f"[BATCH {batch_index}] STEP B command: {bg_command[:200]}...")
            
            response2 = send_command_to_server(endpoint, token, bg_command, timeout=START_SCRIPT_TIMEOUT)
            
            if not response2 or response2.status_code != 200:
                status = response2.status_code if response2 else "None"
                log_error(f"[BATCH {batch_index}] STEP B failed: HTTP {status}")
                batch_result["error"] = "Step B failed"
                save_to_blacklist(batch_result["addresses"])
                return batch_result
            
            log_info(f"[BATCH {batch_index}] ✅ STEP B: HTTP {response2.status_code}")
            log_info(f"[BATCH {batch_index}] 📄 Response: {response2.text[:200]}")
            
            # === STEP C: صبر و بررسی وضعیت ===
            log_info(f"[BATCH {batch_index}] ⏳ STEP C: Waiting for script to complete (max {SCRIPT_EXECUTION_WAIT}s)...")
            
            start_wait = time.time()
            completed = False
            
            while time.time() - start_wait < SCRIPT_EXECUTION_WAIT:
                elapsed = int(time.time() - start_wait)
                
                check_cmd = (
                    f"if [ -f /tmp/done_{batch_index}.flag ]; then "
                    f"echo 'DONE'; "
                    f"cat /tmp/exit_code_{batch_index}.txt 2>/dev/null; "
                    f"else echo 'NOT_YET'; fi"
                )
                
                check_resp = send_command_to_server(endpoint, token, check_cmd, timeout=QUICK_CMD_TIMEOUT)
                
                if check_resp and check_resp.status_code == 200:
                    resp_text = check_resp.text.strip()
                    
                    if "DONE" in resp_text:
                        log_info(f"[BATCH {batch_index}] ✅ Script completed after {elapsed}s")
                        log_info(f"[BATCH {batch_index}] 📊 Status: {resp_text[:100]}")
                        completed = True
                        break
                    else:
                        if elapsed % 30 == 0 and elapsed > 0:
                            log_info(f"[BATCH {batch_index}] ⏳ Still running... ({elapsed}s / {SCRIPT_EXECUTION_WAIT}s)")
                else:
                    log_warning(f"[BATCH {batch_index}] ⚠️ Check failed at {elapsed}s")
                
                time.sleep(RESULT_CHECK_DELAY)
            
            if not completed:
                log_warning(f"[BATCH {batch_index}] ⚠️ Script did NOT complete within {SCRIPT_EXECUTION_WAIT}s")
            
            # === STEP D: خواندن نتیجه ===
            log_info(f"[BATCH {batch_index}] 📖 STEP D: Reading result...")
            
            result_text = ""
            for attempt in range(1, RESULT_CHECK_RETRIES + 1):
                result_resp = send_command_to_server(
                    endpoint, token,
                    f"cat /tmp/result_{batch_index}.txt 2>/dev/null || echo 'NO_RESULT'",
                    timeout=QUICK_CMD_TIMEOUT
                )
                
                if result_resp and result_resp.status_code == 200:
                    result_text = result_resp.text
                    log_info(f"[BATCH {batch_index}] ✅ Result received (attempt {attempt}, size: {len(result_text)} chars)")
                    break
                else:
                    log_warning(f"[BATCH {batch_index}] ⚠️ Result read attempt {attempt} failed")
                    time.sleep(RESULT_CHECK_DELAY)
            
            # === STEP E: نمایش کامل نتیجه ===
            log_separator()
            log_info(f"[BATCH {batch_index}] 📄 ===== FULL RESULT =====")
            log_separator()
            
            if result_text:
                for line in result_text.splitlines():
                    log_info(f"[BATCH {batch_index}] | {line}")
            else:
                log_warning(f"[BATCH {batch_index}] | (empty result)")
            
            log_separator()
            
            # === STEP F: بررسی موفقیت ===
            if result_text and "NO_RESULT" not in result_text and len(result_text.strip()) > 10:
                is_success, status = check_if_script_successful(result_text)
                script_successful = is_success
                script_status = status
                log_info(f"[BATCH {batch_index}] 🎯 Script status: {status}")
            else:
                log_error(f"[BATCH {batch_index}] ❌ Result is empty or unreadable")
                script_status = "result_unreadable"
        else:
            log_info(f"[BATCH {batch_index}] 📝 SEND/RUN DISABLED (REPORT ONLY)")
            script_successful = False
            script_status = "skipped"
        
        batch_result["successful"] = script_successful
        batch_result["status"] = script_status
        
        # === STEP G: حذف آدرس‌ها ===
        if script_successful:
            log_separator()
            log_info(f"[BATCH {batch_index}] ✅ Script succeeded! Deleting addresses...")
            log_separator()
            used_addresses = [batch[0]["address"], batch[1]["address"], batch[2]["address"]]
            delete_used_addresses_from_github(used_addresses)
        else:
            if script_status == "skipped":
                log_info(f"[BATCH {batch_index}] ℹ️ Send/Run disabled. Addresses untouched.")
            else:
                log_warning(f"[BATCH {batch_index}] ⚠️ Script NOT successful (status: {script_status})!")
                log_warning(f"[BATCH {batch_index}] ⚠️ Adding addresses to blacklist...")
                save_to_blacklist(batch_result["addresses"])
        
        log_info(f"[BATCH {batch_index}] ✅ PROCESSING COMPLETED!")
        
    except Exception as e:
        log_error(f"[BATCH {batch_index}] ❌ CRITICAL ERROR: {e}")
        import traceback
        log_error(f"[BATCH {batch_index}] Traceback: {traceback.format_exc()}")
        batch_result["error"] = str(e)
        save_to_blacklist(batch_result["addresses"])
    
    return batch_result


# 🔥 اجرای متوالی
batch_results = []

for pair_idx, (batch_id, config) in enumerate(batch_config_pairs):
    batch = address_batches[batch_id - 1]
    run_id = batch_run_ids.get(batch_id)
    
    result = process_single_batch(batch_id, batch, config, run_id)
    batch_results.append(result)
    
    if pair_idx < len(batch_config_pairs) - 1:
        log_info(f"⏳ Waiting 10s before next batch...")
        time.sleep(10)


# ============================================================
# STEP 6: SHUT DOWN ALL SERVERS
# ============================================================

log_separator()
log_info("🛑 STEP 6: SHUTTING DOWN ALL SERVERS")
log_separator()

for idx in range(1, total_address_batches + 1):
    run_id = batch_run_ids.get(idx)
    if run_id:
        log_info(f"[BATCH {idx}] 🛑 Shutting down server (Run ID: {run_id})...")
        cancel_workflow(run_id)
    else:
        log_warning(f"[BATCH {idx}] ⚠️ No Run ID, cannot shut down")


# ============================================================
# STEP 7: DELETE ALL .txt FILES
# ============================================================

log_separator()
log_info("🗑️ STEP 7: CLEANING UP .txt FILES")
log_separator()

delete_all_txt_files()


# ============================================================
# FINAL SUMMARY
# ============================================================

log_separator()
log_info("🎉 ALL DONE!")
log_separator()
log_info("📊 SUMMARY:")
log_info(f"   Total address batches: {total_address_batches}")
log_info(f"   Servers triggered: {len(batch_run_ids)}")
log_info(f"   Endpoint configs found: {len(endpoint_configs)}")
log_info(f"   Batches processed: {len(batch_results)}")
log_info(f"   Send & Run Enabled: {ENABLE_SEND_AND_RUN}")

log_info("📌 Run IDs used:")
for idx in sorted(batch_run_ids.keys()):
    log_info(f"   Batch {idx}: {batch_run_ids[idx]}")

final_blacklist = load_blacklist()
log_info(f"📋 Final blacklist: {len(final_blacklist)} addresses")

success_count = 0
failed_count = 0
skipped_count = 0

log_separator()
log_info("📊 BATCH RESULTS:")
log_separator()

for result in batch_results:
    status_icon = "✅" if result["successful"] else "❌"
    log_info(f"   Batch {result['batch']}: {status_icon} Run ID={result['run_id']}, Status={result['status']}")
    if result["successful"]:
        success_count += 1
    elif result["status"] == "skipped":
        skipped_count += 1
    else:
        failed_count += 1

log_info(f"   ✅ Successful: {success_count}/{len(batch_results)}")
log_info(f"   ⏭️ Skipped: {skipped_count}/{len(batch_results)}")
log_info(f"   ❌ Failed: {failed_count}/{len(batch_results)}")

log_separator()
log_info("✅ ALL DONE!")
log_separator()
