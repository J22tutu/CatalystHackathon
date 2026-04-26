import os
from typing import Callable
from dotenv import load_dotenv
from google import genai

from models.schemas import (
    Skill, ProficiencyScore, AssessmentTurn,
    QuestionResponse, ScoreResponse, QualitySignal
)
from prompts.assessment import (
    QUESTION_GEN_PROMPT, SCORE_RESPONSE_PROMPT, ASSESSMENT_INTRO_PROMPT
)

load_dotenv()

MAX_QUESTIONS_PER_SKILL = 4
MIN_QUESTIONS_PER_SKILL = 2

_client = None  # type: genai.Client


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client


def _call_llm(prompt: str) -> str:
    model = os.getenv("ASSESSMENT_MODEL", "gemini-2.5-flash")
    response = _get_client().models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def _parse_json_response(text: str) -> dict:
    import json
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _quality_signal(score: int) -> QualitySignal:
    if score >= 4:
        return QualitySignal.STRONG
    elif score == 3:
        return QualitySignal.PARTIAL
    return QualitySignal.WEAK


def generate_question(
    skill: str,
    claimed_level: int,
    history: list[AssessmentTurn],
    quality_signal: QualitySignal,
) -> QuestionResponse:
    previous = (
        [f"- {t.question}" for t in history] if history else ["none"]
    )
    prompt = QUESTION_GEN_PROMPT.format(
        skill=skill,
        claimed_level=claimed_level,
        previous_questions="\n".join(previous),
        quality_signal=quality_signal.value,
    )
    raw = _call_llm(prompt)
    data = _parse_json_response(raw)
    return QuestionResponse(
        question=data["question"],
        tests_for=data.get("tests_for", ""),
        difficulty=int(data.get("difficulty", claimed_level)),
    )


def score_response(skill: str, question: str, response: str) -> ScoreResponse:
    prompt = SCORE_RESPONSE_PROMPT.format(
        skill=skill,
        question=question,
        response=response,
    )
    raw = _call_llm(prompt)
    data = _parse_json_response(raw)
    return ScoreResponse(
        score=int(data["score"]),
        confidence=float(data.get("confidence", 0.7)),
        rationale=data.get("rationale", ""),
        follow_up_needed=bool(data.get("follow_up_needed", False)),
    )


def assess_skill(
    skill: Skill,
    conversation_callback: Callable[[str], str],
) -> ProficiencyScore:
    """
    Conversationally assess one skill.
    conversation_callback(question) → candidate's answer as string.
    """
    history: list[AssessmentTurn] = []
    scores: list[int] = []
    current_signal = QualitySignal.PARTIAL

    # opening intro line
    intro_prompt = ASSESSMENT_INTRO_PROMPT.format(
        skill=skill.canonical_name,
        claimed_level=skill.claimed_level,
        role="the target role",
    )
    intro = _call_llm(intro_prompt)
    conversation_callback(intro)  # send intro, ignore response (it's just a greeting)

    for i in range(MAX_QUESTIONS_PER_SKILL):
        # generate next question
        q_response = generate_question(
            skill=skill.canonical_name,
            claimed_level=skill.claimed_level,
            history=history,
            quality_signal=current_signal,
        )

        # get candidate answer
        candidate_answer = conversation_callback(q_response.question)

        # handle evasive / too-short answers
        if len(candidate_answer.strip()) < 20:
            follow_up = "Could you elaborate a bit more? Even a rough example would help."
            candidate_answer = conversation_callback(follow_up)

        # score the response
        score_result = score_response(
            skill=skill.canonical_name,
            question=q_response.question,
            response=candidate_answer,
        )

        # record the turn
        turn = AssessmentTurn(
            skill=skill.canonical_name,
            question=q_response.question,
            tests_for=q_response.tests_for,
            difficulty=q_response.difficulty,
            response=candidate_answer,
            score=score_result.score,
            quality_signal=current_signal,
        )
        history.append(turn)
        scores.append(score_result.score)
        current_signal = _quality_signal(score_result.score)

        # stop early if we have enough signal and no follow-up needed
        enough_questions = i + 1 >= MIN_QUESTIONS_PER_SKILL
        if enough_questions and not score_result.follow_up_needed:
            break

    # final score = weighted average (recent answers count more)
    weights = list(range(1, len(scores) + 1))
    final_score = round(sum(s * w for s, w in zip(scores, weights)) / sum(weights))
    confidence = min(1.0, 0.5 + len(scores) * 0.15)

    return ProficiencyScore(
        skill=skill.canonical_name,
        assessed_level=max(1, min(5, final_score)),
        confidence=confidence,
        rationale=history[-1].question if history else "",
        question_count=len(history),
    )
