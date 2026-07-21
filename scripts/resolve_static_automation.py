import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_PATH = ROOT / "config" / "static_report_schedule.json"
SETTINGS_EXAMPLE_PATH = ROOT / "config" / "settings.example.json"
SETTINGS_PATH = ROOT / "config" / "settings.json"

MODES = {
    "static-export-only",
    "weekly-capture",
    "meeting-day-final-report",
    "auto",
}


def read_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def parse_iso_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def weekday_name(value):
    return str(value or "").strip().lower()


def current_schedule_date(schedule):
    override = os.environ.get("STATIC_AUTOMATION_DATE", "").strip()
    if override:
        return parse_iso_date(override)
    try:
        tz = ZoneInfo(schedule.get("timezone") or "Asia/Singapore")
    except ZoneInfoNotFoundError:
        tz = timezone(timedelta(hours=8))
    return datetime.now(tz).date()


def report_dates(schedule):
    start = parse_iso_date(schedule["last_completed_meeting_date"])
    meeting = parse_iso_date(schedule["upcoming_meeting_date"])
    end = meeting - timedelta(days=1)
    offset = int(schedule.get("meeting_day_final_report", {}).get("ranking_date_offset_days", 1))
    ranking = end - timedelta(days=offset)
    return start, end, ranking


def resolve_auto_mode(schedule, today):
    meeting_config = schedule.get("meeting_day_final_report", {})
    weekly_config = schedule.get("weekly_candidate_capture", {})
    meeting = parse_iso_date(schedule["upcoming_meeting_date"])

    if meeting_config.get("enabled", True) and today == meeting:
        return "meeting-day-final-report"

    weekly_day = weekday_name(weekly_config.get("weekday", "Sunday"))
    if weekly_config.get("enabled", True) and today.strftime("%A").lower() == weekly_day:
        return "weekly-capture"

    return "static-export-only"


def write_runtime_settings(schedule):
    settings = read_json(SETTINGS_EXAMPLE_PATH)
    start, end, ranking = report_dates(schedule)
    settings["report_start_date"] = start.isoformat()
    settings["report_end_date"] = end.isoformat()
    settings["ranking_date"] = ranking.isoformat()
    write_json(SETTINGS_PATH, settings)
    return start, end, ranking


def write_github_output(values):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main():
    parser = argparse.ArgumentParser(description="Resolve static dashboard automation mode from committed schedule config.")
    parser.add_argument("--mode", choices=sorted(MODES), default="auto")
    args = parser.parse_args()

    schedule = read_json(SCHEDULE_PATH)
    today = current_schedule_date(schedule) if args.mode == "auto" else None
    mode = resolve_auto_mode(schedule, today) if args.mode == "auto" else args.mode
    start, end, ranking = write_runtime_settings(schedule)
    live_required = "true" if mode in {"weekly-capture", "meeting-day-final-report"} else "false"

    values = {
        "mode": mode,
        "live_required": live_required,
        "today": today.isoformat() if today else "",
        "report_start_date": start.isoformat(),
        "report_end_date": end.isoformat(),
        "ranking_date": ranking.isoformat(),
        "meeting_date": schedule.get("upcoming_meeting_date", ""),
    }
    write_github_output(values)
    for key, value in values.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
