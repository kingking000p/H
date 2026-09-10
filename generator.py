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
from concurrent.futures import ThreadPoolExecutor, as_completed


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

INITIAL_WAIT_SECONDS = 60
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
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
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


# ============================================================
# DELETE USED ADDRESSES
# ============================================================

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
    """روشن کردن سرور - با GITHUB_TOKEN"""
    dispatch_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    dispatch_payload = {
        "ref": GITHUB_REF,
        "inputs": {"batch_id": batch_id}
    }
    try:
        response = requests.post(dispatch_url, headers=github_headers(), json=dispatch_payload, timeout=30)
        return response
    except Exception as e:
        log_error(f"Workflow dispatch failed: {e}")
        return None


def get_run_id_for_batch(batch_id):
    """گرفتن Run ID بر اساس batch_id از inputs"""
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
                # چک کنیم که run مربوط به همین batch_id هست
                run_name = run.get("name", "") or ""
                display_title = run.get("display_title", "") or ""
                if str(batch_id) in run_name or str(batch_id) in display_title:
                    return run.get("id")
            # اگه پیدا نشد، جدیدترین رو برگردون
            if runs:
                return runs[0].get("id")
    except Exception as e:
        log_error(f"Error getting run_id for batch {batch_id}: {e}")
    return None


# ============================================================
# READ ENDPOINT CONFIGS FROM .txt FILES IN logs/ DIRECTORY
# ============================================================

def get_all_txt_files():
    """لیست همه فایل‌های .txt در پوشه logs را برمی‌گرداند."""
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
    """محتوای یک فایل .txt در پوشه logs را می‌خواند."""
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


def get_endpoint_configs():
    """همه فایل‌های .txt در پوشه logs را اسکن می‌کند."""
    all_files = get_all_txt_files()
    
    # مرتب‌سازی: logs_*.txt اول
    logs_files = sorted([f for f in all_files if f["name"].startswith("logs_")], key=lambda x: x["name"])
    other_files = sorted([f for f in all_files if not f["name"].startswith("logs_")], key=lambda x: x["name"])
    
    configs = []
    for file_info in logs_files + other_files:
        file_name = file_info["name"]
        content, _ = get_file_content(file_name)
        if content:
            endpoint, token = extract_endpoint_and_token(content)
            if endpoint and token:
                log_info(f"✅ Found config in {LOGS_DIR}/{file_name}")
                configs.append({
                    "file_name": file_name,
                    "endpoint": endpoint,
                    "token": token,
                    "sha": file_info.get("sha")
                })
    
    log_info(f"📊 Total endpoint configs found in {LOGS_DIR}: {len(configs)}")
    return configs


# ============================================================
# DELETE ALL TXT FILES
# ============================================================

def delete_all_txt_files():
    log_separator()
    log_info("🗑️ DELETING ALL .txt FILES FROM REPOSITORY")
    log_separator()
    deleted_count = 0
    failed_count = 0
    
    # پوشه logs
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
    
    # ریشه
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
# 🔥 SECTION 2 - FIRST: TURN ON ALL SERVERS (WITH GG_TOKEN)
# ============================================================

log_separator()
log_info(f"🔥 STEP 1: TURNING ON {total_address_batches} SERVERS")
log_separator()

# ساخت اسکریپت‌ها و روشن کردن همه سرورها با هم
log_info("📝 Generating scripts for all batches...")
for idx, batch in enumerate(address_batches, start=1):
    script_file = generate_script_for_batch(batch, idx)
    log_info(f"   ✅ Script {idx}: {script_file.name} ({script_file.stat().st_size} bytes)")

log_info(f"🔥 Triggering {total_address_batches} workflows (servers)...")

# روشن کردن همه سرورها با هم
batch_run_ids = {}

