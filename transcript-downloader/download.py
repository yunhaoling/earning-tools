import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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

    raise ValueError(
        f"Cannot parse quarter '{raw}'. "
        "Expected formats: Q1_2025, 2025Q1, 2025_Q1, q12025, etc."
    )


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def is_pdf_url(url: str) -> bool:
    """Check if URL points directly to a PDF via URL extension or HEAD request."""
    # Fast path: check URL extension
    path = urlparse(url).path
    if path.lower().endswith(".pdf"):
        return True
    # Fallback: HEAD request to check Content-Type
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            return "application/pdf" in content_type
    except Exception:
        return False


def download_pdf_directly(url: str, output_path: Path) -> None:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
        if not data[:5] == b"%PDF-":
            raise Exception("Not a valid PDF")
        output_path.write_bytes(data)
    except Exception:
        # Server blocked urllib; fall back to real Chrome browser
        _download_pdf_via_browser(url, output_path)


def _download_pdf_via_browser(url: str, output_path: Path) -> None:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page()
        # Visit the parent site first to acquire Akamai session cookies
        page.goto(origin, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        # Now fetch the PDF using the browser context (shares cookies + TLS)
        resp = page.context.request.get(url)
        if resp.status != 200:
            raise Exception(f"Download failed: HTTP {resp.status}")
        body = resp.body()
        if body[:5] != b"%PDF-":
            raise Exception("Server returned an error page instead of a PDF")
        output_path.write_bytes(body)
        browser.close()


def convert_page_to_pdf(url: str, output_path: Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
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
        "--type",
        required=True,
        type=int,
        choices=[1, 2],
        help="Document type: 1 = transcript, 2 = earnings release",
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
    type_suffix = "_transcript" if args.type == 1 else "_earning_release"
    filename = f"{year}_Q{quarter}_{ticker}{type_suffix}.pdf"
    output_path = output_dir / ticker / str(year) / f"Q{quarter}" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading: {args.url}")
    print(f"Saving to:   {output_path}")

    if is_pdf_url(args.url):
        print("Detected direct PDF link, downloading...")
        download_pdf_directly(args.url, output_path)
    else:
        print("HTML page detected, converting to PDF...")
        convert_page_to_pdf(args.url, output_path)
    print("Done.")


if __name__ == "__main__":
    main()
