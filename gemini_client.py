"""
gemini_client.py

Thin wrapper around the Gemini API used to enrich the raw DataForSEO data with:
- NLP / semantic keyword ideas, each scored 0-100 for relevance to the seed keyword
- Fan-out query ideas (follow-up / adjacent searches a user might run next),
  each scored 0-100 for relevance
- Relevance scores (0-100) AND a concise answer for each People Also Ask
  question DataForSEO returned (Answer Engine Optimization / AEO data)
- An "answer snippet" for the seed keyword itself: the query intent
  (Definition / Comparison / Process / List / Yes-No), a snippet written in
  the format an AI answer engine or featured snippet would actually extract
  (paragraph, ordered steps, or a comparison table), and an extraction-
  readiness score with short reasons.

The relevance and extraction-readiness scores are Gemini's own judgment of
fit/quality - they are not measured metrics like search volume, just a quick
way to help prioritize a long list of ideas. Word counts are computed in
Python from the returned text, not trusted from the model.

The API key is read from the GEMINI_API_KEY environment variable and is
never hardcoded.
"""

import os
import json

import google.generativeai as genai

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

VALID_INTENTS = {"Definition", "Comparison", "Process", "List", "Yes/No"}
VALID_FORMATS = {"paragraph", "steps", "table"}


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

    return f"""You are an SEO and Answer Engine Optimization (AEO) research assistant.
AEO means optimizing content so AI answer engines (Google AI Overviews,
ChatGPT, Perplexity, voice assistants) are likely to extract and cite it,
not just rank it in blue links. Analyze the seed keyword and the Google SERP
data below, then respond with STRICT JSON only (no markdown, no commentary,
no code fences).

Seed keyword: "{seed_keyword}"

Top organic result titles:
{json.dumps(organic_titles, indent=2)}

People Also Ask questions (answer and score these exact questions, do not reword them):
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
    {{
      "question": "<exact question text, copied verbatim from the People Also Ask list above>",
      "relevance": 0,
      "answer": "a concise 40-60 word answer to this exact question, self-contained and quotable"
    }}
  ],
  "answer_snippet": {{
    "intent_type": "one of: Definition, Comparison, Process, List, Yes/No - the seed keyword's dominant search intent",
    "format": "one of: paragraph, steps, table - the format an AI answer engine would actually extract for this intent",
    "paragraph": "40-60 word direct-answer paragraph, ONLY if format is paragraph, else null",
    "steps": ["short imperative step 1", "short imperative step 2", "..."] ,
    "table_headers": ["Column A", "Column B"],
    "table_rows": [["row1 col A", "row1 col B"], ["row2 col A", "row2 col B"]],
    "extraction_score": 0,
    "score_reasons": ["short reason 1 (under 12 words)", "short reason 2 (under 12 words)"]
  }}
}}

Rules:
- "relevance" is an integer 0-100: how closely the item matches the seed
  keyword's topic and search intent (100 = extremely relevant, 0 = unrelated).
- Provide 8-12 items for "nlp_keywords" and 8-12 items for "fan_out_queries".
- "paa_relevance" must contain exactly one entry per question in the People
  Also Ask list above, in the same order, with the question text copied
  verbatim (do not paraphrase or reorder them). If the list above is empty,
  return an empty array for "paa_relevance".
- For "answer_snippet": choose format based on intent_type -
  Definition/Yes-No -> "paragraph" (40-60 words, restate the topic naturally
  in the first sentence, no fluff, self-contained enough to be quoted alone);
  Process -> "steps" (3-8 short imperative steps, no numbering in the text
  itself); Comparison/List -> "table" (2-5 rows, 2-4 columns of the key
  attributes being compared or listed).
- Only populate the fields relevant to the chosen format; set the other
  format fields to null or an empty array (e.g. if format is "paragraph",
  "steps" should be an empty array and "table_headers"/"table_rows" empty
  arrays).
- "extraction_score" is an integer 0-100: how likely this exact snippet would
  be selected/extracted by an AI answer engine or Google's featured snippet
  algorithm, based on directness, clarity, and self-containment.
- "score_reasons" must have 2-3 short items, each under 12 words.
"""


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