with ThreadPoolExecutor(max_workers=min(total_address_batches, 10)) as executor:
    futures = {}
    for idx, batch in enumerate(address_batches, start=1):
        log_info(f"[BATCH {idx}] 🔥 Triggering workflow...")
        future = executor.submit(trigger_workflow_with_inputs, idx)
        futures[future] = idx
    
    for future in as_completed(futures):
        batch_idx = futures[future]
        try:
            response = future.result()
            if response and response.status_code in (200, 204):
                log_info(f"[BATCH {batch_idx}] ✅ Workflow triggered (HTTP {response.status_code})")
            else:
                status_code = response.status_code if response else "None"
                log_error(f"[BATCH {batch_idx}] ❌ Failed to trigger workflow (HTTP {status_code})")
        except Exception as e:
            log_error(f"[BATCH {batch_idx}] ❌ Error triggering workflow: {e}")

# صبر ۳ ثانیه تا GitHub Run IDها ثبت بشن
log_info("⏳ Waiting 3 seconds for GitHub to register runs...")
time.sleep(3)

# گرفتن Run ID هر بچ
log_info("📌 Getting Run IDs for all batches...")
for idx in range(1, total_address_batches + 1):
    run_id = get_run_id_for_batch(idx)
    if run_id:
        batch_run_ids[idx] = run_id
        log_info(f"[BATCH {idx}] Run ID: {run_id}")
    else:
        log_warning(f"[BATCH {idx}] ⚠️ Could not get Run ID")

log_separator()
log_info(f"✅ {len(batch_run_ids)}/{total_address_batches} servers triggered successfully")
log_separator()


# ============================================================
# 🔥 SECTION 3 - WAIT 60 SECONDS FOR SERVERS TO START
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

log_info("✅ 60 seconds completed. Servers should be ready now.")


# ============================================================
# 🔥 SECTION 4 - NOW READ logs/ DIRECTORY FOR ENDPOINT CONFIGS
# ============================================================

log_separator()
log_info(f"📖 STEP 3: READING ENDPOINT CONFIGS FROM {LOGS_DIR}/")
log_separator()

endpoint_configs = get_endpoint_configs()

if not endpoint_configs:
    log_warning("⚠️ No endpoint configs found in logs/ directory.")
else:
    log_info(f"✅ Found {len(endpoint_configs)} endpoint configs")


# ============================================================
# SECTION 5 - MATCH BATCHES WITH CONFIGS & PROCESS
# ============================================================

log_separator()
log_info("🔗 STEP 4: MATCHING BATCHES WITH ENDPOINT CONFIGS")
log_separator()

log_info(f"Address batches: {total_address_batches}")
log_info(f"Endpoint configs: {len(endpoint_configs)}")

# تعیین تعداد قابل پردازش
processable_count = min(total_address_batches, len(endpoint_configs))

if processable_count == 0:
    log_error("❌ No processable batches (no configs available)")
    log_info("🛑 Shutting down all triggered servers...")
    for idx, run_id in batch_run_ids.items():
        cancel_workflow(run_id)
    fail("No endpoint configs available for processing")

if len(endpoint_configs) < total_address_batches:
    log_warning(f"⚠️ Only {len(endpoint_configs)} configs for {total_address_batches} batches.")
    log_warning(f"⚠️ Processing first {processable_count} batches only.")

log_info(f"✅ Will process {processable_count} batches")


# ============================================================
# SECTION 6 - PROCESS BATCHES WITH THEIR CONFIGS
# ============================================================

log_separator()
log_info(f"🚀 STEP 5: PROCESSING {processable_count} BATCHES")
log_separator()
log_info(f"Send & Run Enabled: {ENABLE_SEND_AND_RUN}")


