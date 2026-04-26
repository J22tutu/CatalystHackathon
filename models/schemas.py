from __future__ import annotations

from enum import Enum
from typing import TypedDict, Annotated, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ImportanceLevel(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    NICE_TO_HAVE = "nice-to-have"


class SkillCategory(str, Enum):
    TECHNICAL = "technical"
    DOMAIN = "domain"
    SOFT = "soft"


class GapLabel(str, Enum):
    NONE = "None"
    MINOR = "Minor"
    MODERATE = "Moderate"
    SIGNIFICANT = "Significant"


class Phase(str, Enum):
    PARSE = "parse"
    ASSESS = "assess"
    ANALYSE = "analyse"
    PLAN = "plan"
    REPORT = "report"


class ResourceType(str, Enum):
    COURSE = "course"
    DOCS = "docs"
    PROJECT = "project"
    READING = "reading"
    COMMUNITY = "community"


class QualitySignal(str, Enum):
    STRONG = "strong"
    PARTIAL = "partial"
    WEAK = "weak"


# ---------------------------------------------------------------------------
# Core domain models (Pydantic — used for LLM structured output)
# ---------------------------------------------------------------------------

class Skill(BaseModel):
    name: str
    canonical_name: str
    claimed_level: int = Field(default=0, ge=0, le=5)   # 0 = not on resume
    required_level: int = Field(default=3, ge=1, le=5)
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    category: SkillCategory = SkillCategory.TECHNICAL


class ProficiencyScore(BaseModel):
    skill: str
    assessed_level: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    question_count: int = Field(default=0, ge=0)


class SkillGap(BaseModel):
    skill: str
    gap_size: int               # required_level − assessed_level
    gap_severity: float         # gap_size × importance weight
    label: GapLabel


class LearningResource(BaseModel):
    title: str
    url: str
    type: ResourceType
    estimated_hours: int = Field(ge=1)
    free: bool = True


class LearningPlanItem(BaseModel):
    skill: str
    priority: int = Field(ge=1)
    gap_label: GapLabel
    adjacent_skills: list[str] = Field(default_factory=list)
    resources: list[LearningResource] = Field(default_factory=list)
    estimated_weeks: str
    milestone: str              # what "done" looks like


class LearningPlan(BaseModel):
    candidate_name: str
    role: str
    generated_at: str
    strengths: list[str] = Field(default_factory=list)
    items: list[LearningPlanItem] = Field(default_factory=list)
    total_estimated_weeks: str


# ---------------------------------------------------------------------------
# Assessment turn — one Q&A exchange during skill assessment
# ---------------------------------------------------------------------------

class AssessmentTurn(BaseModel):
    skill: str
    question: str
    tests_for: str
    difficulty: int = Field(ge=1, le=5)
    response: str = ""
    score: int = Field(default=0, ge=0, le=5)
    quality_signal: QualitySignal = QualitySignal.PARTIAL


# ---------------------------------------------------------------------------
# LangGraph state — passed between all graph nodes
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    jd_raw: str
    resume_raw: str
    candidate_name: str
    role: str
    required_skills: list[Skill]
    candidate_skills: list[Skill]
    assessment_queue: list[str]         # canonical skill names pending assessment
    current_skill: str
    assessment_log: list[AssessmentTurn]
    scores: dict[str, ProficiencyScore]
    gaps: list[SkillGap]
    learning_plan: Optional[LearningPlan]
    phase: Phase
    messages: Annotated[list[BaseMessage], add_messages]


# ---------------------------------------------------------------------------
# LLM response schemas (used for structured output parsing)
# ---------------------------------------------------------------------------

class SkillExtractionResponse(BaseModel):
    skills: list[Skill]


class QuestionResponse(BaseModel):
    question: str
    tests_for: str
    difficulty: int = Field(ge=1, le=5)


class ScoreResponse(BaseModel):
    score: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    follow_up_needed: bool
