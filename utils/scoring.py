from models.schemas import Skill, ProficiencyScore, SkillGap, GapLabel

_GAP_LABELS = {0: GapLabel.NONE, 1: GapLabel.MINOR}


def _gap_label(gap_size: int) -> GapLabel:
    if gap_size <= 0:
        return GapLabel.NONE
    if gap_size == 1:
        return GapLabel.MINOR
    if gap_size <= 3:
        return GapLabel.MODERATE
    return GapLabel.SIGNIFICANT


def compute_gaps(
    required: list[Skill],
    scores: dict[str, ProficiencyScore],
    top_n: int = 5,
) -> list[SkillGap]:
    """
    Compute and rank skill gaps.
    gap_severity = importance × max(0, required_level − assessed_level)
    Returns top_n gaps sorted by severity descending.
    """
    gaps = []
    for skill in required:
        assessed = scores.get(skill.canonical_name)
        assessed_level = assessed.assessed_level if assessed else 0
        gap_size = max(0, skill.required_level - assessed_level)
        severity = round(skill.importance * gap_size, 3)
        gaps.append(
            SkillGap(
                skill=skill.canonical_name,
                gap_size=gap_size,
                gap_severity=severity,
                label=_gap_label(gap_size),
            )
        )

    gaps.sort(key=lambda g: g.gap_severity, reverse=True)
    return gaps[:top_n]


def split_strengths_and_gaps(
    required: list[Skill],
    scores: dict[str, ProficiencyScore],
) -> tuple[list[str], list[SkillGap]]:
    """Return (strengths, gaps) — strengths are skills with gap_size == 0."""
    all_gaps = compute_gaps(required, scores, top_n=len(required))
    strengths = [g.skill for g in all_gaps if g.gap_size == 0]
    gaps = [g for g in all_gaps if g.gap_size > 0]
    return strengths, gaps
