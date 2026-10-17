"""Agent handoff: ingest a researched Evidence Pack and render cited Markdown.

The research agent must gather and check evidence independently. This module
never pretends that fetching a page automatically proves a claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from focu.evidence import EvidenceStore
from focu.intents import IntentStore


def render_markdown(pack: dict, question: str) -> str:
    source_map = {s["id"]: s for s in pack["sources"]}
    lines = [f"# {question}", "", pack["summary"], "", "## Findings", ""]
    for finding in pack["findings"]:
        links = ", ".join(f"[{ref}]({source_map[ref]['url']})" for ref in finding["source_ids"])
        lines.append(f"- {finding['claim']} ({links})")
        if finding.get("uncertainty"):
            lines.append(f"  - **Uncertainty:** {finding['uncertainty']}")
    completeness = pack.get("research_completeness")
    if completeness:
        lines.extend(["", "## Research completeness", "",
                      f"Status: **{completeness['status']}**", ""])
        for label, key in (("Answered", "answered"), ("Unverified", "unverified"), ("Limitations", "limitations")):
            if completeness.get(key):
                lines.append(f"**{label}:**")
                lines.extend(f"- {item}" for item in completeness[key])
                lines.append("")
    lines.extend(["", "## Sources", ""])
    for source in pack["sources"]:
        details = ", ".join(str(source[key]) for key in ("source_type", "access_status", "verification") if source.get(key))
        lines.append(f"- **{source['id']}**: [{source['title']}]({source['url']})" + (f" — {details}" if details else ""))
    return "\n".join(lines) + "\n"


def ingest_research(db_path: str | Path, evidence_path: str | Path, output_path: str | Path) -> Path:
    intents = IntentStore(db_path)
    evidence = EvidenceStore(db_path)
    pack = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    intent = intents.get(pack["intent_id"])
    if not intent:
        raise ValueError("Evidence references unknown intent")
    if intent["status"] != "researching":
        raise ValueError("Intent must be researching before accepting evidence")
    # Validate and store before completing the intent.
    evidence.save(pack)
    markdown = render_markdown(pack, intent["question"])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    intents.transition(intent["id"], "researching", "completed", evidence_pack_id=pack["id"])
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an agent-authored evidence pack and render cited Markdown")
    parser.add_argument("--db", default="data/focu.sqlite3")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(ingest_research(args.db, args.evidence, args.output))


if __name__ == "__main__":
    main()
