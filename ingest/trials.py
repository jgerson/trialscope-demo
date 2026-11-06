"""Load interventional studies from ClinicalTrials.gov (API v2) into the trials namespace.

    python ingest/trials.py --limit 50000
"""
from __future__ import annotations

import argparse
import os
import re
import time

import requests

from common import DATA_DIR, load_batches, read_jsonl, write_jsonl

import config

API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ",".join([
    "NCTId", "BriefTitle", "OverallStatus", "Phase", "Condition", "InterventionName", "BriefSummary",
    "EligibilityCriteria", "MinimumAge", "MaximumAge", "Sex", "LocationCountry", "LeadSponsorName", "StartDate",
])
RAW = os.path.join(DATA_DIR, "trials.jsonl")


def fetch(limit: int) -> list[dict]:
    cached = read_jsonl(RAW)
    if len(cached) >= limit:
        return cached[:limit]
    studies, token = [], None
    while len(studies) < limit:
        params = {
            "pageSize": 1000,
            "fields": FIELDS,
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
            "sort": "LastUpdatePostDate:desc",
        }
        if token:
            params["pageToken"] = token
        for attempt in range(5):
            r = requests.get(API, params=params, timeout=60)
            if r.ok:
                break
            time.sleep(2 * (attempt + 1))
        r.raise_for_status()
        d = r.json()
        studies.extend(d.get("studies", []))
        token = d.get("nextPageToken")
        print(f"  fetched {len(studies):,} trials", flush=True)
        if not token:
            break
    studies = studies[:limit]
    write_jsonl(RAW, studies)
    return studies


def _age(s: str | None, default: int) -> int:
    if not s:
        return default
    m = re.match(r"(\d+)\s*(\w+)", s)
    if not m:
        return default
    n, unit = int(m.group(1)), m.group(2).lower()
    return n if unit.startswith("year") else 0


def _pretty(s: str) -> str:
    return s.replace("_", " ").capitalize()


PHASES = {"EARLY_PHASE1": "Early phase 1", "PHASE1": "Phase 1", "PHASE2": "Phase 2",
          "PHASE3": "Phase 3", "PHASE4": "Phase 4", "NA": "N/A"}


def to_row(study: dict) -> dict | None:
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    nct = ident.get("nctId")
    if not nct:
        return None
    status = p.get("statusModule", {})
    elig = p.get("eligibilityModule", {})
    title = ident.get("briefTitle", "")
    summary = (p.get("descriptionModule", {}).get("briefSummary") or "").strip()
    conditions = p.get("conditionsModule", {}).get("conditions", []) or []
    interventions = [i.get("name", "") for i in p.get("armsInterventionsModule", {}).get("interventions", []) or []]
    countries = sorted({loc.get("country") for loc in p.get("contactsLocationsModule", {}).get("locations", []) or []
                        if loc.get("country")})
    phases = [PHASES.get(x, x) for x in p.get("designModule", {}).get("phases", []) or []]
    start = (status.get("startDateStruct") or {}).get("date", "")
    criteria = (elig.get("eligibilityCriteria") or "").strip()

    text = "\n".join(filter(None, [
        f"{nct}: {title}",
        "Conditions: " + "; ".join(conditions) if conditions else "",
        "Interventions: " + "; ".join(interventions) if interventions else "",
        summary,
        "Eligibility: " + criteria[:2500] if criteria else "",
    ]))
    return {
        "id": nct,
        "text": text,
        "title": title,
        "summary": summary[:1200],
        "nct_id": nct,
        "status": _pretty(status.get("overallStatus", "UNKNOWN")),
        "phases": phases or ["N/A"],
        "conditions": conditions[:20],
        "countries": countries[:50],
        "sponsor": (p.get("sponsorCollaboratorsModule", {}).get("leadSponsor") or {}).get("name", ""),
        "start_year": int(start[:4]) if start[:4].isdigit() else 0,
        "min_age": _age(elig.get("minimumAge"), 0),
        "max_age": _age(elig.get("maximumAge"), 120),
        "sex": (elig.get("sex") or "ALL").capitalize(),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50_000)
    args = ap.parse_args()
    studies = fetch(args.limit)
    rows = [r for r in (to_row(s) for s in studies) if r]
    load_batches(config.NS_TRIALS, rows, "trials", batch_size=200)
