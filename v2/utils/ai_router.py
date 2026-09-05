"""
Omni-AI Router: Universal AI provider abstraction supporting OpenAI, Claude (Anthropic), and Gemini.
Auto-detects API keys in the environment. Falls back gracefully to Zero-AI local code if no keys are found.
"""
import os
import sys
import json
import re
import requests
from typing import List, Dict, Optional, Any

# Path to zero-AI fallback modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def _get_spacy_extract():
    try:
        from spacy_extractor import extract_claims_from_text
        return extract_claims_from_text
    except Exception:
        return None


def _get_code_contradictions():
    try:
        from contradiction import detect_contradictions
        return detect_contradictions
    except Exception:
        return None


def _get_query_expander():
    try:
        from query_expander import expand_topic
        return expand_topic
    except Exception:
        return None


class AIRouter:
    """
    Universal LLM client that automatically detects available API keys:
    1. OPENAI_API_KEY -> OpenAI GPT-4o / GPT-4o-mini
    2. ANTHROPIC_API_KEY -> Anthropic Claude 3.5 Haiku / Sonnet
    3. GEMINI_API_KEY -> Google Gemini 3.5 Flash-Lite / 3.7 Flash
    4. None -> Local Zero-AI fallback (spaCy NER & rule-based string logic)
    """

    def __init__(
        self,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        gemini_key: Optional[str] = None,
        preferred_provider: Optional[str] = None
    ):
        self.openai_key = openai_key or os.environ.get("OPENAI_API_KEY", "")
        self.anthropic_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        self.preferred_provider = preferred_provider or os.environ.get("PREFERRED_AI_PROVIDER", "").lower()

    @property
    def provider(self) -> str:
        """Determines active provider based on preference and available keys."""
        if self.preferred_provider in ("openai", "chatgpt") and self.openai_key:
            return "openai"
        if self.preferred_provider in ("anthropic", "claude") and self.anthropic_key:
            return "anthropic"
        if self.preferred_provider in ("gemini", "google") and self.gemini_key:
            return "gemini"

        # Automatic detection hierarchy
        if self.openai_key:
            return "openai"
        if self.anthropic_key:
            return "anthropic"
        if self.gemini_key:
            return "gemini"
        return "none"

    def generate_json(self, prompt: str, system_prompt: str = "") -> Any:
        """
        Executes a prompt across the active provider and parses JSON output.
        Falls back cleanly to an empty list/dict on failure.
        """
        provider = self.provider
        if provider == "openai":
            return self._call_openai(prompt, system_prompt)
        elif provider == "anthropic":
            return self._call_anthropic(prompt, system_prompt)
        elif provider == "gemini":
            return self._call_gemini(prompt, system_prompt)
        return None

    # ─── Provider Implementations (Direct HTTP REST) ────────────────

    def _call_openai(self, prompt: str, system_prompt: str = "") -> Any:
        """Calls OpenAI Chat Completions API (gpt-4o-mini)."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def _call_anthropic(self, prompt: str, system_prompt: str = "") -> Any:
        """Calls Anthropic Messages API (Claude 3.5 Haiku)."""
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
            "max_tokens": 2048,
            "system": system_prompt or "You are an objective fact extraction system. Return ONLY valid JSON.",
            "messages": [
                {"role": "user", "content": prompt + "\n\nReturn ONLY a valid JSON object or array."}
            ],
            "temperature": 0.1
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        
        # Extract json from markdown backticks if present
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        raw_json = match.group(1) if match else content
        return json.loads(raw_json)

    def _call_gemini(self, prompt: str, system_prompt: str = "") -> Any:
        """Calls Google Gemini API."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_key)
            model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
            model = genai.GenerativeModel(
                model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = model.generate_content(full_prompt)
            return json.loads(response.text)
        except Exception as e:
            print(f"Gemini API error: {e}")
            return None

    @property
    def provider_label(self) -> str:
        """Returns human-readable provider label."""
        labels = {
            "openai": "ChatGPT / OpenAI (gpt-4o-mini)",
            "anthropic": "Claude / Anthropic (claude-3-5-haiku)",
            "gemini": "Google Gemini (gemini-3.5-flash-lite)",
            "none": "Zero-AI Local Mode ($0.00)"
        }
        return labels.get(self.provider, "Zero-AI Local Mode ($0.00)")

    def expand_topic(self, topic: str, count: int = 10) -> List[str]:
        """
        Expands research topic into distinct search queries using active AI provider,
        falling back to rule-based synonym expansion if no AI is available.
        """
        if self.provider != "none":
            prompt = f"""Generate {count} distinct, high-signal search engine queries to comprehensively research: "{topic}".
Include diverse angles, specific terminology, and industry variants.
Return ONLY a JSON array of strings: ["query 1", "query 2", ...]"""
            try:
                res = self.generate_json(prompt)
                if isinstance(res, list) and len(res) > 0:
                    return [str(q).strip() for q in res if q]
                elif isinstance(res, dict) and "queries" in res:
                    return [str(q).strip() for q in res["queries"] if q]
            except Exception as e:
                print(f"AI query expansion failed: {e}")

        expander = _get_query_expander()
        if expander:
            return expander(topic, count=count)
        return [topic, f"best {topic}", f"{topic} guide", f"{topic} checklist"]

    def extract_claims(self, text: str, source_url: str, source_domain: str) -> List[Dict[str, Any]]:
        """
        Extracts factual claims using the active AI provider,
        or falls back to local spaCy NER if no AI keys are set.
        """
        spacy_fn = _get_spacy_extract()

        def _fallback():
            if spacy_fn:
                return spacy_fn(text, source_url, source_domain)
            return []

        if self.provider == "none":
            return _fallback()

        prompt = f"""
        Extract every atomic, verifiable factual claim from this article.
        Return a JSON object with a "claims" array.
        Each claim object MUST have:
        - "claim": the factual statement
        - "subject": what/who the fact is about
        - "numbers": array of any specific numbers/percentages/dates/amounts mentioned

        Article excerpt:
        \"\"\"{text[:30000]}\"\"\"
        """
        system_prompt = "You are a rigorous, unbiased factual claim extraction engine. Omit opinions, marketing, and predictions."

        try:
            data = self.generate_json(prompt, system_prompt)
            claims_list = []
            if isinstance(data, dict):
                claims_list = data.get("claims", [])
            elif isinstance(data, list):
                claims_list = data

            results = []
            for item in claims_list:
                results.append({
                    "claim": item.get("claim", ""),
                    "subject": item.get("subject", ""),
                    "numbers": item.get("numbers", []),
                    "source_url": source_url,
                    "source_domain": source_domain
                })
            return results if results else _fallback()
        except Exception as e:
            print(f"AI extraction failed ({self.provider}): {e}. Falling back to spaCy.")
            return _fallback()

    def check_contradiction(self, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detects contradictions between claims using AI or rule-based string logic.
        """
        code_fn = _get_code_contradictions()

        def _fallback():
            if code_fn:
                conflicts = code_fn(claims)
                return {
                    "has_contradiction": len(conflicts) > 0,
                    "contradictions": conflicts,
                    "explanation": "Rule-based contradiction check" if conflicts else "No contradictions detected"
                }
            return {"has_contradiction": False, "contradictions": [], "explanation": "No detector available"}

        if self.provider == "none" or len(claims) < 2:
            return _fallback()

        prompt = f"""
        These claims were found on different websites regarding the same topic:
        {json.dumps(claims, indent=2)}

        Do they assert the SAME specific fact, or do they contradict each other?
        Return a JSON object:
        {{
            "same_fact": boolean,
            "has_contradiction": boolean,
            "explanation": string
        }}
        """
        try:
            res = self.generate_json(prompt)
            if isinstance(res, dict):
                return res
        except Exception as e:
            print(f"AI contradiction check failed: {e}")

        # Fallback to local code
        return _fallback()
