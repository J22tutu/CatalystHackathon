import json
import os
from datetime import datetime
from dotenv import load_dotenv
from google import genai

from models.schemas import (
    SkillGap, LearningPlan, LearningPlanItem, LearningResource,
    GapLabel, ResourceType
)
from prompts.planning import LEARNING_PLAN_PROMPT, REPORT_SUMMARY_PROMPT

load_dotenv()

_client = None  # type: genai.Client


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client


def _call_llm(prompt: str) -> str:
    model = os.getenv("PLANNING_MODEL", "gemini-2.5-flash")
    response = _get_client().models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def _parse_json(text: str) -> dict:
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _load_resources_seed() -> dict:
    seed_path = os.path.join(os.path.dirname(__file__), "..", "data", "resources_seed.json")
    with open(os.path.normpath(seed_path)) as f:
        return json.load(f)


def _gaps_to_text(gaps: list[SkillGap]) -> str:
    lines = []
    for i, g in enumerate(gaps, 1):
        lines.append(
            f"{i}. {g.skill} — gap size: {g.gap_size}, "
            f"severity: {g.gap_severity:.2f}, label: {g.label.value}"
        )
    return "\n".join(lines)


def _parse_plan_items(data: dict, gaps: list[SkillGap]) -> list[LearningPlanItem]:
    items = []
    gap_labels = {g.skill: g.label for g in gaps}

    for item in data.get("items", []):
        resources = []
        for r in item.get("resources", []):
            try:
                resources.append(LearningResource(
                    title=r["title"],
                    url=r["url"],
                    type=ResourceType(r.get("type", "course")),
                    estimated_hours=int(r.get("estimated_hours", 10)),
                    free=bool(r.get("free", True)),
                ))
            except Exception:
                continue

        skill_name = item.get("skill", "")
        items.append(LearningPlanItem(
            skill=skill_name,
            priority=int(item.get("priority", len(items) + 1)),
            gap_label=gap_labels.get(skill_name, GapLabel.MODERATE),
            adjacent_skills=item.get("adjacent_skills", []),
            resources=resources,
            estimated_weeks=item.get("estimated_weeks", "3–5 weeks"),
            milestone=item.get("milestone", ""),
        ))
    return items


def generate_plan(
    gaps: list[SkillGap],
    strengths: list[str],
    candidate_name: str,
    role: str,
) -> LearningPlan:
    seed = _load_resources_seed()
    # only pass seed categories relevant to the gaps
    relevant_keys = {g.skill for g in gaps}
    relevant_seed = {k: v for k, v in seed.items() if k in relevant_keys} or seed

    prompt = LEARNING_PLAN_PROMPT.format(
        candidate_name=candidate_name,
        role=role,
        strengths=", ".join(strengths) if strengths else "none identified",
        gaps=_gaps_to_text(gaps),
        resources_seed=json.dumps(relevant_seed, indent=2),
    )

    raw = _call_llm(prompt)
    data = _parse_json(raw)
    items = _parse_plan_items(data, gaps)

    return LearningPlan(
        candidate_name=candidate_name,
        role=role,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        strengths=data.get("strengths", strengths),
        items=items,
        total_estimated_weeks=data.get("total_estimated_weeks", "8–12 weeks"),
    )


def generate_summary(
    candidate_name: str,
    role: str,
    scores: dict,
    gaps: list[SkillGap],
) -> str:
    scores_text = "\n".join(
        f"  {skill}: {s.assessed_level}/5 (confidence {s.confidence:.0%})"
        for skill, s in scores.items()
    )
    gaps_text = "\n".join(
        f"  {g.skill}: {g.label.value} gap (size {g.gap_size})"
        for g in gaps
    )
    prompt = REPORT_SUMMARY_PROMPT.format(
        candidate_name=candidate_name,
        role=role,
        scores=scores_text,
        gaps=gaps_text,
    )
    return _call_llm(prompt)
