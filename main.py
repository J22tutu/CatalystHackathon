#!/usr/bin/env python3
"""CLI entry point for the Skill Assessment Agent."""
from __future__ import annotations

import argparse
import json
import sys
from dotenv import load_dotenv

from agents.parser import parse_jd, parse_resume
from agents.assessor import generate_question, score_response
from agents.planner import generate_plan, generate_summary
from utils.document_loader import extract_text
from utils.scoring import split_strengths_and_gaps
from models.schemas import (
    Phase, QualitySignal, AssessmentTurn, ProficiencyScore
)

load_dotenv()

MAX_Q = 3
MIN_Q = 2


def ask(question: str) -> str:
    print(f"\n🤖 {question}\n")
    return input("You: ").strip()


def assess_skill_cli(skill, candidate_skills: list) -> ProficiencyScore:
    cs = next((c for c in candidate_skills if c.canonical_name == skill.canonical_name), None)
    claimed = cs.claimed_level if cs else 0
    skill = skill.model_copy(update={"claimed_level": claimed})

    history: list[AssessmentTurn] = []
    scores: list[int] = []
    signal = QualitySignal.PARTIAL

    print(f"\n{'─' * 50}")
    print(f"  Assessing: {skill.canonical_name.upper()}")
    print(f"{'─' * 50}")

    for i in range(MAX_Q):
        q = generate_question(
            skill=skill.canonical_name,
            claimed_level=skill.claimed_level,
            history=history,
            quality_signal=signal,
        )
        answer = ask(q.question)

        if len(answer) < 20:
            answer = ask("Could you elaborate a bit more?") or answer

        result = score_response(skill.canonical_name, q.question, answer)

        history.append(AssessmentTurn(
            skill=skill.canonical_name,
            question=q.question,
            tests_for=q.tests_for,
            difficulty=q.difficulty,
            response=answer,
            score=result.score,
            quality_signal=signal,
        ))
        scores.append(result.score)

        if result.score >= 4:
            signal = QualitySignal.STRONG
        elif result.score == 3:
            signal = QualitySignal.PARTIAL
        else:
            signal = QualitySignal.WEAK

        if i + 1 >= MIN_Q and not result.follow_up_needed:
            break

    weights = list(range(1, len(scores) + 1))
    final = max(1, min(5, round(sum(s * w for s, w in zip(scores, weights)) / sum(weights))))

    return ProficiencyScore(
        skill=skill.canonical_name,
        assessed_level=final,
        confidence=min(1.0, 0.5 + len(scores) * 0.15),
        rationale=history[-1].question if history else "",
        question_count=len(scores),
    )


def print_report(plan, summary: str, strengths: list, gaps: list):
    print("\n" + "═" * 60)
    print("  ASSESSMENT REPORT")
    print("═" * 60)
    print(f"\n{summary}\n")

    print("─" * 60)
    print("  SKILL SCORES")
    print("─" * 60)

    print(f"\n✅ Strengths : {', '.join(strengths) if strengths else 'none'}")
    print("\n📊 Gaps:")
    for g in gaps:
        print(f"   • {g.skill:<20} {g.label.value} gap (size {g.gap_size})")

    print("\n" + "─" * 60)
    print("  PERSONALISED LEARNING PLAN")
    print("─" * 60)
    print(f"\n  Total estimated time: {plan.total_estimated_weeks}\n")

    for item in plan.items:
        print(f"  [{item.priority}] {item.skill.upper()} — {item.gap_label.value} — {item.estimated_weeks}")
        print(f"      Milestone : {item.milestone}")
        if item.adjacent_skills:
            print(f"      Builds on : {', '.join(item.adjacent_skills)}")
        for r in item.resources:
            free = "free" if r.free else "paid"
            print(f"      • {r.title} ({r.type.value}, {free})")
        print()

    print("═" * 60)


def main():
    parser = argparse.ArgumentParser(description="AI Skill Assessment Agent")
    parser.add_argument("--jd",       required=True, help="Path to job description (.txt)")
    parser.add_argument("--resume",   required=True, help="Path to resume (.pdf/.docx/.txt)")
    parser.add_argument("--name",     default="Candidate", help="Candidate name")
    parser.add_argument("--skills",   type=int, default=3, help="Max skills to assess (default 3)")
    parser.add_argument("--output",   help="Optional path to save report as JSON")
    args = parser.parse_args()

    print("\n🧠 AI-Powered Skill Assessment Agent")
    print("─" * 40)

    # parse inputs
    print("\n📄 Parsing JD and resume...")
    jd_text = extract_text(args.jd)
    resume_text = extract_text(args.resume)

    required = parse_jd(jd_text)
    candidate = parse_resume(resume_text, required)

    queue = [
        s for s in sorted(required, key=lambda x: x.importance, reverse=True)
    ][:args.skills]

    print(f"\n   Found {len(required)} required skills. Assessing top {len(queue)}:")
    for s in queue:
        print(f"   • {s.canonical_name} (required level {s.required_level})")

    print(f"\n   Candidate  : {args.name}")
    confirm = input("\n   Ready to begin? [y/n]: ").strip().lower()
    if confirm != "y":
        print("Exiting.")
        sys.exit(0)

    # assess each skill
    scores = {}
    for skill in queue:
        score = assess_skill_cli(skill, candidate)
        scores[skill.canonical_name] = score
        print(f"\n   ✓ {skill.canonical_name}: {score.assessed_level}/5")

    # analyse
    print("\n\n📊 Analysing gaps...")
    strengths, gaps = split_strengths_and_gaps(required, scores)

    # plan
    print("📚 Generating learning plan...")
    plan = generate_plan(gaps, strengths, args.name, role="target role")
    summary = generate_summary(args.name, "target role", scores, gaps)

    # report
    print_report(plan, summary, strengths, gaps)

    # optional JSON export
    if args.output:
        report = {
            "candidate": args.name,
            "scores": {k: v.model_dump() for k, v in scores.items()},
            "strengths": strengths,
            "gaps": [g.model_dump() for g in gaps],
            "plan": plan.model_dump(),
            "summary": summary,
        }
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 Report saved to {args.output}")


if __name__ == "__main__":
    main()
