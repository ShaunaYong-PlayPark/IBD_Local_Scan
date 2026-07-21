from candidate_store import write_report_period_outputs


def main():
    selected, metadata_path, layer2_path = write_report_period_outputs()
    print("Report-period candidate preparation complete.")
    print(f"Selected stored candidates: {len(selected)}")
    print(f"Metadata for Layer 4/final report: {metadata_path}")
    print(f"Ranking evidence for final report: {layer2_path}")


if __name__ == "__main__":
    main()
