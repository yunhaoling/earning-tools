import argparse
import re
import sys
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright


def parse_quarter(raw: str) -> tuple[int, int]:
    """Parse flexible quarter format into (year, quarter_number).

    Supported formats: Q1_2025, 2025Q1, 2025_Q1, q12025, Q22024, etc.
    """
    raw = raw.strip()

    # Try Q<n><sep><year> patterns: Q1_2025, Q12025, q1 2025
    m = re.match(r"[Qq]([1-4])[\s_-]*(\d{4})$", raw)
    if m:
        return int(m.group(2)), int(m.group(1))

    # Try <year><sep>Q<n> patterns: 2025Q1, 2025_Q1, 2025 q1
    m = re.match(r"(\d{4})[\s_-]*[Qq]([1-4])$", raw)
    if m:
        return int(m.group(1)), int(m.group(2))

    print(f"Error: cannot parse quarter '{raw}'.")
    print("Expected formats: Q1_2025, 2025Q1, 2025_Q1, q12025, etc.")
    sys.exit(1)


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}")
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def download_to_pdf(url: str, output_path: Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.pdf(path=str(output_path))
        browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="Download an earnings call transcript as PDF."
    )
    parser.add_argument("--url", required=True, help="Transcript page URL")
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. AAPL)")
    parser.add_argument(
        "--quarter",
        required=True,
        help="Earnings quarter (e.g. Q1_2025, 2025Q1)",
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).parent / "config.yaml"),
        help="Path to config.yaml (default: config.yaml in script dir)",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    output_dir = Path(config.get("output_dir", "./output"))
    if not output_dir.is_absolute():
        output_dir = config_path.parent / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    year, quarter = parse_quarter(args.quarter)
    ticker = args.ticker.upper()
    filename = f"{year}_Q{quarter}_{ticker}.pdf"
    output_path = output_dir / filename

    print(f"Downloading: {args.url}")
    print(f"Saving to:   {output_path}")

    download_to_pdf(args.url, output_path)
    print("Done.")


if __name__ == "__main__":
    main()
