#!/bin/bash
# ============================================================
# FEELLESS402 CLAIM + RECEIVE
# ============================================================

python3 -m pip install -U nanopy feeless402 requests && \
python3 - <<'PY'
import os
import time
import secrets
import requests
import nanopy


# ============================================================
# 🔥 CONFIG - فقط این ۷ متغیر رو پر کن
# ============================================================

SEED = '673754a71ff81f5d7dc9c4d1f2e3acd996df945794e4de4c34e0ea4cc2861234'
ADDRESS1 = '__ADDRESS1__'
INDEX1  = __INDEX1__

ADDRESS2 = '__ADDRESS2__'
INDEX2  = __INDEX2__

ADDRESS3 = '__ADDRESS3__'
INDEX3  = __INDEX3__


# ============================================================
# VALIDATION
# ============================================================

if not SEED or SEED == 'SEEDخودت-این-ج':
    raise SystemExit("❌ ERROR: Enter the SEED correctly!")

if not ADDRESS1 or ADDRESS1 == 'nano_1abc...' or not ADDRESS2 or ADDRESS2 == 'nano_2def...' or not ADDRESS3 or ADDRESS3 == 'nano_3ghi...':
    raise SystemExit("❌ ERROR: All addresses must be complete and valid!")

try:
    INDEX1, INDEX2, INDEX3 = int(INDEX1), int(INDEX2), int(INDEX3)
except Exception:
    raise SystemExit("❌ ERROR: Indexes must be integers!")

TARGETS = [
    {'address': ADDRESS1, 'index': INDEX1},
    {'address': ADDRESS2, 'index': INDEX2},
    {'address': ADDRESS3, 'index': INDEX3},
]


# ============================================================
# CONFIG
# ============================================================

FAUCET = "https://feeless402.com"
RPC_URL = "https://node.somenano.com/proxy"

RECEIVE_DIFFICULTY = int("fffffe0000000000", 16)
PENDING_TIMEOUT = 180
PENDING_INTERVAL = 5

session = requests.Session()


# ============================================================
# 🔥 HASH CLEANER (کلید حل مشکل)
# ============================================================

def clean_hash(h):
    """
    🔥 پاک‌سازی کامل hash از هر کاراکتر غیر-hex
    این تابع مشکل 'non-hexadecimal number found in fromhex()' رو حل می‌کنه
    """
    if h is None:
        return None
    
    # تبدیل bytes به string
    if isinstance(h, bytes):
        try:
            h = h.decode("utf-8", errors="ignore")
        except Exception:
            h = str(h)
    else:
        h = str(h)
    
    # فقط کاراکترهای hex رو نگه دار (0-9, a-f, A-F)
    h = "".join(c for c in h if c in "0123456789abcdefABCDEF")
    
    return h


# ============================================================
# RPC
# ============================================================

def rpc(payload):
    r = session.post(RPC_URL, json=payload, timeout=60)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"RPC returned invalid JSON: {r.text}")
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


# ============================================================
# UTILS
# ============================================================

def raw_to_xno(raw):
    return int(raw) / 10**30


def derive_account(index):
    return nanopy.Account(sk=nanopy.deterministic_key(SEED, index))


def is_already_claimed(result):
    text = str(result).lower()
    return ("already claimed" in text or "one claim per address" in text or "starter xno" in text)


def is_ip_limit(result):
    text = str(result).lower()
    return ("claims per ip" in text or "ip limit" in text or "daily limit" in text or "rate limit" in text)


# ============================================================
# CLAIM
# ============================================================

