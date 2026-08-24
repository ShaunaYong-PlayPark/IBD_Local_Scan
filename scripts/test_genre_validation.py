import csv
from pathlib import Path

import export_static_dashboard as exporter
from test_temp_utils import repo_temp_dir


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def write_reference(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["report_name", "genre", "genre_source_url"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    with repo_temp_dir("genre_validation_") as temp:
        reference = Path(temp) / "game_genre_sources.csv"

        write_reference(reference, [{"report_name": "Missing Genre", "genre": "RPG", "genre_source_url": "https://example.com/rpg"}])
        failures = exporter.genre_validation_failures([{"Game Title": "Missing Genre", "Genre": ""}], reference)
        assert_true("Missing Genre" in failures[0] and "missing or generic genre" in failures[0], "missing genre must fail validation")

        write_reference(reference, [{"report_name": "Generic Genre", "genre": "Game", "genre_source_url": "https://example.com/game"}])
        failures = exporter.genre_validation_failures([{"Game Title": "Generic Genre", "Genre": "Game"}], reference)
        assert_true("Generic Genre" in failures[0] and "missing or generic genre" in failures[0], "generic Game genre must fail validation")

        write_reference(reference, [{"report_name": "Missing Source", "genre": "RPG", "genre_source_url": ""}])
        failures = exporter.genre_validation_failures([{"Game Title": "Missing Source", "Genre": "RPG"}], reference)
        assert_true("Missing Source" in failures[0] and "missing genre_source_url" in failures[0], "missing genre source must fail validation")

        try:
            exporter.require_valid_game_genres([{"Game Title": "Missing Source", "Genre": "RPG"}], reference)
        except ValueError as error:
            assert_true("Genre validation failed" in str(error) and "Missing Source" in str(error), "validation error must list the failing title")
        else:
            raise AssertionError("invalid genre data must stop report generation")

    print("GENRE_VALIDATION_PASS")


if __name__ == "__main__":
    main()
