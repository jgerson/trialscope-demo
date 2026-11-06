"""The copilot: Claude with two tools backed by turbopuffer.

Claude decides which namespaces to search and with which filters, then answers with
citation tags ([N1] notes, [P1] PubMed, [T1] trials) that the UI renders as cards.
Requires ANTHROPIC_API_KEY; without it the app runs search-only.
"""
from __future__ import annotations

import json
import time

import config
import tp_client

TAG = {"notes": "N", "pubmed": "P", "trials": "T"}

TOOLS = [
    {
        "name": "search",
        "description": (
            "Search TrialScope. Sources: 'patient' (the current patient's notes), 'pubmed' (oncology and cardiology "
            "abstracts, 2015 onward) and 'trials' (ClinicalTrials.gov interventional studies). Uses hybrid search "
            "(BM25 + vector, fused with RRF). Put drug names, genes and NCT ids in the query text. Use filters to "
            "narrow trials by status, phase, country, patient age and sex."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sources": {"type": "array", "items": {"type": "string", "enum": ["patient", "pubmed", "trials"]}},
                "query": {"type": "string"},
                "trial_status": {"type": "array", "items": {"type": "string",
                                 "enum": ["Recruiting", "Not yet recruiting", "Active not recruiting", "Completed",
                                          "Enrolling by invitation"]}},
                "trial_phases": {"type": "array", "items": {"type": "string",
                                 "enum": ["Early phase 1", "Phase 1", "Phase 2", "Phase 3", "Phase 4"]}},
                "country": {"type": "string", "description": "e.g. 'United States'"},
                "patient_age": {"type": "integer"},
                "patient_sex": {"type": "string", "enum": ["Female", "Male"]},
                "pubmed_year_from": {"type": "integer"},
                "top_k": {"type": "integer", "default": 8},
            },
            "required": ["sources", "query"],
        },
    },
    {
        "name": "read_patient_notes",
        "description": "Read the current patient's most recent notes in full, newest first.",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}},
    },
]

SYSTEM = """You are the TrialScope copilot, helping a physician search their own patient notes, PubMed and \
ClinicalTrials.gov. All patients are synthetic demo records.

Rules:
- Ground every claim in tool results and cite it with the tag shown in the result, like [N2], [P1] or [T3].
- For trial matching, first read the patient's notes, extract diagnosis, stage, biomarkers, age, sex and location, \
then search trials with filters (usually status Recruiting or Not yet recruiting, the patient's country, age and sex).
- Say plainly that eligibility needs physician review against the full protocol. Do not give treatment advice.
- Be concise: a short answer, then a bulleted list of the best matches with one line on why each fits.

{patient}"""


def _patient_block(patient: dict | None) -> str:
    if not patient:
        return "No patient is selected; the 'patient' source is unavailable."
    return ("Current patient: " + json.dumps({k: patient.get(k) for k in
            ("id", "name", "age", "sex", "city", "state", "primary_dx", "stage", "biomarkers")}))


class Citations:
    def __init__(self):
        self.items: dict[str, dict] = {}
        self._by_id: dict[str, str] = {}
        self._n = {"N": 0, "P": 0, "T": 0}

    def tag(self, hit: dict) -> str:
        key = f"{hit['_kind']}:{hit['id']}"
        if key not in self._by_id:
            t = TAG[hit["_kind"]]
            self._n[t] += 1
            self._by_id[key] = f"{t}{self._n[t]}"
            self.items[self._by_id[key]] = hit
        return self._by_id[key]


def _fmt_hit(tag: str, h: dict) -> str:
    k = h["_kind"]
    if k == "notes":
        return f"[{tag}] {h.get('visit_date')} · {h.get('note_type')} · {h.get('title')}\n{(h.get('body') or '')[:900]}"
    if k == "pubmed":
        return f"[{tag}] PMID {h.get('pmid')} · {h.get('journal')} {h.get('year')} · {h.get('title')}\n{(h.get('abstract') or '')[:700]}"
    return (f"[{tag}] {h.get('nct_id')} · {h.get('status')} · {', '.join(h.get('phases') or [])} · {h.get('title')}\n"
            f"Conditions: {', '.join((h.get('conditions') or [])[:6])}\n{(h.get('summary') or '')[:500]}")


def _run_tool(name: str, args: dict, patient: dict | None, cites: Citations, mode: str) -> tuple[str, dict]:
    if name == "read_patient_notes":
        if not patient:
            return "No patient selected.", {"results": 0, "ms": 0}
        t0 = time.perf_counter()
        notes = tp_client.list_notes(patient["id"], limit=int(args.get("limit") or 10))
        ms = (time.perf_counter() - t0) * 1000
        out = []
        for n in notes:
            n.update(_kind="notes", _namespace=config.patient_ns(patient["id"]))
            out.append(_fmt_hit(cites.tag(n), n))
        return "\n\n".join(out) or "No notes.", {"results": len(notes), "ms": round(ms)}

    targets = []
    for src in args.get("sources", []):
        if src == "patient" and patient:
            targets.append((config.patient_ns(patient["id"]), None))
        elif src == "pubmed":
            targets.append((config.NS_PUBMED, tp_client.build_filters("pubmed", {"year_from": args.get("pubmed_year_from")})))
        elif src == "trials":
            targets.append((config.NS_TRIALS, tp_client.build_filters("trials", {
                "status": args.get("trial_status"), "phases": args.get("trial_phases"), "country": args.get("country"),
                "age": args.get("patient_age"), "sex": args.get("patient_sex")})))
    if not targets:
        return "No valid sources.", {"results": 0, "ms": 0}
    res = tp_client.search_many(targets, args["query"], mode=mode, top_k=int(args.get("top_k") or 8))
    hits = res["hits"][:15]
    text = "\n\n".join(_fmt_hit(cites.tag(h), h) for h in hits) or "No results."
    return text, {"results": len(res["hits"]), "ms": res["wall_ms"]}


def ask(question: str, history: list[dict], patient: dict | None, mode: str = "hybrid", max_turns: int = 6) -> dict:
    """Run one copilot turn. Returns {"answer", "steps", "citations", "messages"}."""
    import anthropic

    llm = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    cites = Citations()
    steps = []
    messages = history + [{"role": "user", "content": question}]
    system = SYSTEM.format(patient=_patient_block(patient))
    t0 = time.perf_counter()

    for _ in range(max_turns):
        resp = llm.messages.create(model=config.COPILOT_MODEL, max_tokens=1500, system=system,
                                   tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            out, meta = _run_tool(block.name, dict(block.input), patient, cites, mode)
            steps.append({"tool": block.name, "input": dict(block.input), **meta})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
        messages.append({"role": "user", "content": results})

    answer = "".join(b.text for b in resp.content if b.type == "text")
    # Keep history compact: question and final answer only.
    new_history = history + [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    return {"answer": answer, "steps": steps, "citations": cites.items,
            "history": new_history, "seconds": time.perf_counter() - t0}
