# Design Document: AI-Powered Skill Assessment & Personalised Learning Plan Agent

**Version:** 1.0  
**Date:** 2026-04-26  
**Author:** Ankit Rai  
**Status:** Draft

---

## 1. Problem Statement

A resume tells you what someone *claims* to know — not how well they actually know it. Hiring processes that rely on self-reported skill levels routinely misplace candidates: strong candidates with undersold resumes are passed over; weak candidates with polished resumes are hired into roles they can't perform.

**Goal:** Build a conversational AI agent that:
1. Accepts a Job Description (JD) and a candidate resume as inputs
2. Conducts an adaptive, Socratic assessment of each required skill
3. Scores real proficiency vs. claimed proficiency
4. Identifies skill gaps ranked by role criticality
5. Generates a personalised learning plan with curated resources and time-to-competency estimates

---

## 2. User Personas

| Persona | Goal | Pain Point |
|---|---|---|
| **Job Candidate** | Know exactly what gaps to close before applying | Generic learning paths; no honest proficiency signal |
| **Recruiter / Hiring Manager** | Validate candidates faster and more accurately | Slow screening; self-reported skills are unreliable |
| **Career Coach / L&D Professional** | Give clients a grounded, actionable upskilling plan | No objective starting-point baseline |

---

## 3. Scope

### In Scope
- Resume parsing (PDF, DOCX, plain text)
- JD parsing and skill extraction
- Conversational skill assessment (multi-turn, adaptive)
- Proficiency scoring per skill
- Gap analysis and priority ranking
- Personalised learning plan generation
- Curated resource recommendations per skill gap
- Time-to-competency estimates

### Out of Scope (v1)
- Real-time job market data integration
- Video/audio interview modality
- Integration with ATS (Applicant Tracking Systems)
- Multi-user collaboration or team assessment

---

## 4. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                            User Interface                            │
│                   Streamlit Chat UI  /  CLI                          │
└─────────────────────────────┬────────────────────────────────────────┘
                              │  (Resume PDF, JD text, chat turns)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         Orchestrator Agent                           │
│              (LangGraph StatefulGraph / Claude Tool Use)             │
│                                                                      │
│  State: { jd, resume, skills[], currentSkill, assessmentLog[],      │
│           scores{}, gaps[], learningPlan, phase }                    │
└──────┬────────────────┬──────────────────┬───────────────────────────┘
       │                │                  │
       ▼                ▼                  ▼
┌──────────────┐ ┌──────────────────┐ ┌──────────────────────────────┐
│  Input       │ │  Assessment      │ │  Learning Plan               │
│  Parser      │ │  Agent           │ │  Generator                   │
│              │ │                  │ │                              │
│ • JD skill   │ │ • Adaptive Q&A   │ │ • Gap prioritisation         │
│   extraction │ │ • Depth probing  │ │ • Adjacent skill mapping     │
│ • Resume     │ │ • Scoring rubric │ │ • Resource curation          │
│   proficiency│ │ • Per-skill      │ │ • Time-to-competency est.    │
│   mapping    │ │   verdict        │ │ • Output report              │
└──────────────┘ └──────────────────┘ └──────────────────────────────┘
       │                │                         │
       └────────────────┴─────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Claude API        │
                    │  (claude-sonnet-   │
                    │   4-6 / opus-4-7)  │
                    └───────────────────┘
```

---

## 5. Agent Design

### 5.1 Orchestrator (LangGraph)

The orchestrator manages state transitions across four phases:

```
PARSE → ASSESS → ANALYSE → PLAN → REPORT
```

Each phase is a LangGraph node. Edges are conditional — the `ASSESS` phase loops until all required skills have been assessed. The graph uses a persistent `AgentState` TypedDict passed between nodes.

```python
class AgentState(TypedDict):
    jd_raw: str
    resume_raw: str
    required_skills: list[Skill]       # extracted from JD
    candidate_skills: list[Skill]      # extracted from resume
    assessment_queue: list[str]        # skills pending assessment
    current_skill: str
    assessment_log: list[AssessmentTurn]
    scores: dict[str, ProficiencyScore]
    gaps: list[SkillGap]
    learning_plan: LearningPlan
    phase: Phase
    messages: list[BaseMessage]        # chat history for UI
