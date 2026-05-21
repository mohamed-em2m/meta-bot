---
env: default
---
Generate Internal‑Log Summary
**Goal:** Create an English summary of the agent’s response for automatic logs.

**Format:**

* Single paragraph (4–8 sentences) **or** bullet list.
* English only, factual, no commentary.

**Include:**

1. **Actions:** What the agent did (e.g., validations, API calls, reminders).
2. **Key Data:** IDs, dates, URLs, names exactly as in response.
3. **Small Talk:** Note casual phrases (e.g., “Agent said hello.”).

**Rules:**

* Resolve vague terms (e.g., replace “as before” with concrete values).
* If a required field is missing, infer it and justify in parentheses.

**Entity Entries:**
For each property or item mentioned, list its **ID** and **Name**.

**Example:**

```
- Agent validated order #12345 (ID: ORD-12345).
- Agent updated Business Manager URL to https://diib-relities.odoo.com/ .
- Agent said hello.
- Apartment A-987 (Name: Nile View) added to results.
- Inferred Location: Giza (Justification: User asked for “near the Pyramids”).
- Agent reminded user to confirm within 24 h.
```

> Apply this template to every response. Ensure each log entry is standalone, precise, and fully resolved.
