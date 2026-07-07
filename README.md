# SEO Keyword Research Tool

Internal Streamlit dashboard for keyword research, styled after a light,
Ahrefs-style keyword overview page. Enter a seed keyword, pick a location and
language in the top search bar, and get:

- A keyword-difficulty gauge (color-coded Easy/Medium/Hard/Very Hard)
- Search volume with a 12-month trend bar chart, CPC, and competition level
  (DataForSEO Labs)
- A 2x2 "Keyword Ideas" grid: Secondary (related) Keywords with search
  volume, NLP/Semantic Keywords, Fan-out Queries, and People Also Ask — the
  last three scored 0-100 for relevance by DeepSeek
- An **Answer Engine Optimization (AEO)** section:
  - **Answer Snippet Lab** — DeepSeek classifies the seed keyword's search
    intent (Definition / Comparison / Process / List / Yes-No) and writes an
    answer in the format an AI answer engine or featured snippet would
    actually extract (a 40-60 word paragraph, an ordered step list, or a
    comparison table), plus an extraction-readiness score (0-100) with short
    reasons and a length indicator (words/steps/rows vs. the ideal range)
  - **FAQ Answers** — a concise, self-contained answer for every People Also
    Ask question, each with its own relevance score
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
   - `DEEPSEEK_API_KEY` — from the DeepSeek Platform (platform.deepseek.com)
   - `DEEPSEEK_MODEL` — optional, defaults to `deepseek-v4-flash`

   The `.env` file is git-ignored and credentials are never hardcoded in the code.

## Run

```
streamlit run app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501). Enter a
keyword in the top search bar and click **Search**.

## Files

- `app.py` — Streamlit dashboard UI
- `dataforseo_client.py` — DataForSEO API calls:
  - SERP (organic results, People Also Ask, related searches)
  - Labs Keyword Overview (search volume, CPC, competition, difficulty, monthly trend)
- `deepseek_client.py` — DeepSeek API calls: NLP keywords, fan-out queries, PAA
  relevance + answers, and the AEO answer snippet (intent, format-matched
  text, extraction score)
- `requirements.txt` — Python dependencies
- `.env.example` — template for required environment variables
- `.gitignore` — excludes `.env` and other local artifacts
- `.streamlit/config.toml` — light theme configuration

## Notes

- Locations available: United States, United Arab Emirates, Saudi Arabia,
  Oman, Qatar, Iraq. Languages available: English, Arabic. Add more by
  editing the `LOCATIONS` and `LANGUAGES` dictionaries in `app.py`.
- Only the primary keyword plus the first `MAX_SECONDARY_TO_ENRICH` (default
  12) secondary keywords are looked up for search volume/CPC/trend, to keep
  the extra API call fast and cheap.
- The AEO answer snippet and FAQ answers are DeepSeek's best judgment of what
  an AI answer engine would extract/cite — not a guarantee of appearing in
  any specific answer engine, and not sourced from DataForSEO.
- Each DataForSEO call (SERP + Labs) costs API credits — check your
  DataForSEO plan/pricing.
- The keyword-difficulty gauge, search volume, CPC, and competition metrics
  come from DataForSEO Labs' Keyword Overview endpoint, not Ahrefs — values
  and methodology will differ from Ahrefs' own Keyword Difficulty score.
