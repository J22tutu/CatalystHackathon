import os
import tempfile
import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from models.schemas import (
    AgentState, Phase, Skill, SkillCategory, QualitySignal, AssessmentTurn
)
from agents.parser import parse_jd, parse_resume
from agents.assessor import generate_question, score_response
from agents.planner import generate_plan, generate_summary
from utils.document_loader import extract_text
from utils.scoring import split_strengths_and_gaps

load_dotenv()

st.set_page_config(
    page_title="Skill Assessment Agent",
    page_icon="🧠",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

def init_state():
    defaults = {
        "phase": Phase.PARSE,
        "required_skills": [],
        "candidate_skills": [],
        "assessment_queue": [],
        "current_skill": "",
        "assessment_history": [],   # list of AssessmentTurn for current skill
        "all_history": [],          # all turns across all skills
        "scores": {},
        "gaps": [],
        "strengths": [],
        "learning_plan": None,
        "messages": [],             # chat display messages
        "question_pending": None,   # current unanswered question
        "current_signal": QualitySignal.PARTIAL,
        "q_count": 0,
        "candidate_name": "Candidate",
        "role": "",
        "jd_text": "",
        "resume_text": "",
        "summary": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_message(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def get_current_skill_obj() -> Skill | None:
    name = st.session_state.current_skill
    for s in st.session_state.required_skills:
        if s.canonical_name == name:
            cs = next(
                (c for c in st.session_state.candidate_skills
                 if c.canonical_name == name), None
            )
            claimed = cs.claimed_level if cs else 0
            return s.model_copy(update={"claimed_level": claimed})
    return None


def finish_skill_assessment():
    """Score the skill, save result, advance queue."""
    history = st.session_state.assessment_history
    if not history:
        return

    scores_list = [t.score for t in history]
    weights = list(range(1, len(scores_list) + 1))
    final = round(sum(s * w for s, w in zip(scores_list, weights)) / sum(weights))
    final = max(1, min(5, final))

    from models.schemas import ProficiencyScore
    skill_name = st.session_state.current_skill
    st.session_state.scores[skill_name] = ProficiencyScore(
        skill=skill_name,
        assessed_level=final,
        confidence=min(1.0, 0.5 + len(history) * 0.15),
        rationale=history[-1].question,
        question_count=len(history),
    )
    st.session_state.all_history.extend(history)
    st.session_state.assessment_history = []
    st.session_state.question_pending = None
    st.session_state.q_count = 0
    st.session_state.current_signal = QualitySignal.PARTIAL

    queue = list(st.session_state.assessment_queue)
    if skill_name in queue:
        queue.remove(skill_name)
    st.session_state.assessment_queue = queue

    if queue:
        next_skill = queue[0]
        st.session_state.current_skill = next_skill
        add_message("assistant", f"Got it. Moving on to **{next_skill}**.")
    else:
        st.session_state.phase = Phase.ANALYSE
        add_message("assistant", "That covers all the skills. Let me analyse your results...")


def run_analyse_plan_report():
    """Run analyse → plan → report after assessment is done."""
    strengths, gaps = split_strengths_and_gaps(
        st.session_state.required_skills,
        st.session_state.scores,
    )
    st.session_state.strengths = strengths
    st.session_state.gaps = gaps

    # Gap summary
    strength_text = ", ".join(strengths) if strengths else "none identified"
    gap_lines = "\n".join(f"  • {g.skill}: {g.label.value} gap" for g in gaps)
    add_message("assistant",
        f"**Assessment complete!**\n\n"
        f"✅ **Strengths:** {strength_text}\n\n"
        f"📊 **Gaps identified:**\n{gap_lines}\n\n"
        f"Generating your personalised learning plan..."
    )

    # Generate plan
    plan = generate_plan(
        gaps=gaps,
        strengths=strengths,
        candidate_name=st.session_state.candidate_name,
        role=st.session_state.role,
    )
    st.session_state.learning_plan = plan

    # Summary narrative
    summary = generate_summary(
        candidate_name=st.session_state.candidate_name,
        role=st.session_state.role,
        scores=st.session_state.scores,
        gaps=gaps,
    )
    st.session_state.summary = summary
    st.session_state.phase = Phase.REPORT


# ---------------------------------------------------------------------------
# Sidebar — inputs
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🧠 Skill Assessment Agent")
    st.markdown("---")

    st.session_state.candidate_name = st.text_input(
        "Your name", value=st.session_state.candidate_name
    )
    st.session_state.role = st.text_input(
        "Role you're applying for", value=st.session_state.role,
        placeholder="e.g. Senior Data Engineer"
    )

    st.markdown("**Job Description**")
    jd_input = st.text_area(
        "Paste JD here", height=200, value=st.session_state.jd_text,
        label_visibility="collapsed"
    )

    st.markdown("**Your Resume**")
    resume_file = st.file_uploader("Upload resume", type=["pdf", "docx", "txt"])
    resume_paste = st.text_area(
        "Or paste resume text", height=150, label_visibility="collapsed"
    )

    start_btn = st.button("🚀 Start Assessment", type="primary", use_container_width=True)

    if start_btn:
        if not jd_input.strip():
            st.error("Please paste a job description.")
        elif not resume_file and not resume_paste.strip():
            st.error("Please upload or paste your resume.")
        else:
            with st.spinner("Parsing JD and resume..."):
                # extract resume text
                if resume_file:
                    suffix = "." + resume_file.name.split(".")[-1]
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(resume_file.read())
                        tmp_path = tmp.name
                    resume_text = extract_text(tmp_path)
                    os.unlink(tmp_path)
                else:
                    resume_text = resume_paste.strip()

                jd_text = jd_input.strip()
                required = parse_jd(jd_text)
                candidate = parse_resume(resume_text, required)

                queue = [
                    s.canonical_name
                    for s in sorted(required, key=lambda x: x.importance, reverse=True)
                ][:5]

                # reset session
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                init_state()

                st.session_state.jd_text = jd_text
                st.session_state.resume_text = resume_text
                st.session_state.required_skills = required
                st.session_state.candidate_skills = candidate
                st.session_state.assessment_queue = queue
                st.session_state.current_skill = queue[0] if queue else ""
                st.session_state.phase = Phase.ASSESS
                st.session_state.role = st.session_state.role or "the target role"

                add_message("assistant",
                    f"Hi **{st.session_state.candidate_name}**! I've parsed your resume and the JD.\n\n"
                    f"I'll assess your proficiency in **{len(queue)} skills**: "
                    f"{', '.join(queue)}.\n\n"
                    f"Let's start with **{queue[0]}**. I'll ask up to 4 questions per skill."
                )
            st.rerun()

    st.markdown("---")
    if st.session_state.required_skills:
        st.markdown("**Required Skills**")
        for s in st.session_state.required_skills:
            score = st.session_state.scores.get(s.canonical_name)
            if score:
                bar = "🟢" if score.assessed_level >= s.required_level else "🟡" if score.assessed_level >= s.required_level - 1 else "🔴"
                st.markdown(f"{bar} {s.canonical_name} ({score.assessed_level}/{s.required_level})")
            elif s.canonical_name == st.session_state.current_skill:
                st.markdown(f"⏳ **{s.canonical_name}** ← assessing")
            else:
                st.markdown(f"⬜ {s.canonical_name}")


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("AI-Powered Skill Assessment")

# render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# ASSESS phase — generate question and handle answer
# ---------------------------------------------------------------------------

if st.session_state.phase == Phase.ASSESS and st.session_state.current_skill:

    # generate first question for this skill if none pending
    if st.session_state.question_pending is None:
        skill = get_current_skill_obj()
        if skill:
            with st.spinner(f"Preparing question for {skill.canonical_name}..."):
                q = generate_question(
                    skill=skill.canonical_name,
                    claimed_level=skill.claimed_level,
                    history=st.session_state.assessment_history,
                    quality_signal=st.session_state.current_signal,
                )
            st.session_state.question_pending = q
            add_message("assistant", q.question)
            st.rerun()

    # accept user answer
    if answer := st.chat_input("Your answer..."):
        q = st.session_state.question_pending
        add_message("user", answer)

        with st.spinner("Scoring your response..."):
            result = score_response(
                skill=st.session_state.current_skill,
                question=q.question,
                response=answer,
            )

        # record turn
        turn = AssessmentTurn(
            skill=st.session_state.current_skill,
            question=q.question,
            tests_for=q.tests_for,
            difficulty=q.difficulty,
            response=answer,
            score=result.score,
            quality_signal=st.session_state.current_signal,
        )
        st.session_state.assessment_history.append(turn)
        st.session_state.q_count += 1

        # update signal for next question
        if result.score >= 4:
            st.session_state.current_signal = QualitySignal.STRONG
        elif result.score == 3:
            st.session_state.current_signal = QualitySignal.PARTIAL
        else:
            st.session_state.current_signal = QualitySignal.WEAK

        MAX_Q = 4
        MIN_Q = 2
        done = (
            st.session_state.q_count >= MAX_Q
            or (st.session_state.q_count >= MIN_Q and not result.follow_up_needed)
        )

        if done:
            finish_skill_assessment()
            st.session_state.question_pending = None

            if st.session_state.phase == Phase.ANALYSE:
                with st.spinner("Generating learning plan (this takes ~20s)..."):
                    run_analyse_plan_report()
        else:
            # generate next question
            skill = get_current_skill_obj()
            if skill:
                with st.spinner("Next question..."):
                    next_q = generate_question(
                        skill=skill.canonical_name,
                        claimed_level=skill.claimed_level,
                        history=st.session_state.assessment_history,
                        quality_signal=st.session_state.current_signal,
                    )
                st.session_state.question_pending = next_q
                add_message("assistant", next_q.question)

        st.rerun()

# ---------------------------------------------------------------------------
# REPORT phase — render learning plan
# ---------------------------------------------------------------------------

if st.session_state.phase == Phase.REPORT and st.session_state.learning_plan:
    plan = st.session_state.learning_plan

    if st.session_state.summary:
        st.markdown("---")
        st.subheader("📋 Assessment Summary")
        st.info(st.session_state.summary)

    st.markdown("---")
    st.subheader("📚 Your Personalised Learning Plan")
    st.caption(f"Total estimated time: **{plan.total_estimated_weeks}**")

    if plan.strengths:
        st.success(f"✅ Strengths: {', '.join(plan.strengths)}")

    for item in plan.items:
        with st.expander(
            f"#{item.priority} — {item.skill.title()} "
            f"({item.gap_label.value} gap) · {item.estimated_weeks}",
            expanded=item.priority == 1,
        ):
            st.markdown(f"**Milestone:** {item.milestone}")
            if item.adjacent_skills:
                st.markdown(f"**Builds on:** {', '.join(item.adjacent_skills)}")
            st.markdown("**Resources:**")
            for r in item.resources:
                free_badge = "🆓" if r.free else "💰"
                st.markdown(
                    f"- {free_badge} [{r.title}]({r.url}) "
                    f"— {r.type.value}, ~{r.estimated_hours}h"
                )

    if st.button("🔄 Start New Assessment"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ---------------------------------------------------------------------------
# PARSE phase — waiting for input
# ---------------------------------------------------------------------------

if st.session_state.phase == Phase.PARSE:
    st.markdown(
        "👈 **Paste a Job Description and upload your resume in the sidebar to begin.**"
    )
