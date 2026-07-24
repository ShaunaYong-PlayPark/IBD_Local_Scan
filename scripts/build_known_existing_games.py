import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "reference" / "historical_top_games_raw"
OUTPUT_CSV = ROOT / "data" / "reference" / "known_existing_games.csv"

OUTPUT_FIELDS = [
    "platform",
    "app_id",
    "unified_app_id",
    "unified_name",
    "app_name",
    "first_known_date",
    "last_known_date",
    "source_file_count",
]

PLATFORM_MAP = {
    "App Store": "ios",
    "Google Play": "android",
}


def clean(value):
    return str(value or "").strip()


def normalise_platform(value):
    return PLATFORM_MAP.get(clean(value), "")


def raw_encoding(path):
    with path.open("rb") as handle:
        prefix = handle.read(4)
    if prefix.startswith(b"\xff\xfe") or prefix.startswith(b"\xfe\xff"):
        return "utf-16"
    return "utf-8-sig"


def read_raw_rows():
    files = sorted(RAW_DIR.glob("*.csv"))
    total_rows = 0
    excluded_rows = 0
    grouped = {}
    source_files_by_key = defaultdict(set)

    for path in files:
        with path.open("r", encoding=raw_encoding(path), newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                total_rows += 1
                platform = normalise_platform(row.get("Platform"))
                app_id = clean(row.get("App ID"))
                unified_app_id = clean(row.get("Unified ID"))
                date = clean(row.get("Date"))
                if not platform or not app_id or not unified_app_id:
                    excluded_rows += 1
                    continue

                key = (platform, app_id)
                source_files_by_key[key].add(path.name)
                existing = grouped.get(key)
                if existing is None:
                    grouped[key] = {
                        "platform": platform,
                        "app_id": app_id,
                        "unified_app_id": unified_app_id,
                        "unified_name": clean(row.get("Unified Name")),
                        "app_name": clean(row.get("App Name")),
                        "first_known_date": date,
                        "last_known_date": date,
                    }
                    continue

                if date and (
                    not existing["first_known_date"] or date < existing["first_known_date"]
                ):
                    existing["first_known_date"] = date
                    existing["unified_name"] = clean(row.get("Unified Name")) or existing["unified_name"]
                    existing["app_name"] = clean(row.get("App Name")) or existing["app_name"]
                if date and (
                    not existing["last_known_date"] or date > existing["last_known_date"]
                ):
                    existing["last_known_date"] = date
                if not existing["unified_name"]:
                    existing["unified_name"] = clean(row.get("Unified Name"))
                if not existing["app_name"]:
                    existing["app_name"] = clean(row.get("App Name"))
                if not existing["unified_app_id"]:
                    existing["unified_app_id"] = unified_app_id

    rows = []
    for key, row in grouped.items():
        row = dict(row)
        row["source_file_count"] = len(source_files_by_key[key])
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row["platform"],
            row["first_known_date"],
            row["unified_name"].casefold(),
            row["app_id"],
        )
    )
    return files, total_rows, excluded_rows, rows


def write_output(rows):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def print_samples(rows):
    for platform in ("ios", "android"):
        print(f"sample_{platform}:")
        for row in [row for row in rows if row["platform"] == platform][:3]:
            print(
                "  "
                f"{row['platform']}\t{row['app_id']}\t{row['unified_app_id']}\t"
                f"{row['unified_name']}\t{row['first_known_date']}\t{row['last_known_date']}"
            )


def main():
    files, total_rows, excluded_rows, rows = read_raw_rows()
    write_output(rows)
    unique_unified_ids = {row["unified_app_id"] for row in rows}

    print("KNOWN_EXISTING_GAMES_BUILD_COMPLETE")
    print(f"raw_file_count={len(files)}")
    print(f"total_raw_rows_read={total_rows}")
    print(f"output_row_count={len(rows)}")
    print(f"unique_unified_app_id_count={len(unique_unified_ids)}")
    print(f"excluded_row_count={excluded_rows}")
    print(f"output={OUTPUT_CSV}")
    print_samples(rows)


if __name__ == "__main__":
    main()
