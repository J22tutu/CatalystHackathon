# 🧠 AI-Powered Skill Assessment & Personalised Learning Plan Agent

> *A resume tells you what someone claims to know — not how well they actually know it.*

---

## Overview

This agent bridges the gap between **claimed proficiency** and **actual proficiency**. Given a Job Description and a candidate's resume, it conducts a conversational, adaptive assessment to evaluate real skill depth, identifies gaps, and generates a personalised learning plan — complete with curated resources and realistic time estimates.

No more relying on self-reported skill levels. Let the agent find out.

---

## ✨ Features

- 📄 **Resume + JD Parsing** — Extracts required skills from the job description and maps them against the candidate's resume
- 🤖 **Conversational Skill Assessment** — Engages the candidate in a dynamic, Socratic dialogue to probe real understanding of each required skill
- 📊 **Proficiency Gap Analysis** — Scores each skill and identifies where the candidate falls short
- 🗺️ **Personalised Learning Plan** — Focuses on adjacent and acquirable skills with realistic timelines
- 📚 **Curated Resource Recommendations** — Suggests targeted courses, articles, projects, and practice sets per skill gap
- ⏱️ **Time-to-Competency Estimates** — Provides honest, grounded estimates for how long each gap will take to close

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                   User Interface                │
│         (CLI / Streamlit / Web Chat)            │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   Orchestrator      │
          │   (LangGraph /      │
          │    LangChain Agent) │
          └──────────┬──────────┘
                     │
       ┌─────────────┼──────────────┐
       │             │              │
┌──────▼──────┐ ┌────▼──────┐ ┌────▼──────────┐
│  JD + Resume│ │Assessment │ │ Learning Plan │
│  Parser     │ │   Agent   │ │  Generator    │
└─────────────┘ └───────────┘ └───────────────┘
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- An OpenAI / Anthropic API key
- `pip` or `conda`

### Installation

```bash
git clone https://github.com/your-org/skill-assessment-agent.git
cd skill-assessment-agent
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Add your API keys and model preferences to .env
```

### Run

```bash
python main.py --resume path/to/resume.pdf --jd path/to/job_description.txt
```

Or launch the interactive UI:

```bash
streamlit run app.py
```

---

## 🔄 How It Works

1. **Parse Inputs** — The agent reads the Job Description and resume, extracting a list of required skills and the candidate's claimed proficiencies.

2. **Assess Each Skill** — For each skill, the agent engages the candidate in a conversational assessment — asking scenario-based questions, follow-ups, and edge cases to gauge real depth of knowledge.

3. **Score & Gap Analysis** — Based on responses, each skill is assigned a proficiency score. Gaps are ranked by criticality to the role.

4. **Generate Learning Plan** — For each gap, the agent identifies:
   - Adjacent skills the candidate can realistically build on
   - Curated learning resources (courses, docs, projects)
   - Estimated time to reach job-ready proficiency

5. **Deliver Report** — A structured summary is produced covering assessment scores, gap analysis, and the full personalised plan.

---

## 📁 Project Structure

```
skill-assessment-agent/
├── agents/
│   ├── parser.py            # Resume & JD parsing logic
│   ├── assessor.py          # Conversational assessment agent
│   └── planner.py           # Learning plan generation
├── prompts/
│   ├── assessment_prompts.py
│   └── planning_prompts.py
├── utils/
│   ├── scoring.py           # Proficiency scoring logic
│   └── resource_curator.py  # Resource recommendation engine
├── app.py                   # Streamlit UI
├── main.py                  # CLI entry point
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🧪 Example Output

```
📋 Skill Assessment Report
──────────────────────────────
Candidate : Jane Doe
Role      : Senior Data Engineer

Skill             Claimed   Assessed   Gap
──────────────────────────────────────────
Apache Spark       Expert    Intermediate  ⚠️ Moderate
dbt                Advanced  Beginner      🔴 High
SQL                Expert    Advanced      ✅ Close
Python             Advanced  Advanced      ✅ None
Data Modelling     Advanced  Intermediate  ⚠️ Moderate

📚 Personalised Learning Plan
──────────────────────────────
1. dbt (High Priority) — Est. 4–6 weeks
   • dbt Fundamentals (free) — getdbt.com/courses
   • Build a project: model your own dataset end-to-end
   • Read: dbt Best Practices Guide

2. Apache Spark — Est. 2–3 weeks
   • Databricks Learning: Apache Spark fundamentals
   • Practice: Spark on a local Docker cluster
```

---

## 🤝 Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 💡 Inspiration

Built for the belief that **potential matters more than polish** — and that the right learning plan, grounded in honest assessment, can close almost any gap.
