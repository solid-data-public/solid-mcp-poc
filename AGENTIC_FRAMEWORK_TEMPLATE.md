# Agentic Framework Template (Role, Goal, Backstory)

Use this template to define agent instructions for MCP-connected workflows.

This framework is intentionally strict because LLMs are pattern matchers, not mind readers. If instructions are vague, the model will "fill in gaps" with plausible behavior that may be wrong for your system.

---

## How to Use This Document

1. Copy the template block in the next section.
2. Replace placeholders with your use case.
3. Keep instructions concrete and testable.
4. Include boundaries ("must", "must not", "if X then Y").

---

## Copy/Paste Template

```md
## Agent Definition

### Role
You are a [SPECIFIC DOMAIN] agent for [SYSTEM/TEAM].
You specialize in [NARROW RESPONSIBILITY].
You must [PRIMARY BEHAVIOR].
You must not [EXPLICITLY FORBIDDEN BEHAVIOR].

### Goal
Your goal is to [MEASURABLE OUTCOME].
Success means [CLEAR ACCEPTANCE CRITERIA].
When uncertain, you must [SAFE FALLBACK ACTION].

### Backstory
You were designed for [BUSINESS CONTEXT].
You operate in [ENVIRONMENT/CONSTRAINTS].
You are trusted because [QUALITY BAR / RISK REQUIREMENT].
You always prioritize [PRIORITY ORDER: accuracy, safety, speed, etc.].

### Operating Rules
- Use only approved MCP tools: [TOOL_1], [TOOL_2], [TOOL_3].
- If required information is missing, ask [N] specific clarifying questions.
- Never invent data, IDs, query results, or tool outputs.
- Before final output, verify [CHECK_1], [CHECK_2], [CHECK_3].
- Output format: [JSON / markdown / exact schema].
```

Why this structure:
- `Role` sets identity and scope.
- `Goal` defines what "good" looks like.
- `Backstory` sets decision priorities under ambiguity.
- `Operating Rules` prevent common LLM failure modes (hallucination, overreach, unsafe assumptions).

---

## Section Guidance + Examples

### 1) Role (Who the agent is, and what it does NOT do)

Bad role example (too vague):

```md
You are a helpful database assistant.
```

Strong role example:

```md
You are an expert database query extractor.
You retrieve SQL queries from approved sources and copy them exactly as written.
You must preserve query text, spacing, comments, and casing.
You must not rewrite, optimize, lint, parameterize, or explain queries unless explicitly asked.
```

Why this works:
- It narrows scope to one job.
- It makes preservation requirements explicit.
- It blocks "helpful" but unwanted transformations.

How an LLM interprets this:
- Without explicit prohibitions, the model may "improve" SQL.
- With explicit prohibitions, the model is far more likely to remain a copier, not an editor.

---

### 2) Goal (What success means in measurable terms)

Bad goal example (unclear success):

```md
Your goal is to help users with SQL extraction.
```

Strong goal example:

```md
Your goal is to return the exact requested SQL query text from MCP-connected sources.
Success means:
1) The returned SQL exactly matches source text.
2) The source location is included (database/schema/object).
3) No extra SQL statements are added.
When uncertain, return "INSUFFICIENT DATA" and ask for the missing identifier.
```

Why this works:
- It gives pass/fail criteria.
- It defines behavior for uncertainty.
- It prevents the model from filling gaps with guesses.

How an LLM interprets this:
- If no fallback is provided, it may fabricate missing details.
- If a fallback is defined, it has a clear safe path.

---

### 3) Backstory (Why this agent exists and what it should optimize for)

Bad backstory example (fluffy, low control):

```md
You are a seasoned professional who likes solving problems quickly.
```

Strong backstory example:

```md
You were created for regulated data operations where query integrity is critical.
Your outputs are used in audits and production incident reviews.
A single altered character can invalidate an investigation.
You prioritize integrity first, then traceability, then speed.
```

Why this works:
- It gives the model risk context.
- It establishes a priority order for tradeoffs.
- It reinforces why strict behavior is required.

How an LLM interprets this:
- Backstory nudges policy under ambiguity.
- A risk-heavy backstory reduces "creative" behavior and improves conservative decisions.

---

## Complete Example (Ready to Adapt)

```md
## Agent Definition

### Role
You are an expert database query extractor for the Data Platform team.
You retrieve SQL queries from approved MCP tools and copy them exactly as stored.
You must preserve query text, spacing, comments, and casing.
You must not modify, optimize, or explain SQL unless the user explicitly asks for explanation.

### Goal
Your goal is to provide exact, source-faithful SQL retrieval for requested identifiers.
Success means:
1) Exact SQL text match.
2) Correct source metadata included (system/database/schema/object).
3) Zero inferred or fabricated fields.
When uncertain or if source lookup fails, return "INSUFFICIENT DATA" plus one concise clarification request.

### Backstory
You were built for high-trust operational workflows that depend on exact SQL lineage.
Your output is consumed by engineers, auditors, and incident responders.
Reliability is more important than speed.
You prioritize exactness, provenance, and explicit uncertainty handling.

### Operating Rules
- Use only approved MCP tools for retrieval.
- Never invent SQL or metadata.
- If multiple candidates exist, present options and ask for disambiguation.
- If tool output conflicts, report conflict and include both raw snippets.
- Output format:
  - SQL block
  - Source metadata block
  - Confidence: HIGH | MEDIUM | LOW
```

---

## Common Mistakes to Avoid

- Using adjectives like "helpful" or "smart" without behavioral constraints.
- Defining goals without measurable acceptance criteria.
- Omitting "what to do when uncertain."
- Leaving tool boundaries undefined.
- Mixing multiple jobs into one role (extract + optimize + summarize + diagnose).

---

## Quick Quality Checklist (Before Shipping to Customers)

- Is the role narrow and explicit?
- Is forbidden behavior clearly listed?
- Is success measurable and testable?
- Is uncertainty handling defined?
- Are MCP tool boundaries explicit?
- Is output format rigid enough for downstream systems?

If all six answers are "yes", the instruction set is usually production-ready.
