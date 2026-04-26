import json
import os
from typing import Union
from dotenv import load_dotenv

from models.schemas import Skill, SkillCategory
from prompts.extraction import JD_EXTRACTION_PROMPT, RESUME_EXTRACTION_PROMPT
from utils.llm_client import call_llm

load_dotenv()

_IMPORTANCE_MAP = {
    "required": 1.0,
    "must-have": 1.0,
    "strong": 0.85,
    "proven": 0.85,
    "preferred": 0.7,
    "desired": 0.7,
    "nice-to-have": 0.4,
    "bonus": 0.4,
}


def _call_llm_json(prompt: str) -> dict:
    text = call_llm(prompt, model_env_key="PARSING_MODEL", default_model="gemini-2.5-flash")
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())

    return json.loads(text)


def _normalise_importance(raw: Union[str, float]) -> float:
    if isinstance(raw, (int, float)):
        return float(max(0.0, min(1.0, raw)))
    return _IMPORTANCE_MAP.get(str(raw).lower().strip(), 0.7)


def parse_jd(jd_text: str) -> list[Skill]:
    """Extract required skills from a job description."""
    prompt = JD_EXTRACTION_PROMPT.format(jd_text=jd_text)
    data = _call_llm_json(prompt)
    skills = []
    for item in data.get("skills", []):
        try:
            skill = Skill(
                name=item["name"],
                canonical_name=item.get("canonical_name", item["name"]).lower().strip(),
                claimed_level=0,
                required_level=int(item.get("required_level", 3)),
                importance=_normalise_importance(item.get("importance", 0.7)),
                category=SkillCategory(item.get("category", "technical")),
            )
            skills.append(skill)
        except Exception:
            continue
    return skills


def parse_resume(resume_text: str, required_skills: list[Skill]) -> list[Skill]:
    """Map required skills to claimed proficiency levels from a resume."""
    required_names = [
        {"canonical_name": s.canonical_name, "name": s.name}
        for s in required_skills
    ]
    prompt = RESUME_EXTRACTION_PROMPT.format(
        resume_text=resume_text,
        required_skills=json.dumps(required_names, indent=2),
    )
    data = _call_llm_json(prompt)

    req_lookup = {s.canonical_name: s for s in required_skills}

    skills = []
    for item in data.get("skills", []):
        try:
            canonical = item.get("canonical_name", item["name"]).lower().strip()
            ref = req_lookup.get(canonical)
            skill = Skill(
                name=item["name"],
                canonical_name=canonical,
                claimed_level=int(item.get("claimed_level", 0)),
                required_level=ref.required_level if ref else 3,
                importance=ref.importance if ref else 0.5,
                category=SkillCategory(item.get("category", "technical")),
            )
            skills.append(skill)
        except Exception:
            continue
    return skills

