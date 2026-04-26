LEARNING_PLAN_PROMPT = """You are a senior learning & development specialist creating a personalised upskilling plan.

Candidate: {candidate_name}
Role they are targeting: {role}
Their strengths (no action needed): {strengths}

Skill gaps to address (ranked by priority):
{gaps}

For each gap, generate a learning plan item. Use ONLY resources from the curated list below —
do not invent URLs or resource names.

Curated resource list:
{resources_seed}

For each gap output a JSON object with exactly these fields:
- "skill": skill name
- "priority": integer starting from 1 (1 = highest priority)
- "gap_label": one of "Minor", "Moderate", "Significant"
- "adjacent_skills": list of skills the candidate already has that will accelerate learning this gap
- "resources": list of 2–4 resource objects, each with:
    - "title": resource name from the curated list
    - "url": URL from the curated list
    - "type": one of "course", "docs", "project", "reading", "community"
    - "estimated_hours": realistic hours to complete
    - "free": boolean
- "estimated_weeks": realistic time range as a string e.g. "3–5 weeks"
  Use these heuristics:
  Minor + strong adjacent skills → "1–2 weeks"
  Minor + weak adjacent skills   → "2–3 weeks"
  Moderate + strong adjacent     → "3–5 weeks"
  Moderate + weak adjacent       → "5–8 weeks"
  Significant + strong adjacent  → "6–10 weeks"
  Significant + weak adjacent    → "10–16 weeks"
- "milestone": one concrete sentence describing what "done" looks like for this skill

Output a JSON object with a single key "items" containing the array, plus:
- "total_estimated_weeks": overall time range if tackled sequentially
- "strengths": the strengths list passed in (pass through unchanged)
"""

REPORT_SUMMARY_PROMPT = """You are generating the final assessment summary for a candidate.

Candidate: {candidate_name}
Role: {role}

Assessment scores:
{scores}

Skill gaps:
{gaps}

Write a concise, honest, encouraging summary (3–5 sentences) that:
1. Acknowledges their genuine strengths
2. Names the most critical gaps clearly without sugarcoating
3. Ends with a motivating statement about the learning plan

Plain text output only — no markdown, no bullet points.
"""
