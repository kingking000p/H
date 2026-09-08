from pathlib import Path
import os
import stat

# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_FILE = BASE_DIR / "template.sh"
ADDRESSES_FILE = BASE_DIR / "addresses.txt"
OUTPUT_FILE = BASE_DIR / "script.sh"

BATCH_SIZE = 3

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
                    f"ERROR: index is not an integer at line {line_no}: {index_text}"
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

    # Make sure no placeholders remain.
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

    # chmod +x
    current_mode = OUTPUT_FILE.stat().st_mode
    OUTPUT_FILE.chmod(
        current_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("======================================")
    print(" FIRST BATCH GENERATOR")
    print("======================================")
    print()

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

    script = build_first_batch(template, records)

    write_output(script)

    # Verify output exists and is non-empty.
    if not OUTPUT_FILE.exists():
        raise SystemExit("ERROR: script.sh was not created")

    if OUTPUT_FILE.stat().st_size == 0:
        raise SystemExit("ERROR: script.sh is empty")

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
    print("DONE")
    print("======================================")


if __name__ == "__main__":
    main()
