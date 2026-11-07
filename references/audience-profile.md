# Focu audience profile

**Version:** 2026-11-05.1
**Owner:** one person (Focu's owner)
**Change discipline:** only the owner's explicit statements or corrections can change this profile. Propose edits in chat, then commit the approved change with a dated changelog entry. Never silently infer expertise from reading behavior.

## Machine-readable settings

The following settings are the single source of truth for *all* article-writing and audio prompts. Domain IDs are stable; adding a domain is a small YAML edit.

```yaml
version: "2026-11-05.1"
default_level: working_knowledge
domains:
  computer_science:
    level: expert
    aliases: [computer science, algorithms, computing]
    provenance: owner-stated
  programming:
    level: expert
    aliases: [software engineering, code, programming]
    provenance: owner-stated
  machine_learning:
    level: expert
    aliases: [machine learning, AI, deep learning, neural networks, LLM]
    provenance: owner-stated
  sociology:
    level: novice
    aliases: [sociology, social science]
    provenance: owner-stated
levels:
  expert: "Assume technical fluency. Omit introductory definitions and elementary metaphors. Lead with precise mechanisms, original numbers, evidence quality, limitations, negative controls, independent replication, disagreements and open questions. Critique overstated claims directly; avoid ungrounded judgments."
  working_knowledge: "Give brief contextual orientation without a basics lecture; define specialized unexplained terms only where needed. Prioritize mechanism, quantitative evidence, uncertainties and counterarguments."
  novice: "Build foundational context, explain field-specific terms, and scaffold the reasoning. Use analogies only when they genuinely improve comprehension and do not replace evidence or add factual claims."
preferences:
  - "Write for one person, not an audience. English is the default."
  - "Distinguish demonstrated results from claims; evidence and citations take priority over polish."
  - "Keep all meaningful hard numbers, mechanism, limitations and negative controls."
  - "Avoid chef, sculptor, detective or other decorative metaphors in expert domains."
```

## Owner-stated background (do not elaborate beyond these statements)

- Education: PhD (owner-stated).
- Professions: software engineer; machine learning engineer (owner-stated).
- Expert level: computer science, programming and machine learning/AI (owner-stated).
- Weaker grounding: sociology and comparable subjects outside the owner's stated expertise (owner-stated example). Other unknown domains default to **working knowledge**, not to an inferred novice or expert level.

## Calibration

In articles and standalone research audio, the domain profile governs the depth, explanations and critical stance. For a secretary briefing, `references/briefing-style.md` governs order/format and this audience profile governs the level and critical stance; neither may discard source facts or numbers.

The system measures audience mismatch in QC JSON: in expert domains look for elementary analogies or basics lectures; in novice domains flag unexplained technical jargon for manual review. **Audience mismatch is reported but is not a delivery blocker** until the owner explicitly changes that policy.

Domain assignment is explicit (agent selects a domain from the owner's request/source subject, or uses the default). Never silently update profile levels because the user reads a new topic.

## Changelog

- **2026-11-05 — v2026-11-05.1:** Initial profile based only on the owner's stated PhD, software/ML background, expert technical domains, sociology as a novice-domain example, and the request for critical peer-level analysis.