def process_single_batch(batch_index, batch, config, config_index, run_id):
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
        log_info(f"[BATCH {batch_index}] 🚀 Starting... (config #{config_index + 1} from {config['file_name']})")
        
        for pos, item in enumerate(batch, start=1):
            log_info(f"[BATCH {batch_index}]   TARGET{pos}: index={item['index']}, address={item['address'][:30]}...")
        
        token_masked = f"{config['token'][:10]}...{config['token'][-5:]}" if len(config['token']) > 15 else config['token']
        log_info(f"[BATCH {batch_index}] 🔑 Token {config_index + 1}: {token_masked}")
        log_info(f"[BATCH {batch_index}] 🌐 Endpoint {config_index + 1}: {config['endpoint']}")
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
            log_info(f"[BATCH {batch_index}] 🚀 Sending and running script...")
            
            try:
                with open(script_file, "rb") as f:
                    script_bytes = f.read()
                b64_data = base64.b64encode(script_bytes).decode('ascii')
            except Exception as e:
                log_error(f"[BATCH {batch_index}] Could not read/encode script: {e}")
                batch_result["error"] = "Script read error"
                save_to_blacklist(batch_result["addresses"])
                return batch_result
            
            payload1 = {"command": f"echo '{b64_data}' > /tmp/script_{batch_index}.b64"}
            
            try:
                response1 = requests.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=payload1,
                    timeout=60
                )
                log_info(f"[BATCH {batch_index}] STEP 1: HTTP {response1.status_code}")
            except Exception as e:
                log_error(f"[BATCH {batch_index}] STEP 1 failed: {e}")
                batch_result["error"] = "Step 1 failed"
                save_to_blacklist(batch_result["addresses"])
                return batch_result
            
            payload2 = {"command": f"base64 -d /tmp/script_{batch_index}.b64 | bash"}
            
            try:
                start_time = time.time()
                response2 = requests.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=payload2,
                    timeout=600
                )
                elapsed = time.time() - start_time
                log_info(f"[BATCH {batch_index}] STEP 2: HTTP {response2.status_code} ({elapsed:.1f}s)")
                
                if response2.status_code == 200:
                    is_success, status = check_if_script_successful(response2.text)
                    script_successful = is_success
                    script_status = status
                    log_info(f"[BATCH {batch_index}] Script status: {status}")
                else:
                    log_error(f"[BATCH {batch_index}] Script execution failed: HTTP {response2.status_code}")
                    script_status = f"http_{response2.status_code}"
            except requests.Timeout:
                log_error(f"[BATCH {batch_index}] ⏱️ STEP 2 TIMEOUT!")
                script_status = "timeout"
            except Exception as e:
                log_error(f"[BATCH {batch_index}] STEP 2 failed: {e}")
                script_status = "request_failed"
        else:
            log_info(f"[BATCH {batch_index}] 📝 SEND/RUN DISABLED (REPORT ONLY)")
            log_info(f"[BATCH {batch_index}]    Would have sent: {script_file.name}")
            log_info(f"[BATCH {batch_index}]    Would have used endpoint: {endpoint}")
            script_successful = False
            script_status = "skipped"
        
        batch_result["successful"] = script_successful
        batch_result["status"] = script_status
        
        # پاک کردن آدرس‌ها
        if script_successful:
            log_info(f"[BATCH {batch_index}] ✅ Deleting addresses from GitHub...")
            used_addresses = [batch[0]["address"], batch[1]["address"], batch[2]["address"]]
            delete_used_addresses_from_github(used_addresses)
        else:
            if script_status == "skipped":
                log_info(f"[BATCH {batch_index}] ℹ️ Send/Run disabled. Addresses untouched.")
            else:
                log_warning(f"[BATCH {batch_index}] ⚠️ Script NOT successful! Adding to blacklist...")
                save_to_blacklist(batch_result["addresses"])
        
        log_info(f"[BATCH {batch_index}] ✅ PROCESSING COMPLETED!")
        
    except Exception as e:
        log_error(f"[BATCH {batch_index}] ❌ CRITICAL ERROR: {e}")
        batch_result["error"] = str(e)
        save_to_blacklist(batch_result["addresses"])
    
    return batch_result


# اجرا
batch_results = []

with ThreadPoolExecutor(max_workers=min(processable_count, 10)) as executor:
    futures = []
    for idx in range(1, processable_count + 1):
        batch = address_batches[idx - 1]
        config = endpoint_configs[idx - 1]
        run_id = batch_run_ids.get(idx)
        futures.append(executor.submit(process_single_batch, idx, batch, config, idx - 1, run_id))
    
    for future in as_completed(futures):
        try:
            result = future.result()
            batch_results.append(result)
        except Exception as e:
            log_error(f"Error processing batch: {e}")


# ============================================================
# SECTION 7 - SHUT DOWN ALL SERVERS (INCLUDING UNPROCESSED)
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
# DELETE ALL .txt FILES
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
