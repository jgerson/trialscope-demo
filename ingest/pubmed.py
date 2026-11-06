"""Load oncology and cardiology abstracts from PubMed (NCBI E-utilities) into the pubmed namespace.

    python ingest/pubmed.py --limit 100000

ESearch returns at most 10,000 ids per query, so the corpus is collected month by month
(2015 onward) for each topic, taking an even share from every month.
"""
from __future__ import annotations

import argparse
import math
import os
import time
import xml.etree.ElementTree as ET
import calendar
from datetime import date

import requests

from common import DATA_DIR, load_batches, read_jsonl, write_jsonl

import config

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_KEY = os.environ.get("NCBI_API_KEY", "")  # optional: raises the rate limit from 3 to 10 req/s
PAUSE = 0.11 if NCBI_KEY else 0.36
TOPICS = {
    "oncology": "neoplasms[MeSH Major Topic]",
    "cardiology": "cardiovascular diseases[MeSH Major Topic]",
}
RAW = os.path.join(DATA_DIR, "pubmed.jsonl")
session = requests.Session()


def _get(path: str, method: str = "get", **params):
    params.update({"tool": "trialscope-demo"})
    if NCBI_KEY:
        params["api_key"] = NCBI_KEY
    for attempt in range(6):
        time.sleep(PAUSE)
        try:
            if method == "post":
                r = session.post(f"{EUTILS}/{path}", data=params, timeout=90)
            else:
                r = session.get(f"{EUTILS}/{path}", params=params, timeout=90)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    r.raise_for_status()
    return r


def months(start_year: int = 2015):
    today = date.today()
    y, m = start_year, 1
    while (y, m) <= (today.year, today.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def collect_ids(limit: int) -> list[tuple[str, str]]:
    month_list = list(months())
    per_slice = math.ceil(limit / len(TOPICS) / len(month_list))
    ids: dict[str, str] = {}
    for topic, term in TOPICS.items():
        for y, m in month_list:
            mm = f"{y}/{m:02d}"
            r = _get("esearch.fcgi", db="pubmed", retmode="json", retmax=per_slice, sort="relevance",
                     term=f"{term} AND hasabstract[text] AND english[la]", datetype="pdat",
                     mindate=f"{mm}/01", maxdate=f"{mm}/{calendar.monthrange(y, m)[1]:02d}")
            for pmid in r.json().get("esearchresult", {}).get("idlist", []):
                ids.setdefault(pmid, topic)
        print(f"  {topic}: {len(ids):,} ids so far", flush=True)
    return list(ids.items())[:limit]


def _text(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def parse(xml: bytes, topics: dict[str, str]) -> list[dict]:
    out = []
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        pmid = _text(art.find(".//MedlineCitation/PMID"))
        title = _text(art.find(".//ArticleTitle"))
        parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            parts.append(f"{label.title()}: {_text(ab)}" if label else _text(ab))
        abstract = "\n".join(p for p in parts if p)
        if not (pmid and title and abstract):
            continue
        year = _text(art.find(".//JournalIssue/PubDate/Year")) or _text(art.find(".//JournalIssue/PubDate/MedlineDate"))[:4]
        mesh = [_text(d) for d in art.findall(".//MeshHeading/DescriptorName")]
        out.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": _text(art.find(".//Journal/Title")),
            "year": int(year) if year[:4].isdigit() else 0,
            "pub_types": [_text(p) for p in art.findall(".//PublicationType")][:10],
            "mesh": mesh[:30],
            "topic": topics.get(pmid, ""),
        })
    return out


def fetch(limit: int) -> list[dict]:
    cached = read_jsonl(RAW)
    if len(cached) >= limit * 0.95:
        return cached[:limit]
    pairs = collect_ids(limit)
    topics = dict(pairs)
    pmids = [p for p, _ in pairs]
    articles = []
    for i in range(0, len(pmids), 200):
        r = _get("efetch.fcgi", method="post", db="pubmed", retmode="xml", id=",".join(pmids[i : i + 200]))
        articles.extend(parse(r.content, topics))
        if (i // 200) % 25 == 0:
            print(f"  fetched {len(articles):,} abstracts", flush=True)
    write_jsonl(RAW, articles)
    return articles


def to_row(a: dict) -> dict:
    text = f"{a['title']}\n{a['abstract'][:3500]}"
    if a["mesh"]:
        text += "\nMeSH: " + "; ".join(a["mesh"])
    return {
        "id": f"PMID{a['pmid']}",
        "text": text,
        "title": a["title"],
        "abstract": a["abstract"][:2000],
        "pmid": a["pmid"],
        "journal": a["journal"],
        "year": a["year"],
        "pub_types": a["pub_types"] or ["Journal Article"],
        "mesh": a["mesh"] or [""],
        "topic": a["topic"],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100_000)
    args = ap.parse_args()
    arts = fetch(args.limit)
    print(f"{len(arts):,} abstracts ready", flush=True)
    load_batches(config.NS_PUBMED, [to_row(a) for a in arts], "pubmed", batch_size=200)