```

### 5.2 Input Parser

**Inputs:** Raw JD text, resume (PDF/DOCX/text)

**Outputs:** `required_skills[]` with importance weight; `candidate_skills[]` with claimed level

**Approach:**
- PDF/DOCX → text via `pdfplumber` / `python-docx`
- Skill extraction via structured Claude output (JSON mode) using a taxonomy prompt
- Skills normalised against a canonical taxonomy (O*NET / custom) to avoid duplicates (e.g. "ML" == "Machine Learning")
- Importance weight derived from JD signal words: *required*, *must-have*, *preferred*, *nice-to-have*

```
Skill Levels: Beginner | Intermediate | Advanced | Expert
```

### 5.3 Assessment Agent

This is the core of the system. For each skill in the queue:

1. **Opening question** — scenario-based, calibrated to claimed level on resume
2. **Adaptive follow-ups** — branch based on response quality:
   - Correct/deep → harder question or move on
   - Partial → probe the gap area
   - Wrong/shallow → easier question to find floor
3. **Edge case probe** — one question testing a common misconception or production pitfall
4. **Verdict** — 1–5 proficiency score with rationale

**Questioning Strategy:**

| Question Type | Purpose | Example |
|---|---|---|
| Conceptual | Test understanding, not syntax | "Explain when you'd choose a hash join over a nested loop join" |
| Scenario-based | Test application | "Your Spark job is OOMing on a 10GB dataset. Walk me through your debugging process." |
| Trade-off | Test depth | "What are the trade-offs between dbt models and stored procedures?" |
| Edge case | Surface blind spots | "What happens to your dbt model if an upstream source starts returning NULLs?" |

**Scoring Rubric:**

| Score | Label | Signal |
|---|---|---|
| 1 | No Awareness | Cannot define the concept |
| 2 | Beginner | Knows definition; no practical experience |
| 3 | Intermediate | Can use it; struggles with edge cases |
| 4 | Advanced | Handles edge cases; understands internals |
| 5 | Expert | Can teach it; knows production pitfalls |

**Anti-gaming guardrails:**
- Questions are generated dynamically — never pulled from a static bank
- If answer quality suddenly spikes (copy-paste pattern detection), the agent probes with a follow-up that requires synthesis
- The agent tracks response latency signal from the UI as a soft confidence modifier

### 5.4 Gap Analyser

Computes a `SkillGap` for each required skill:

```
gap_severity = importance_weight × max(0, required_level − assessed_score)
```

Gaps are ranked by `gap_severity`. The top N gaps (configurable, default 5) become the focus of the learning plan.

**Gap classification:**

| Gap Size | Label | Action |
|---|---|---|
| 0 | None | Mark as strength |
| 1 | Minor | Light upskilling — docs + practice |
| 2–3 | Moderate | Structured course + project |
| 4 | Significant | Multi-week structured program |

### 5.5 Learning Plan Generator

For each prioritised gap, the plan generator:

1. **Adjacent skill mapping** — identifies what the candidate already knows that transfers (e.g. knows SQL → dbt is more accessible)
2. **Resource curation** — selects 2–4 resources per skill gap across modalities: course, official docs, hands-on project, community/blog
3. **Time estimate** — based on gap size, candidate's adjacent knowledge, and learning modality
4. **Sequencing** — orders the plan so foundational gaps are addressed before dependent skills

**Resource taxonomy:**

| Type | Examples |
|---|---|
| Structured Course | Coursera, DataCamp, official certification |
| Documentation | Official docs, style guides |
| Hands-on Project | Kaggle, personal build prompt, GitHub repo |
| Reading | Paper, blog post, architecture write-up |
| Community | Discord, Slack group, meetup |

**Time estimate heuristics:**

| Gap Size | Adjacent Knowledge | Estimate |
|---|---|---|
| Minor | Strong | 1–2 weeks |
| Minor | Weak | 2–3 weeks |
| Moderate | Strong | 3–5 weeks |
| Moderate | Weak | 5–8 weeks |
| Significant | Strong | 6–10 weeks |
| Significant | Weak | 10–16 weeks |

---

## 6. Conversation Flow (User-Facing)

```
Agent: "Hi! I'm here to assess your fit for the [Role] position. 
        I'll work through the key skills from the job description, 
        starting with [highest-priority skill]. Ready?"

