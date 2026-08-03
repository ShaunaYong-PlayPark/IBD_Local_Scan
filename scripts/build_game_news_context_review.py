import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEETING_PACK_OUTPUT_ROOT = ROOT / "data" / "output" / "meeting_pack"
RAW_FILENAME = "news_context_layer.csv"
REVIEW_FILENAME = "news_context_review.csv"
REVIEW_FIELDS = [
    "include_in_final_report",
    "final_report_section",
    "editor_decision",
    "editor_note",
]


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def raw_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / RAW_FILENAME


def review_path(meeting_date):
    return MEETING_PACK_OUTPUT_ROOT / meeting_date / REVIEW_FILENAME


def row_key(row):
    return str(row.get("url") or row.get("title_en") or row.get("title") or "").strip()


def build(meeting_date):
    source = raw_path(meeting_date)
    destination = review_path(meeting_date)
    raw_rows = read_csv(source)
    existing = {}
    if destination.exists():
        existing = {row_key(row): row for row in read_csv(destination) if row_key(row)}

    rows = []
    fields = list(raw_rows[0].keys()) if raw_rows else []
    for raw in raw_rows:
        row = dict(raw)
        prior = existing.get(row_key(raw), {})
        for field in REVIEW_FIELDS:
            row[field] = prior.get(field, "")
        rows.append(row)
    write_csv(destination, rows, fields + REVIEW_FIELDS)
    return destination, rows


def main():
    parser = argparse.ArgumentParser(description="Create a manual review copy of Game News context rows.")
    parser.add_argument("--meeting-date", required=True)
    args = parser.parse_args()
    path, rows = build(args.meeting_date)
    print(f"News context review rows: {len(rows)}")
    print(f"Output path: {path}")


if __name__ == "__main__":
    main()
