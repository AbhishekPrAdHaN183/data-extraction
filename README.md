# Project 7: Industry-Oriented Python Web Scraping and Data Extraction System

A comprehensive, self-contained Python web scraping and data extraction system built to simulate industrial workflows. The system features a robust, multi-threaded crawler engine, a data cleaning and validation pipeline, a built-in mock industrial parts catalog sandbox, and a premium glassmorphism web dashboard.

---

## 🌟 Key Features

1. **Robust Web Scraper Engine**:
   - Rotates User-Agent headers to bypass simple bot block gates.
   - Retries failed requests (429, 500, 502, 503, 504) with exponential backoff.
   - Enforces adjustable rate-limiting request delays with random jitter variance (+/- 20%) to mimic natural browser behaviors.
2. **Ethical Compliance Systems**:
   - Parses and respects `robots.txt` rules automatically.
   - Detects and avoids hidden "honeypot" trap links dynamically using inline CSS attribute checks (e.g. `display: none`, `visibility: hidden`, opacity, tiny elements).
3. **Data Pipeline & Schema Validation**:
   - Cleans formatting: strips HTML tags, removes duplicate whitespace.
   - Standardizes currency (e.g. `"$1,850.00"` -> `1850.0`), stock units, and customer star rating values.
   - Checks records against a schema (requires names, validates SKU alphanumeric formats).
4. **Built-in Mock Sandbox Server**:
   - FastAPI server replicating an industrial supply parts portal ("Apex Industrial Supplies").
   - Implements multi-page pagination, dynamic element values (stock/rating) loaded asynchronously via client-side AJAX, rate-limiting response codes, and honeypot traps that ban bots for 60 seconds.
5. **Premium Web Dashboard**:
   - Web console styled with slate-dark glassmorphism, glowing accents, and an interactive interface.
   - Real-time logging terminal displaying crawling and API activities via live-updated streams.
   - Live interactive data grid showing extracted details with sorting and text filtering.
   - Integrated exports downloading data in CSV or Excel (`.xlsx`) formats.

---

## 📂 Project Structure

```
pg7/
├── main.py                     # Main launcher (runs Server Dashboard or CLI mode)
├── requirements.txt            # Package dependencies
├── README.md                   # Project documentation
├── src/
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── engine.py           # HTTP Request agent, Robots.txt, and Rate Limiter
│   │   ├── parser.py           # BeautifulSoup parser & Honeypot Detector
│   │   ├── pipeline.py         # Data cleaners, schemas validator, & CSV/Excel writers
│   │   └── manager.py          # Crawler coordinator & Dashboard log queue handler
│   ├── sandbox/
│   │   ├── __init__.py
│   │   └── server.py           # FastAPI Sandbox portal & Scraper controller API
│   └── dashboard/
│       └── templates/
│           └── index.html      # Premium glassmorphism dashboard UI page
└── tests/
    └── test_scraper.py         # Automated pytest suite
```

---

## 🚀 Getting Started

### 1. Install Dependencies

Install the required packages using pip:
```bash
pip install fastapi uvicorn requests beautifulsoup4 lxml pandas openpyxl pytest
```

### 2. Run the Web Dashboard & Sandbox (Recommended)

Start the unified server:
```bash
python main.py
```
Open your browser and navigate to:
- **Scraper Dashboard**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)
- **Mock Industrial Sandbox**: [http://127.0.0.1:8000/sandbox](http://127.0.0.1:8000/sandbox)

### 3. Run the Scraper via CLI

You can execute the scraper directly in your terminal without starting the web dashboard:
```bash
# Start a default crawl targeting the local sandbox and export to CSV
python main.py --cli

# Target a custom starting URL with a custom crawl delay of 2.0 seconds and export to Excel
python main.py --cli --url "http://localhost:8000/sandbox" --delay 2.0 --export excel --output exports/products_data.xlsx

# Ignore robots.txt checks and User-Agent rotations
python main.py --cli --no-robots --no-rotate
```

#### CLI Command Options:
* `--cli`: Run in Command Line Interface mode directly.
* `--url`: Starting URL index to crawl.
* `--delay`: Wait time (seconds) between request dispatches.
* `--no-robots`: Ignore `robots.txt` crawler exclusion paths.
* `--no-rotate`: Disable random rotation of browser headers.
* `--export`: Export format, options are `csv` or `excel` (default: `csv`).
* `--output`: Output filepath.

---

## 🧪 Running Automated Tests

Run the test suite using `pytest` with Python's module path option to verify all components:
```bash
python -m pytest tests/
```
The test suite validates:
* Inline CSS honeypot link identification.
* Product detail parsing, categorizations, and link harvesting.
* Price float standardizer, numeric stock extractions, star symbols cleaners, and whitespace trim.
* Mock file CSV & Excel table exporters.

---

## 🛡️ Ethical Scraping Practices Implemented

* **Exclusion respect**: Reads and checks target domain `/robots.txt` paths before making request dispatches.
* **Non-disruptive rate-limits**: Limits request speeds, adding random variance to distribute traffic load gently over target servers.
* **Retry backoffs**: Prevents hammering servers when rate-limits or temporary HTTP server errors are hit by waiting and backing off exponentially.
* **Honeypot detection**: Inspects layout markers (`display:none`, visibility tags, tiny bounds) to respect honeypots and bypass traps ethically.