def claim(address):
    print()
    print("=" * 38)
    print(f"CLAIM FOR ADDRESS: {address}")
    print("=" * 38)

    try:
        r = session.get(f"{FAUCET}/faucet/challenge", params={"address": address}, timeout=30)
    except Exception as e:
        print(f"challenge error: {e}")
        return "error"

    try:
        challenge = r.json()
    except Exception:
        print(f"invalid challenge response HTTP {r.status_code}: {r.text}")
        return "error"

    if "error" in challenge:
        print(f"challenge error: {challenge['error']}")
        return "error"

    root = challenge.get("root")
    difficulty_hex = challenge.get("difficulty")
    if not root or not difficulty_hex:
        print(f"bad challenge: {challenge}")
        return "error"

    difficulty = int(difficulty_hex, 16)
    print(f"root:       {root}")
    print(f"difficulty: {difficulty_hex}")
    print("generating faucet PoW...")

    try:
        work_int = nanopy.ext.work_generate(bytes.fromhex(root), difficulty, secrets.token_bytes(128))
    except Exception as e:
        print(f"PoW error: {e}")
        return "error"

    work = f"{work_int:016x}"
    print(f"work: {work}")

    try:
        r = session.post(f"{FAUCET}/faucet", json={"address": address, "work": work}, timeout=240)
    except Exception as e:
        print(f"claim request error: {e}")
        return "error"

    try:
        result = r.json()
    except Exception:
        result = r.text

    print(f"HTTP {r.status_code}")
    print(f"response: {result}")

    if r.status_code == 200:
        print(">>> CLAIM SUCCESS <<<")
        return "success"
    if is_already_claimed(result):
        print(">>> ALREADY CLAIMED <<<")
        return "claimed"
    if is_ip_limit(result):
        print(">>> IP LIMIT REACHED <<<")
        return "ip_limit"
    print(">>> CLAIM FAILED <<<")
    return "error"


# ============================================================
# RECEIVABLE / RECEIVE
# ============================================================

def get_receivable(address):
    result = rpc({
        "action": "receivable",
        "account": address,
        "count": "1",
        "source": "true",
        "include_only_confirmed": "false"
    })
    blocks = result.get("blocks", {})
    if not blocks:
        return None
    source_hash, info = next(iter(blocks.items()))
    amount = info.get("amount")
    if amount is None:
        return None
    # 🔥 پاک‌سازی hash هنگام دریافت
    clean = clean_hash(source_hash)
    return {"hash": clean, "amount": int(amount)}


def wait_for_pending(index, address):
    print()
    print("-" * 38)
    print(f"WAITING FOR PAYMENT - INDEX {index}")
    print("-" * 38)
    deadline = time.time() + PENDING_TIMEOUT
    while time.time() < deadline:
        try:
            pending = get_receivable(address)
            if pending:
                print(">>> PENDING FOUND <<<")
                print(f"source: {pending['hash']}")
                print(f"amount: {pending['amount']} raw")
                print(f"amount: {raw_to_xno(pending['amount'])} XNO")
                return pending
        except Exception as e:
            print(f"RPC check error: {e}")
        print(f"no payment yet -> retry in {PENDING_INTERVAL}s")
        time.sleep(PENDING_INTERVAL)
    print(">>> PENDING TIMEOUT <<<")
    return None


def receive(index, address, pending):
    print()
    print("=" * 38)
    print(f"RECEIVE INDEX {index}")
    print("=" * 38)

    acc = derive_account(index)
    source_hash = pending["hash"]
    amount = pending["amount"]
    
    # ============================================================
    # 🔥 FIX: پاک‌سازی نهایی hash
    # ============================================================
    print(f"source_hash (before): {repr(source_hash)}")
    
    # تبدیل bytes به string
    if isinstance(source_hash, bytes):
        source_hash = source_hash.decode("utf-8", errors="ignore")
    
    # فقط کاراکترهای hex
    source_hash = "".join(c for c in str(source_hash) if c in "0123456789abcdefABCDEF")
    
    print(f"source_hash (after):  {repr(source_hash)}")
    print(f"source_hash length:   {len(source_hash)}")
    print(f"amount:               {amount} raw")
    
    # بررسی طول hash
    if len(source_hash) != 64:
        raise RuntimeError(f"Invalid hash length: {len(source_hash)} (expected 64). Hash: {repr(source_hash)}")
    
    # تست تبدیل به bytes
    try:
        hash_bytes = bytes.fromhex(source_hash)
        print(f"hash_bytes length: {len(hash_bytes)} bytes")
    except ValueError as e:
        raise RuntimeError(f"Cannot convert hash to bytes: {e}. Hash: {repr(source_hash)}")
    # ============================================================

    # تلاش اول: با string
    rb = None
    try:
        print("Trying acc.receive(hash_=str, ...)...")
        rb = acc.receive(hash_=source_hash, raw_amt=amount)
        print("✅ Success with string hash")
    except Exception as e:
        print(f"❌ Failed with string hash: {e}")
        
        # تلاش دوم: با bytes
        try:
            print("Trying acc.receive(hash_=bytes, ...)...")
            rb = acc.receive(hash_=hash_bytes, raw_amt=amount)
            print("✅ Success with bytes hash")
        except Exception as e2:
            raise RuntimeError(f"Both attempts failed. str: {e}, bytes: {e2}")
    
    block = dict(rb.dict_)
    previous = block.get("previous", "0" * 64)

    if not previous or previous == "0" * 64:
        subtype = "open"
        root = acc.pk
    else:
        subtype = "receive"
        root = previous

    print(f"subtype: {subtype}")
    print(f"root:    {root}")
    print("generating Nano receive/open PoW...")

    work_int = nanopy.ext.work_generate(bytes.fromhex(root), RECEIVE_DIFFICULTY, secrets.token_bytes(128))
    work = f"{work_int:016x}"
    block["work"] = work
    print(f"work: {work}")

    validation = rpc({"action": "work_validate", "work": work, "hash": root})
    print(f"validation: {validation}")

    if str(validation.get("valid_receive")).lower() not in ("1", "true"):
        raise RuntimeError(f"Invalid receive PoW: {validation}")

    print(">>> POW VALID <<<")

    result = rpc({
        "action": "process",
        "json_block": "true",
        "subtype": subtype,
        "block": block
    })
    print(f"process result: {result}")

    block_hash = result.get("hash")
    if not block_hash:
        raise RuntimeError(f"No block hash returned: {result}")

    print(">>> RECEIVE SUCCESS <<<")
    print(f"block hash: {block_hash}")
    return block_hash


