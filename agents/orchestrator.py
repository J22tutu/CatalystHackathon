import os
from typing import Literal
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage

from models.schemas import AgentState, Phase, ProficiencyScore
from agents.parser import parse_jd, parse_resume
from agents.assessor import assess_skill
from agents.planner import generate_plan, generate_summary
from utils.document_loader import extract_text
from utils.scoring import split_strengths_and_gaps

load_dotenv()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def parse_node(state: AgentState) -> AgentState:
    jd_text = state["jd_raw"]
    resume_text = state["resume_raw"]

    required = parse_jd(jd_text)
    candidate = parse_resume(resume_text, required)

    # build assessment queue: top 5 required skills by importance
    queue = [
        s.canonical_name
        for s in sorted(required, key=lambda x: x.importance, reverse=True)
    ][:5]

    return {
        **state,
        "required_skills": required,
        "candidate_skills": candidate,
        "assessment_queue": queue,
        "current_skill": queue[0] if queue else "",
        "phase": Phase.ASSESS,
        "messages": state["messages"] + [
            AIMessage(content=(
                f"I've analysed the job description and your resume. "
                f"I'll now assess your proficiency in {len(queue)} key skills: "
                f"{', '.join(queue)}.\n\n"
                f"Let's start with **{queue[0]}**."
            ))
        ],
    }


def assess_node(state: AgentState) -> AgentState:
    skill_name = state["current_skill"]
    required_skills = state["required_skills"]
    candidate_skills = state["candidate_skills"]

    # find the skill object
    skill = next(
        (s for s in required_skills if s.canonical_name == skill_name),
        None,
    )
    if skill is None:
        # skill not found — skip it
        return _advance_queue(state)

    # merge claimed level from resume parse
    candidate_skill = next(
        (s for s in candidate_skills if s.canonical_name == skill_name),
        None,
    )
    if candidate_skill:
        skill = skill.model_copy(update={"claimed_level": candidate_skill.claimed_level})

    messages_buffer: list = list(state["messages"])

    def conversation_callback(agent_message: str) -> str:
        """Append agent message to state; return last human message."""
        messages_buffer.append(AIMessage(content=agent_message))
        # the UI layer will inject the human response into messages
        # for the orchestrator we return the last HumanMessage content
        human_msgs = [m for m in messages_buffer if isinstance(m, HumanMessage)]
        return human_msgs[-1].content if human_msgs else ""

    score: ProficiencyScore = assess_skill(skill, conversation_callback)

    new_scores = {**state.get("scores", {}), skill_name: score}
    new_log = list(state.get("assessment_log", []))

    return _advance_queue({
        **state,
        "scores": new_scores,
        "assessment_log": new_log,
        "messages": messages_buffer,
    })


def _advance_queue(state: AgentState) -> AgentState:
    queue = list(state["assessment_queue"])
    current = state["current_skill"]
    if current in queue:
        queue.remove(current)

    next_skill = queue[0] if queue else ""
    messages = list(state["messages"])

    if next_skill:
        messages.append(AIMessage(
            content=f"Got it. Moving on to **{next_skill}**."
        ))

    return {
        **state,
        "assessment_queue": queue,
        "current_skill": next_skill,
        "messages": messages,
        "phase": Phase.ASSESS if queue else Phase.ANALYSE,
    }


def analyse_node(state: AgentState) -> AgentState:
    strengths, gaps = split_strengths_and_gaps(
        state["required_skills"],
        state["scores"],
    )

    strength_text = ", ".join(strengths) if strengths else "none identified"
    gap_lines = "\n".join(
        f"  • {g.skill}: {g.label.value} gap" for g in gaps
    )

    summary_msg = (
        f"Assessment complete. Here's what I found:\n\n"
        f"✅ **Strengths:** {strength_text}\n\n"
        f"📊 **Gaps identified:**\n{gap_lines}\n\n"
        f"Generating your personalised learning plan..."
    )

    return {
        **state,
        "gaps": gaps,
        "phase": Phase.PLAN,
        "messages": state["messages"] + [AIMessage(content=summary_msg)],
    }


def plan_node(state: AgentState) -> AgentState:
    strengths, _ = split_strengths_and_gaps(
        state["required_skills"],
        state["scores"],
    )

    plan = generate_plan(
        gaps=state["gaps"],
        strengths=strengths,
        candidate_name=state.get("candidate_name", "Candidate"),
        role=state.get("role", "the target role"),
    )

    return {
        **state,
        "learning_plan": plan,
        "phase": Phase.REPORT,
    }


def report_node(state: AgentState) -> AgentState:
    plan = state["learning_plan"]
    summary = generate_summary(
        candidate_name=state.get("candidate_name", "Candidate"),
        role=state.get("role", "the target role"),
        scores=state["scores"],
        gaps=state["gaps"],
    )

    plan_lines = [f"**Your Personalised Learning Plan**\n"]
    for item in plan.items:
        plan_lines.append(
            f"**{item.priority}. {item.skill.title()}** "
            f"({item.gap_label.value} gap) — {item.estimated_weeks}"
        )
        plan_lines.append(f"   Milestone: {item.milestone}")
        for r in item.resources:
            free_tag = "free" if r.free else "paid"
            plan_lines.append(f"   • {r.title} ({r.type.value}, {free_tag})")
        plan_lines.append("")

    plan_lines.append(f"⏱ Total estimated time: **{plan.total_estimated_weeks}**")

    final_msg = f"{summary}\n\n" + "\n".join(plan_lines)

    return {
        **state,
        "phase": Phase.REPORT,
        "messages": state["messages"] + [AIMessage(content=final_msg)],
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_assess(state: AgentState) -> Literal["assess", "analyse"]:
    if state["assessment_queue"]:
        return "assess"
    return "analyse"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("parse",   parse_node)
    graph.add_node("assess",  assess_node)
    graph.add_node("analyse", analyse_node)
    graph.add_node("plan",    plan_node)
    graph.add_node("report",  report_node)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "assess")
    graph.add_conditional_edges(
        "assess",
        route_assess,
        {"assess": "assess", "analyse": "analyse"},
    )
    graph.add_edge("analyse", "plan")
    graph.add_edge("plan",    "report")
    graph.add_edge("report",  END)

    return graph.compile()


# singleton compiled graph
agent = build_graph()
