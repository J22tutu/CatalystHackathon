JD_EXTRACTION_PROMPT = """You are a technical recruiter parsing a job description.

Extract every skill, tool, technology, and domain competency required for this role.
For each skill return a JSON object with exactly these fields:
- "name": the skill as written in the JD
- "canonical_name": lowercase normalised name (e.g. "machine learning" not "ML")
- "required_level": integer 1–5 based on how the JD describes proficiency needed
  (1=awareness, 2=beginner, 3=intermediate, 4=advanced, 5=expert)
- "importance": float 0.0–1.0 derived from signal words
  (required/must-have → 1.0, strong/proven → 0.85, preferred/desired → 0.7, nice-to-have/bonus → 0.4)
- "category": one of "technical", "domain", "soft"

Rules:
- Normalise aliases: "ML" → "machine learning", "k8s" → "kubernetes", "JS" → "javascript"
- Do NOT invent skills not mentioned in the JD
- Exclude generic soft skills like "communication" unless explicitly listed as a requirement
- Output a JSON object with a single key "skills" containing the array

Job Description:
{jd_text}
"""

RESUME_EXTRACTION_PROMPT = """You are parsing a candidate's resume to identify their skills and experience levels.

Given the list of required skills from the job description, map each one to the candidate's
claimed proficiency based on what you find in the resume. Also extract any additional skills
the candidate has that are not in the required list.

For each skill found return a JSON object with exactly these fields:
- "name": skill name
- "canonical_name": lowercase normalised name (match the canonical names from required skills where possible)
- "claimed_level": integer 1–5 based on evidence in the resume
  (1=mentioned once/no context, 2=coursework/personal project, 3=used professionally, 4=led/owned/3+ years, 5=expert/published/taught)
- "required_level": 0 (leave as 0, will be filled by the system)
- "importance": 0.0 (leave as 0.0, will be filled by the system)
- "category": one of "technical", "domain", "soft"

Rules:
- Base claimed_level strictly on evidence in the resume — do not inflate
- If a required skill is not mentioned anywhere in the resume, still include it with claimed_level=0
- Output a JSON object with a single key "skills" containing the array

Required skills to map: {required_skills}

Resume:
{resume_text}
"""