# ============================================================
# FINAL BALANCE
# ============================================================

def final_balance(items):
    if not items:
        print("\nNo address was successful, balance will not be displayed.")
        return

    print()
    print("=" * 38)
    print("FINAL BALANCES")
    print("=" * 38)

    addresses = [item["address"] for item in items]
    result = rpc({"action": "accounts_balances", "accounts": addresses, "include_only_confirmed": "false"})
    total_raw = 0

    for item in items:
        address = item["address"]
        info = result["balances"].get(address, {"balance": "0", "pending": "0"})
        balance_raw = int(info.get("balance", 0))
        pending_raw = int(info.get("pending", 0))
        total_raw += balance_raw
        print()
        print(f"index:      {item['index']}")
        print(f"address:    {address}")
        print(f"balance:    {balance_raw} raw = {raw_to_xno(balance_raw)} XNO")
        print(f"pending:    {pending_raw} raw = {raw_to_xno(pending_raw)} XNO")

    print()
    print("-" * 38)
    print(f"TOTAL: {raw_to_xno(total_raw)} XNO")
    print("-" * 38)


# ============================================================
# MAIN
# ============================================================

print()
print("=" * 38)
print(" FEELLESS402 CLAIM + RECEIVE")
print("=" * 38)
print()
print(f"Targets: {TARGETS}")
print(f"SEED: {SEED[:5]}... (hidden)")
print()

successful = []

for target in TARGETS:
    addr = target["address"]
    idx = target["index"]

    try:
        print()
        print("=" * 38)
        print(f"PROCESSING {addr} (index {idx})")
        print("=" * 38)

        status = claim(addr)

        if status == "success":
            item = {"index": idx, "address": addr}
            successful.append(item)
            print(f">>> SUCCESSFUL CLAIM for {addr}")

            pending = wait_for_pending(idx, addr)
            if pending:
                receive(idx, addr, pending)
            else:
                print(f"⚠️ payment not received for {addr} (index {idx}) - skipping receive")

        elif status == "ip_limit":
            print("Faucet IP limit reached. Stopping further attempts.")
            break

        else:
            print(f"⚠️ claim failed for {addr} (index {idx}) - status: {status} - skipping")

        time.sleep(2)

    except KeyboardInterrupt:
        print("\nStopped by user.")
        break
    except Exception as e:
        print(f"⚠️ ERROR on {addr}: {e} - skipping this address")
        continue


# ============================================================
# DISPLAY FINAL BALANCE
# ============================================================

if successful:
    try:
        final_balance(successful)
    except Exception as e:
        print(f"Final balance error: {e}")
else:
    print("\nNo successful claims.")

print()
print("=" * 38)
print("DONE")
print("=" * 38)
PY
