import time
import os
from google import genai

_client = None  # type: genai.Client


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client


def call_llm(prompt: str, model_env_key: str = "ASSESSMENT_MODEL",
             default_model: str = "gemini-2.5-flash") -> str:
    """Call Gemini with automatic retry on 429 rate limit."""
    model = os.getenv(model_env_key, default_model)
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = get_client().models.generate_content(
                model=model, contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err and attempt < max_retries - 1:
                # parse retry delay from error message
                wait = 60
                import re
                match = re.search(r"retry in (\d+)", err)
                if match:
                    wait = int(match.group(1)) + 2
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("Max retries exceeded on LLM call")
