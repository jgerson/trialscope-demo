"""Build the walkthrough's small dataset with TrialScope's own ingest code (trialscope-demo/ingest):
the first 20 synthetic patients and their notes (same generator and seed as the app), 20 trials from
ClinicalTrials.gov and 20 PubMed abstracts matching those patients' conditions, converted with the
loaders' to_row functions so every record has exactly the app's shape.

Usage, from the repository root: python walkthrough/build_data.py
(Needs network access to ClinicalTrials.gov and PubMed; never touches turbopuffer.)
"""
import json
import os
import sys
import time
import types

import requests

here = os.path.dirname(os.path.abspath(__file__))
repo = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(here)
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "data")
os.makedirs(out, exist_ok=True)

# Stub modules the ingest scripts import, so building data never touches turbopuffer or reads secrets.
for name in ("common", "config", "tp_client"):
    m = types.ModuleType(name)
    m.load_batches = lambda *a, **k: None
    m.DATA_DIR = out
    m.read_jsonl = lambda p: []
    m.write_jsonl = lambda *a, **k: None
    m.NS_PATIENTS = "x"
    sys.modules[name] = m
sys.path.insert(0, os.path.join(repo, "ingest"))
import patients as gen  # noqa: E402
import pubmed  # noqa: E402
import trials  # noqa: E402

# ---------------------------------------------------------------- patients and notes
pts, notes = gen.build(20)
note_rows = []
for p in pts:
    for n in notes[p["id"]]:
        note_rows.append({"patient_id": p["id"], **n})
print(f"patients: {len(pts)}, notes: {len(note_rows)}")

# ---------------------------------------------------------------- trials
# A few per patient condition, mostly recruiting; ShortStop-HER2 is the trial the app's examples use for Dana.
TRIAL_PLAN = [
    ("HER2-positive breast cancer", "RECRUITING", 3),
    ("hormone receptor positive breast cancer", "RECRUITING", 3),
    ("colorectal cancer", "RECRUITING", 3),
    ("atrial fibrillation", "RECRUITING", 3),
    ("EGFR non-small cell lung cancer", "RECRUITING", 3),
    ("melanoma", "RECRUITING", 2),
    ("HER2-positive breast cancer", "COMPLETED", 1),   # not recruiting: shows the status filter at work
    ("atrial fibrillation", "COMPLETED", 1),
]
studies, seen = [], set()


def get_study(nct):
    r = requests.get(f"{trials.API}/{nct}", params={"fields": trials.FIELDS}, timeout=60)
    r.raise_for_status()
    return r.json()


s = get_study("NCT06876714")
studies.append(s)
seen.add("NCT06876714")
for cond, status, n in TRIAL_PLAN:
    r = requests.get(trials.API, params={
        "query.cond": cond, "filter.overallStatus": status, "fields": trials.FIELDS, "pageSize": 25,
        "filter.advanced": "AREA[StudyType]INTERVENTIONAL AND AREA[Phase](PHASE2 OR PHASE3)",
        "sort": "LastUpdatePostDate:desc"}, timeout=60)
    r.raise_for_status()
    took = 0
    for st in r.json().get("studies", []):
        row = trials.to_row(st)
        if not row or row["id"] in seen or not row["summary"] or "United States" not in row["countries"]:
            continue
        studies.append(st)
        seen.add(row["id"])
        took += 1
        if took == n:
            break
    time.sleep(0.3)
trial_rows = [trials.to_row(s) for s in studies][:20]
print(f"trials: {len(trial_rows)}", sorted({t['status'] for t in trial_rows}))

# ---------------------------------------------------------------- pubmed
PUBMED_PLAN = [
    ("trastuzumab cardiotoxicity monitoring", "oncology", 4),
    ("HER2-positive breast cancer neoadjuvant pathologic complete response", "oncology", 3),
    ("EGFR exon 19 resistance after osimertinib", "oncology", 3),
    ("colorectal cancer adjuvant chemotherapy", "oncology", 3),
    ("pulsed field ablation for atrial fibrillation", "cardiology", 4),
    ("anticoagulation atrial fibrillation stroke prevention", "cardiology", 3),
    ("melanoma immunotherapy", "oncology", 2),
    ("hormone receptor positive breast cancer CDK4/6 inhibitor", "oncology", 2),
]
pmid_topic = {}
for term, topic, n in PUBMED_PLAN:  # asks for more than needed; parse() drops records without abstracts
    r = pubmed._get("esearch.fcgi", db="pubmed", retmode="json", retmax=n + 8, sort="relevance",
                    term=f"({term}) AND hasabstract[text] AND english[la] AND 2018:2026[dp]")
    took = 0
    for pmid in r.json().get("esearchresult", {}).get("idlist", []):
        if pmid not in pmid_topic:
            pmid_topic[pmid] = topic
            took += 1
        if took == n:
            break
r = pubmed._get("efetch.fcgi", method="post", db="pubmed", retmode="xml", id=",".join(pmid_topic))
articles = pubmed.parse(r.content, pmid_topic)
pubmed_rows = [pubmed.to_row(a) for a in articles][:20]
print(f"pubmed: {len(pubmed_rows)}")

for name, rows in (("patients", pts), ("notes", note_rows), ("trials", trial_rows), ("pubmed", pubmed_rows)):
    with open(os.path.join(out, f"{name}.json"), "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
print("written to", out)