[ASSESSMENT LOOP — one skill at a time]

Agent: "[Scenario question]"
User:  "[Response]"
Agent: "[Follow-up based on response quality]"
...
Agent: "Got it. Let's move on to [next skill]."

[AFTER ALL SKILLS ASSESSED]

Agent: "Assessment complete. Here's what I found:
        ✅ Strengths: SQL, Python
        ⚠️  Moderate gaps: Apache Spark, Data Modelling
        🔴 Significant gap: dbt
        
        Generating your personalised learning plan..."

[LEARNING PLAN DELIVERED]
```

---

## 7. Data Models

```python
@dataclass
class Skill:
    name: str
    canonical_name: str          # normalised
    claimed_level: int           # 1–5 from resume
    required_level: int          # 1–5 from JD
    importance: float            # 0.0–1.0

@dataclass
class ProficiencyScore:
    skill: str
    assessed_level: int          # 1–5
    confidence: float            # 0.0–1.0
    rationale: str
    question_count: int

@dataclass
class SkillGap:
    skill: str
    gap_size: int                # required − assessed
    gap_severity: float          # weighted
    label: str                   # None / Minor / Moderate / Significant

@dataclass
class LearningResource:
    title: str
    url: str
    type: str                    # course / docs / project / reading
    estimated_hours: int
    free: bool

@dataclass
class LearningPlanItem:
    skill: str
    priority: int
    gap_label: str
    adjacent_skills: list[str]   # transferable knowledge
    resources: list[LearningResource]
    estimated_weeks: str
    milestone: str               # what "done" looks like

@dataclass
class LearningPlan:
    candidate_name: str
    role: str
    generated_at: str
    strengths: list[str]
    items: list[LearningPlanItem]
    total_estimated_weeks: str
```

---

## 8. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| LLM | Claude Sonnet 4.6 (assessment) / Haiku 4.5 (parsing) | Sonnet for reasoning depth; Haiku for fast extraction |
| Agent Framework | LangGraph | Native stateful multi-step agent with cycle support |
| Document Parsing | pdfplumber, python-docx | Reliable PDF/DOCX text extraction |
| UI | Streamlit | Rapid chat UI; sufficient for hackathon scope |
| API Layer | FastAPI | Clean separation if UI needs to be decoupled |
| State Persistence | In-memory (v1) / Redis (v2) | Keep v1 simple |
| Skill Taxonomy | Custom JSON (seeded from O*NET) | Normalises skill aliases |

---

## 9. Prompt Design Principles

1. **Structured output everywhere** — all LLM calls targeting data extraction use JSON mode with a Pydantic schema. No free-form parsing.
2. **Persona consistency** — the assessment agent maintains a consistent persona: curious, direct, non-judgmental.
3. **Calibration injection** — every assessment prompt includes the candidate's claimed level so questions start at the right difficulty.
4. **Rationale capture** — each scoring call includes chain-of-thought reasoning before the score, improving accuracy and auditability.
5. **Prompt caching** — system prompts and the skill taxonomy are cached using Claude's prompt caching feature to reduce latency and cost on multi-turn conversations.

---

## 10. Key Prompt Templates

### 10.1 Skill Extraction (JD)
```
You are a technical recruiter. Extract all skills required for this role.
For each skill return:
- canonical_name (normalised)
- required_level (1–5)
- importance ("required" | "preferred" | "nice-to-have")
- category ("technical" | "domain" | "soft")

Output JSON array. Job Description:
{jd_text}
```

### 10.2 Assessment Question Generation
```
You are assessing a candidate's proficiency in {skill}.
Their claimed level: {claimed_level}/5.
Questions asked so far: {previous_questions}
Last response quality: {quality_signal}  # strong / partial / weak

Generate ONE question. Rules:
- Start at claimed level difficulty; adjust based on quality signal
- Scenario or trade-off format — no trivia or definition questions
- Do not repeat topics already covered
- Output: {"question": "...", "tests_for": "...", "difficulty": 1–5}
```

### 10.3 Response Scoring
```
Skill: {skill}
Question asked: {question}
Candidate response: {response}

