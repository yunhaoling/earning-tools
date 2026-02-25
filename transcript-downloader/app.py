import datetime
import os
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, url_for

from download import (
    convert_page_to_pdf,
    download_pdf_directly,
    is_pdf_url,
    load_config,
)

app = Flask(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"
config = load_config(CONFIG_PATH)
OUTPUT_DIR = Path(config.get("output_dir", "./output"))
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = CONFIG_PATH.parent / OUTPUT_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Transcript Downloader</title>
    <style>
        body { font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }
        h1 { margin-bottom: 24px; }
        label { display: block; margin-top: 14px; font-weight: bold; }
        input[type=text], select { width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; }
        .row { display: flex; gap: 16px; }
        .row > div { flex: 1; }
        button { margin-top: 24px; padding: 10px 24px; font-size: 16px; cursor: pointer; }
        .msg { margin-top: 20px; padding: 12px; border-radius: 4px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>Transcript Downloader</h1>
    {% if message %}
    <div class="msg {{ msg_class }}">{{ message }}</div>
    {% endif %}
    <form method="post" action="/download">
        <label for="url">URL</label>
        <input type="text" id="url" name="url" required value="{{ form.url or '' }}">

        <label for="ticker">Ticker</label>
        <input type="text" id="ticker" name="ticker" required value="{{ form.ticker or '' }}">

        <div class="row">
            <div>
                <label for="year">Year</label>
                <select id="year" name="year">
                    {% for y in years %}
                    <option value="{{ y }}" {{ 'selected' if form.year|string == y|string else '' }}>{{ y }}</option>
                    {% endfor %}
                </select>
            </div>
            <div>
                <label for="quarter">Quarter</label>
                <select id="quarter" name="quarter">
                    {% for q in [1,2,3,4] %}
                    <option value="{{ q }}" {{ 'selected' if form.quarter|string == q|string else '' }}>Q{{ q }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <label for="doc_type">Type</label>
        <select id="doc_type" name="doc_type">
            <option value="1" {{ 'selected' if form.doc_type == '1' else '' }}>Transcript</option>
            <option value="2" {{ 'selected' if form.doc_type == '2' else '' }}>Earnings Release</option>
        </select>

        <button type="submit">Download</button>
    </form>
    <button type="button" onclick="fetch('/open-folder', {method: 'POST'})" style="background: none; border: 1px solid #ccc; margin-top: 8px; padding: 10px 24px; font-size: 16px; cursor: pointer;">Open Output Folder</button>
</body>
</html>
"""

CURRENT_YEAR = datetime.date.today().year
YEARS = list(range(CURRENT_YEAR + 2, CURRENT_YEAR - 6, -1))


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        TEMPLATE,
        message=None,
        msg_class="",
        form={"year": str(CURRENT_YEAR)},
        years=YEARS,
    )


@app.route("/download", methods=["POST"])
def download():
    form = request.form
    url = form.get("url", "").strip()
    ticker = form.get("ticker", "").strip().upper()
    year = form.get("year", "")
    quarter = form.get("quarter", "")
    doc_type = form.get("doc_type", "1")

    if not url or not ticker:
        return render_template_string(
            TEMPLATE,
            message="URL and Ticker are required.",
            msg_class="error",
            form=form,
            years=YEARS,
        )

    try:
        year_int = int(year)
        quarter_int = int(quarter)
    except ValueError:
        return render_template_string(
            TEMPLATE,
            message="Invalid year or quarter.",
            msg_class="error",
            form=form,
            years=YEARS,
        )

    type_suffix = "_transcript" if doc_type == "1" else "_earning_release"
    filename = f"{year_int}_Q{quarter_int}_{ticker}{type_suffix}.pdf"
    output_path = OUTPUT_DIR / ticker / str(year_int) / f"Q{quarter_int}" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if is_pdf_url(url):
            download_pdf_directly(url, output_path)
        else:
            convert_page_to_pdf(url, output_path)
    except Exception as e:
        return render_template_string(
            TEMPLATE,
            message=f"Download failed: {e}",
            msg_class="error",
            form=form,
            years=YEARS,
        )

    return render_template_string(
        TEMPLATE,
        message=f"Saved: {ticker}/{year_int}/Q{quarter_int}/{filename}",
        msg_class="success",
        form=form,
        years=YEARS,
    )


@app.route("/open-folder", methods=["POST"])
def open_folder():
    os.startfile(OUTPUT_DIR)
    return "", 204


if __name__ == "__main__":
    app.run(debug=True)
