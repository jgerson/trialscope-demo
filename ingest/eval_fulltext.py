"""Does full text find answers that abstracts miss? A 10-question check.

Each question asks for a detail from an article's Methods or Results. For each, we search
  (a) ts-pubmed abstracts, restricted to the same 2,000 papers that have full text, and
  (b) ts-pmc full-text passages, collapsed to one result per article,
and record the rank of the target paper and whether the text we'd show contains the answer.

    python ingest/eval_fulltext.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import tp_client as t  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# (question, target PMID, text that must appear in what we show for it to count as "answer shown")
QUESTIONS = [
    ("How was non-structural palpitation defined in adolescents, including age range and Holter monitoring?", "41829886", "24-h ambulatory ECG"),
    ("What sensitivity and specificity did X-ray scattering achieve separating breast cancer from fibroadenoma?", "41752426", "specificity of 0.79"),
    ("What thermal conductivity and heat capacity of cardiac tissue were used to model cooling of spiral waves?", "38960373", "0.7 W"),
    ("What was the primary endpoint of the randomized trial of electroanatomical mapping during pentaspline pulsed field ablation?", "42615914", "eccentricity index"),
    ("What hearing threshold in decibels defined hearing loss in the Framingham dementia analysis?", "41555782", "25 dB"),
    ("What tissue microarray core size was used for immune checkpoint staining in resected colorectal cancer?", "39485029", "1 mm"),
    ("What is the projected ICD-11 stroke incidence rate in Wales per 100,000?", "42486476", "142.6"),
    ("How many points did the ICARS ataxia score improve after kTMP stimulation in cerebellar stroke?", "42726360", "8-point"),
    ("Which panel of normals was used for GATK CNV when benchmarking copy number calling on FFPE samples?", "41689134", "1000 genomes"),
    ("What pixel resolution did the micro-LED matrices have for optogenetic control of cardiac monolayers?", "41684280", "0.9 mm"),
]


def main() -> None:
    selected = [json.loads(line) for line in open(os.path.join(DATA, "pmc_selected.jsonl"))]
    pmids = [s["pmid"] for s in selected]
    abstract_filter = ("pmid", "In", pmids)

    rows = []
    for q, pmid, answer in QUESTIONS:
        a = t.search_namespace(config.NS_PUBMED, q, "hybrid", abstract_filter, 10)
        a_rank = next((h["_rank"] for h in a["hits"] if str(h.get("pmid")) == pmid), None)
        a_hit = next((h for h in a["hits"] if str(h.get("pmid")) == pmid), None)
        a_shown = bool(a_hit and answer.lower() in (a_hit.get("abstract") or "").lower())

        # Full text: fetch 50 passages, keep the best per article (same as the app).
        f = t.search_namespace(config.NS_PMC, q, "hybrid", None, 50)
        seen, articles = set(), []
        for h in f["hits"]:
            if h["pmid"] in seen:
                continue
            seen.add(h["pmid"])
            articles.append(h)
        f_rank = next((i for i, h in enumerate(articles[:10], 1) if str(h["pmid"]) == pmid), None)
        f_hit = next((h for h in articles[:10] if str(h["pmid"]) == pmid), None)
        f_shown = bool(f_hit and answer.lower() in (f_hit.get("passage") or "").lower())
        rows.append({"q": q, "abstract_rank": a_rank, "abstract_shows_answer": a_shown,
                     "fulltext_rank": f_rank, "fulltext_shows_answer": f_shown,
                     "section": f_hit.get("section") if f_hit else None})

    print(f"{'#':>2}  {'abstract':>12}  {'full text':>12}  section of best passage")
    for i, r in enumerate(rows, 1):
        fmt = lambda rank, shown: (f"#{rank}" if rank else "miss") + (" ✓" if shown else "")
        print(f"{i:>2}  {fmt(r['abstract_rank'], r['abstract_shows_answer']):>12}  "
              f"{fmt(r['fulltext_rank'], r['fulltext_shows_answer']):>12}  {(r['section'] or '')[:70]}")
    n = len(rows)
    for label, k in (("abstracts", "abstract"), ("full text", "fulltext")):
        found = sum(1 for r in rows if r[f"{k}_rank"])
        top3 = sum(1 for r in rows if r[f"{k}_rank"] and r[f"{k}_rank"] <= 3)
        shown = sum(1 for r in rows if r[f"{k}_shows_answer"])
        print(f"{label:>10}: paper in top 10 for {found}/{n}, top 3 for {top3}/{n}, answer visible for {shown}/{n}")
    json.dump(rows, open(os.path.join(DATA, "eval_fulltext.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