Score the response 1–5 using this rubric:
1 = No awareness, 2 = Beginner, 3 = Intermediate, 4 = Advanced, 5 = Expert

Think step by step, then output:
{"score": N, "confidence": 0.0–1.0, "rationale": "...", "follow_up_needed": bool}
```

---

## 11. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Assessment latency (per turn) | < 3 seconds |
| Full assessment completion time | < 25 minutes for 5 skills |
| Scoring consistency | Same responses ±1 score on re-run |
| Resume parsing accuracy | > 90% skill extraction recall |
| Learning plan generation time | < 10 seconds after assessment |

---

## 12. Failure Modes & Mitigations

| Failure | Mitigation |
|---|---|
| Candidate gives evasive / one-word answers | Agent probes with "Can you give me a concrete example?" max 2 retries; then marks confidence low |
| LLM hallucinates a resource URL | Resources are selected from a curated seed list; LLM fills in context, not URLs |
| Skill not in taxonomy | Fuzzy match + fallback to raw skill name; log for taxonomy expansion |
| Resume text extraction fails | Graceful fallback: ask candidate to paste skills manually |
| Assessment feels like an interrogation | Persona prompt enforces conversational tone; max 4 questions per skill |

---

## 13. Evaluation Plan

| Metric | Method |
|---|---|
| Scoring accuracy | Human evaluator blind-rates 20 transcripts; compare to agent scores |
| Calibration | Run same candidate through twice; measure score variance |
| Plan relevance | Hiring manager rates learning plan quality (1–5) for 10 candidates |
| Candidate experience | Post-session NPS survey |
| Parsing recall | Manual annotation of 20 JD+resume pairs; F1 score |

---

## 14. Implementation Phases

### Phase 1 — Core Loop (Hackathon Demo)
- [ ] Input parsing (JD + resume)
- [ ] Conversational assessment for top 3 skills
- [ ] Scoring and gap analysis
- [ ] Basic learning plan output (text)
- [ ] Streamlit chat UI

### Phase 2 — Polish
- [ ] Full skill taxonomy with normalisation
- [ ] Structured learning plan with resource curation
- [ ] Time-to-competency estimates
- [ ] PDF report export

### Phase 3 — Production Hardening
- [ ] Session persistence (Redis)
- [ ] Rate limiting & auth
- [ ] ATS integration webhook
- [ ] A/B testing framework for question strategies

---

## 15. File Structure

```
skill-assessment-agent/
├── agents/
│   ├── orchestrator.py        # LangGraph graph definition
│   ├── parser.py              # JD + resume parsing agent
│   ├── assessor.py            # Conversational assessment agent
│   └── planner.py             # Learning plan generator
├── models/
│   └── schemas.py             # Pydantic data models
├── prompts/
│   ├── extraction.py          # JD/resume extraction prompts
│   ├── assessment.py          # Question generation + scoring prompts
│   └── planning.py            # Learning plan generation prompts
├── data/
│   └── skill_taxonomy.json    # Canonical skill list + aliases
├── utils/
│   ├── document_loader.py     # PDF/DOCX → text
│   └── scoring.py             # Gap severity calculation
├── app.py                     # Streamlit UI
├── main.py                    # CLI entry point
├── requirements.txt
├── .env.example
└── DESIGN.md
```

---

## 16. Open Questions

1. **Skill taxonomy scope** — Should we seed from O*NET (broad but generic) or build a tech-focused custom list (narrow but precise)?
2. **Resource curation** — Curated static seed list vs. real-time web search? Static is more reliable for a demo; search adds freshness.
3. **Assessment depth vs. speed** — 4 questions per skill × 5 skills = ~20 turns. Is that acceptable UX or should we offer a "quick mode" (2 questions)?
4. **Scoring transparency** — Should the agent reveal scores to the candidate in real time, or only in the final report?
5. **Soft skills** — JDs often list "communication" or "leadership". Include in assessment or exclude from v1?

---

*This document is a living design. Update open questions and implementation phases as decisions are made.*
