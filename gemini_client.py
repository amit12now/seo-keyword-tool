"""
gemini_client.py

Thin wrapper around the Gemini API used to enrich the raw DataForSEO data with:
- NLP / semantic keyword ideas, each scored 0-100 for relevance to the seed keyword
- Fan-out query ideas (follow-up / adjacent searches a user might run next),
  each scored 0-100 for relevance
- Relevance scores (0-100) for the People Also Ask questions DataForSEO returned

The relevance score is Gemini's own judgment of how closely an idea matches
the seed keyword's topic/intent - it is not a measured metric like search
volume, just a quick way to help prioritize a long list of ideas.

The API key is read from the GEMINI_API_KEY environment variable and is
never hardcoded.
"""

import os
import json

import google.generativeai as genai

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiError(Exception):
    """Raised when the Gemini API is misconfigured or returns an unusable response."""


def _get_model():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError(
            "Missing GEMINI_API_KEY. Add it to your .env file (see .env.example)."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(DEFAULT_MODEL)


def _build_prompt(seed_keyword: str, serp_data: dict) -> str:
    organic_titles = [r.get("title", "") for r in serp_data.get("organic_results", [])]
    paa = serp_data.get("people_also_ask", [])
    related = serp_data.get("related_keywords", [])

    return f"""You are an SEO research assistant. Analyze the seed keyword and the
Google SERP data below, then respond with STRICT JSON only (no markdown, no
commentary, no code fences).

Seed keyword: "{seed_keyword}"

Top organic result titles:
{json.dumps(organic_titles, indent=2)}

People Also Ask questions (score these exact questions, do not reword them):
{json.dumps(paa, indent=2)}

Related searches:
{json.dumps(related, indent=2)}

Return JSON with exactly this shape:
{{
  "nlp_keywords": [
    {{"keyword": "semantic/NLP keyword or entity relevant to the topic", "relevance": 0}}
  ],
  "fan_out_queries": [
    {{"query": "a natural follow-up or adjacent query a searcher might ask next", "relevance": 0}}
  ],
  "paa_relevance": [
    {{"question": "<exact question text, copied verbatim from the People Also Ask list above>", "relevance": 0}}
  ]
}}

Rules:
- "relevance" is an integer 0-100: how closely the item matches the seed
  keyword's topic and search intent (100 = extremely relevant, 0 = unrelated).
- Provide 8-12 items for "nlp_keywords" and 8-12 items for "fan_out_queries".
- "paa_relevance" must contain exactly one entry per question in the People
  Also Ask list above, in the same order, with the question text copied
  verbatim (do not paraphrase or reorder them). If the list above is empty,
  return an empty array for "paa_relevance".
"""


def generate_keyword_insights(seed_keyword: str, serp_data: dict) -> dict:
    """
    Calls Gemini with the seed keyword + SERP context and returns a dict:
      {
        "nlp_keywords": [{"keyword": str, "relevance": int}, ...],
        "fan_out_queries": [{"query": str, "relevance": int}, ...],
        "paa_relevance": [{"question": str, "relevance": int}, ...],
      }

    "paa_relevance" is aligned by position with the People Also Ask list that
    was passed in via serp_data["people_also_ask"] - callers should zip them
    together by index rather than by matching text.
    """
    model = _get_model()
    prompt = _build_prompt(seed_keyword, serp_data)

    try:
        response = model.generate_content(prompt)
    except Exception as exc:  # noqa: BLE001 - surface any SDK error to the UI
        raise GeminiError(f"Gemini API request failed: {exc}") from exc

    raw_text = (response.text or "").strip()

    # Strip accidental markdown code fences, just in case the model adds them.
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:].strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise GeminiError(
            f"Could not parse Gemini response as JSON: {exc}\nRaw response: {raw_text[:500]}"
        ) from exc

    def _clean_scored_list(items, text_key):
        cleaned = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            text = item.get(text_key)
            if not text:
                continue
            try:
                relevance = int(item.get("relevance"))
            except (TypeError, ValueError):
                relevance = None
            cleaned.append({text_key: text, "relevance": relevance})
        return cleaned

    return {
        "nlp_keywords": _clean_scored_list(parsed.get("nlp_keywords"), "keyword"),
        "fan_out_queries": _clean_scored_list(parsed.get("fan_out_queries"), "query"),
        "paa_relevance": _clean_scored_list(parsed.get("paa_relevance"), "question"),
    }