def _clean_paa_list(items):
    """Like _clean_scored_list, but also carries through the AEO answer text."""
    cleaned = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        if not question:
            continue
        try:
            relevance = int(item.get("relevance"))
        except (TypeError, ValueError):
            relevance = None
        answer = item.get("answer")
        answer = answer.strip() if isinstance(answer, str) else None
        cleaned.append({"question": question, "relevance": relevance, "answer": answer or None})
    return cleaned


def _word_count(snippet: dict) -> int:
    fmt = snippet.get("format")
    if fmt == "paragraph":
        text = snippet.get("paragraph") or ""
        return len(text.split())
    if fmt == "steps":
        return sum(len((s or "").split()) for s in snippet.get("steps") or [])
    if fmt == "table":
        headers = snippet.get("table_headers") or []
        rows = snippet.get("table_rows") or []
        total = sum(len((h or "").split()) for h in headers)
        for row in rows:
            total += sum(len((cell or "").split()) for cell in row or [])
        return total
    return 0


def _clean_answer_snippet(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}

    intent_type = raw.get("intent_type")
    if intent_type not in VALID_INTENTS:
        intent_type = None

    fmt = raw.get("format")
    if fmt not in VALID_FORMATS:
        fmt = "paragraph"

    paragraph = raw.get("paragraph")
    paragraph = paragraph.strip() if isinstance(paragraph, str) and paragraph.strip() else None

    steps = [s.strip() for s in (raw.get("steps") or []) if isinstance(s, str) and s.strip()]

    table_headers = [h.strip() for h in (raw.get("table_headers") or []) if isinstance(h, str) and h.strip()]
    table_rows = []
    for row in raw.get("table_rows") or []:
        if isinstance(row, list):
            table_rows.append([str(cell).strip() if cell is not None else "" for cell in row])

    try:
        extraction_score = int(raw.get("extraction_score"))
        extraction_score = max(0, min(100, extraction_score))
    except (TypeError, ValueError):
        extraction_score = None

    score_reasons = [
        r.strip() for r in (raw.get("score_reasons") or []) if isinstance(r, str) and r.strip()
    ][:3]

    snippet = {
        "intent_type": intent_type,
        "format": fmt,
        "paragraph": paragraph,
        "steps": steps,
        "table_headers": table_headers,
        "table_rows": table_rows,
        "extraction_score": extraction_score,
        "score_reasons": score_reasons,
    }
    snippet["word_count"] = _word_count(snippet)
    return snippet


def generate_keyword_insights(seed_keyword: str, serp_data: dict) -> dict:
    """
    Calls Gemini with the seed keyword + SERP context and returns a dict:
      {
        "nlp_keywords": [{"keyword": str, "relevance": int}, ...],
        "fan_out_queries": [{"query": str, "relevance": int}, ...],
        "paa_relevance": [{"question": str, "relevance": int, "answer": str|None}, ...],
        "answer_snippet": {
          "intent_type": str|None,
          "format": "paragraph"|"steps"|"table",
          "paragraph": str|None,
          "steps": [str, ...],
          "table_headers": [str, ...],
          "table_rows": [[str, ...], ...],
          "extraction_score": int|None,
          "score_reasons": [str, ...],
          "word_count": int,
        },
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

    return {
        "nlp_keywords": _clean_scored_list(parsed.get("nlp_keywords"), "keyword"),
        "fan_out_queries": _clean_scored_list(parsed.get("fan_out_queries"), "query"),
        "paa_relevance": _clean_paa_list(parsed.get("paa_relevance")),
        "answer_snippet": _clean_answer_snippet(parsed.get("answer_snippet")),
    }
