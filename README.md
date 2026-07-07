# SEO Keyword Research Tool

Internal Streamlit dashboard for keyword research, styled after a light,
Ahrefs-style keyword overview page. Enter a seed keyword, pick a location and
language, and get:

- A keyword-difficulty gauge (color-coded Easy/Medium/Hard/Very Hard)
- Search volume with a 12-month trend bar chart, CPC, and competition level
  (DataForSEO Labs)
- A primary keyword confirmation (Gemini)
- A 4-column "Keyword Ideas" grid: Related Keywords (with search volume where
  available), NLP/Semantic Keywords, Fan-out Queries, and People Also Ask
- Top 10 Google organic results (DataForSEO)

No export, no database, no login.

## Setup

1. Create a virtual environment (optional but recommended):

   ```
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your credentials:

   ```
   cp .env.example .env
   ```

   - `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` — from your DataForSEO account
   - `GEMINI_API_KEY` — from Google AI Studio
   - `GEMINI_MODEL` — optional, defaults to `gemini-2.5-flash`

   The `.env` file is git-ignored and credentials are never hardcoded in the code.

## Run

```
streamlit run app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501). Enter a
keyword in the sidebar and click **Search**.

## Files

- `app.py` — Streamlit dashboard UI
- `dataforseo_client.py` — DataForSEO API calls:
  - SERP (organic results, People Also Ask, related searches)
  - Labs Keyword Overview (search volume, CPC, competition, difficulty, monthly trend)
- `gemini_client.py` — Gemini API calls (primary keyword confirmation, NLP keywords, fan-out queries)
- `requirements.txt` — Python dependencies
- `.env.example` — template for required environment variables
- `.gitignore` — excludes `.env` and other local artifacts
- `.streamlit/config.toml` — light theme configuration

## Notes

- Locations available: United States, United Arab Emirates, Saudi Arabia,
  Oman, Qatar, Iraq. Languages available: English, Arabic. Add more by
  editing the `LOCATIONS` and `LANGUAGES` dictionaries in `app.py`.
- Only the primary keyword plus the first `MAX_KEYWORDS_TO_ENRICH` (default
  12) related keywords are looked up for search volume/CPC/trend, to keep the
  extra API call fast and cheap.
- Each DataForSEO call (SERP + Labs) costs API credits — check your
  DataForSEO plan/pricing.
- The keyword-difficulty gauge, search volume, CPC, and competition metrics
  come from DataForSEO Labs' Keyword Overview endpoint, not Ahrefs — values
  and methodology will differ from Ahrefs' own Keyword Difficulty score.
