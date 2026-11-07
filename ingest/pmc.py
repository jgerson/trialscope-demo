"""Load full-text articles from the PubMed Central Open Access subset, chunked by section.

    python ingest/pmc.py select --limit 2000     # pick articles that match our PubMed abstracts
    python ingest/pmc.py fetch                    # download their XML from PMC's AWS bucket
    python ingest/pmc.py preview PMC6000000       # print the chunks for one article
    python ingest/pmc.py load                     # chunk and upsert into ts-pmc

Only articles that are already in ts-pubmed, open access, not retracted, and under a license that
allows commercial reuse (CC0, CC BY, CC BY-SA, CC BY-ND) are used. Each chunk is one row:
title + section heading + ~500-800 tokens of text, never crossing a section boundary.
Access follows NCBI's rules for automated retrieval: E-utilities for PMID to PMC ID lookups, the PMC cloud bucket for files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

from common import DATA_DIR, load_batches, read_jsonl, write_jsonl

import config

BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
COMMERCIAL_OK = {"CC0", "CC BY", "CC BY-SA", "CC BY-ND"}
SELECTED = os.path.join(DATA_DIR, "pmc_selected.jsonl")
XML_DIR = os.path.join(DATA_DIR, "pmc_xml")

# Chunk sizes in words (about 1.3 tokens per word in biomedical text): ~520-780 tokens, ~80 words overlap.
TARGET_WORDS, MAX_WORDS, MIN_WORDS, OVERLAP_WORDS = 450, 600, 60, 60
SKIP_SECTIONS = re.compile(r"^(supplementary|supporting information|additional files?|abbreviations|acknowledg|funding|"
                           r"author contributions?|competing interests?|conflicts? of interest|declaration|data availability|"
                           r"ethics approval|consent for publication|availability of data|electronic supplementary|disclosure|"
                           r"publisher'?s note|footnotes?)", re.I)

session = requests.Session()
session.headers["User-Agent"] = "trialscope-demo (personal learning project)"


def _get(url: str, **params) -> requests.Response:
    for attempt in range(5):
        try:
            r = session.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- select


def pmid_to_pmcid(pmids: list[str]) -> dict[str, str]:
    """Map PMIDs to PMC IDs with E-utilities esummary, 200 per request (NCBI's allowed route for automated lookups)."""
    out: dict[str, str] = {}
    for i in range(0, len(pmids), 200):
        batch = pmids[i : i + 200]
        for attempt in range(5):
            try:
                r = session.post(EUTILS + "/esummary.fcgi", timeout=90,
                                 data={"db": "pubmed", "retmode": "json", "tool": "trialscope-demo", "id": ",".join(batch)})
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(3 * (attempt + 1))
        res = r.json().get("result", {})
        for uid in res.get("uids", []):
            for aid in res[uid].get("articleids", []):
                if aid.get("idtype") == "pmc":
                    out[uid] = aid["value"]
        time.sleep(0.36)
        if (i // 200) % 50 == 0:
            print(f"  checked {min(i + 200, len(pmids)):,}/{len(pmids):,} PMIDs, {len(out):,} in PMC", flush=True)
    return out


def article_meta(pmcid: str) -> dict | None:
    """Latest version's metadata JSON from the bucket, or None if the article isn't in the OA bucket."""
    r = _get(BUCKET + "/", **{"list-type": "2", "prefix": f"{pmcid}.", "delimiter": "/"})
    versions = re.findall(r"<Prefix>(" + re.escape(pmcid) + r"\.\d+)/</Prefix>", r.text)
    if not versions:
        return None
    latest = max(versions, key=lambda v: int(v.split(".")[1]))
    m = _get(f"{BUCKET}/{latest}/{latest}.json")
    if m.status_code != 200:
        return None
    meta = m.json()
    meta["key"] = latest
    return meta


def select(limit: int) -> None:
    abstracts = {a["pmid"]: a for a in read_jsonl(os.path.join(DATA_DIR, "pubmed.jsonl"))}
    print(f"{len(abstracts):,} abstracts in ts-pubmed", flush=True)
    mapping = pmid_to_pmcid(list(abstracts))
    print(f"{len(mapping):,} have a PMC ID", flush=True)

    # Check licenses until we have enough of each topic, newest first (more likely open access).
    by_topic = {"oncology": [], "cardiology": []}
    for pmid, pmcid in mapping.items():
        by_topic.setdefault(abstracts[pmid]["topic"], []).append((abstracts[pmid]["year"], pmid, pmcid))
    picked: list[dict] = []
    for topic, items in by_topic.items():
        items.sort(reverse=True)
        want = limit // 2
        got = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            for (year, pmid, pmcid), meta in zip(items, pool.map(lambda it: article_meta(it[2]), items)):
                if got >= want:
                    break
                if not meta or not meta.get("is_pmc_openaccess") or meta.get("is_retracted"):
                    continue
                if meta.get("license_code") not in COMMERCIAL_OK:
                    continue
                picked.append({"pmid": pmid, "pmcid": pmcid, "key": meta["key"], "license": meta["license_code"],
                               "topic": topic, "year": year, "citation": meta.get("citation", "")})
                got += 1
        print(f"  {topic}: {got} articles", flush=True)
    write_jsonl(SELECTED, picked)
    print(f"selected {len(picked)} articles -> {SELECTED}")


# ---------------------------------------------------------------- fetch


def fetch() -> None:
    os.makedirs(XML_DIR, exist_ok=True)
    picked = read_jsonl(SELECTED)
    todo = [p for p in picked if not os.path.exists(os.path.join(XML_DIR, p["pmcid"] + ".xml"))]
    print(f"{len(todo)} of {len(picked)} to download", flush=True)

    def one(p):
        r = _get(f"{BUCKET}/{p['key']}/{p['key']}.xml")
        if r.status_code == 200:
            with open(os.path.join(XML_DIR, p["pmcid"] + ".xml"), "wb") as f:
                f.write(r.content)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for n, _ in enumerate(pool.map(one, todo), 1):
            if n % 250 == 0:
                print(f"  {n}/{len(todo)}", flush=True)


# ---------------------------------------------------------------- parse and chunk


def _text(el) -> str:
    """Paragraph text without literature citations, tables, figures or formulas (figure references are kept)."""
    parts: list[str] = []

    def walk(n):
        # tex-math is the LaTeX copy of a formula; the MathML copy beside it reads cleanly ("Wi=A").
        if n.tag in ("table-wrap", "fig", "table", "disp-formula", "graphic", "supplementary-material", "tex-math"):
            if n is not el and n.tail:
                parts.append(n.tail)
            return
        if n.tag == "xref" and n.get("ref-type") == "bibr":
            if n.tail:
                parts.append(n.tail)
            return
        if n.text:
            parts.append(n.text)
        for c in n:
            walk(c)
        if n is not el and n.tail:
            parts.append(n.tail)

    walk(el)
    t = re.sub(r"\s+", " ", "".join(parts))
    t = re.sub(r"\[\s*[,;–\-\s]*\]|\(\s*[,;–\-\s]*\)", "", t)  # empty brackets left by removed citations
    t = re.sub(r"(?<=\w)[,;–\-]+(?=[.;:)])", "", t)            # "Korea–." / "mortality,." -> "Korea." / "mortality."
    t = re.sub(r"\s+([.,;:)])", r"\1", t)
    return t.strip()


def clean_heading(t: str) -> str:
    """'1. INTRODUCTION' -> 'Introduction', '2.3 Statistical analysis' -> 'Statistical analysis'."""
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(?:(?:\d+|[IVXivx]+|[A-Z])(?:\.\d+)*[.)]?\s+)", "", t).strip(" .:")
    if t.isupper() and len(t) > 3:
        t = t.capitalize()
    return t


def sections(root) -> list[tuple[str, str, list[str]]]:
    """(top-level section, subsection, paragraphs) in reading order. Abstract first, then the body."""
    out: list[tuple[str, str, list[str]]] = []
    abstract = root.find(".//article-meta/abstract")
    if abstract is not None:
        paras = [t for t in (_text(p) for p in abstract.iter("p")) if t]
        if paras:
            out.append(("Abstract", "", paras))
    body = root.find(".//body")
    if body is None:
        return out

    def title_of(sec) -> str:
        t = sec.find("title")
        return clean_heading("".join(t.itertext())) if t is not None else ""

    def walk(sec, top, sub):
        paras = [t for t in (_text(p) for p in sec.findall("./p")) if t]
        if paras:
            out.append((top, sub, paras))
        for child in sec.findall("./sec"):
            t = title_of(child)
            if t and SKIP_SECTIONS.match(t):
                continue
            walk(child, top, f"{sub} › {t}" if sub and t else (t or sub))

    loose = [t for t in (_text(p) for p in body.findall("./p")) if t]
    if loose:
        out.append(("Body", "", loose))
    for sec in body.findall("./sec"):
        t = title_of(sec) or "Body"
        if SKIP_SECTIONS.match(t):
            continue
        walk(sec, t, "")
    return out


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", text) if x]


def chunk_group(units: list[tuple[str, str]]) -> list[tuple[list[str], str]]:
    """Pack (subsection, paragraph) units from one top-level section into chunks.

    Chunks aim for TARGET_WORDS and never exceed MAX_WORDS; long paragraphs are split by sentence.
    Each new chunk repeats the last sentence or two of the previous one (up to OVERLAP_WORDS).
    Returns (subsections covered, text) per chunk.
    """
    pieces: list[tuple[str, str]] = []
    for sub, para in units:
        if len(para.split()) <= MAX_WORDS:
            pieces.append((sub, para))
            continue
        cur: list[str] = []
        for sent in _sentences(para):
            if cur and len(" ".join(cur + [sent]).split()) > TARGET_WORDS:
                pieces.append((sub, " ".join(cur)))
                cur = []
            cur.append(sent)
        if cur:
            pieces.append((sub, " ".join(cur)))

    chunks: list[tuple[list[str], str]] = []
    subs: list[str] = []
    text: list[str] = []
    fresh = 0  # words added since the overlap

    def flush():
        nonlocal subs, text, fresh
        chunks.append((list(dict.fromkeys(subs)), " ".join(text)))
        tail: list[str] = []
        for sent in reversed(_sentences(" ".join(text))):
            if len(" ".join([sent] + tail).split()) > OVERLAP_WORDS:
                break
            tail.insert(0, sent)
        subs, text, fresh = [subs[-1]] if tail else [], tail, 0

    for sub, piece in pieces:
        n = len(piece.split())
        if text and fresh and len(" ".join(text).split()) + n > MAX_WORDS:
            flush()
        subs.append(sub)
        text.append(piece)
        fresh += n
        if len(" ".join(text).split()) >= TARGET_WORDS:
            flush()
    if fresh:
        if chunks and fresh < MIN_WORDS:
            # A short remainder joins the previous chunk instead of standing alone.
            prev_subs, prev_text = chunks[-1]
            overlap = len(text) - 1 if len(text) > 1 else 0
            chunks[-1] = (list(dict.fromkeys(prev_subs + subs)), prev_text + " " + " ".join(text[overlap:] if overlap else text[-1:]))
        else:
            chunks.append((list(dict.fromkeys(subs)), " ".join(text)))
    return [(s, t) for s, t in chunks if len(t.split()) >= 15]


def article_chunks(root) -> list[tuple[str, str]]:
    """(section label, passage) for the whole article, grouped by top-level section."""
    groups: dict[str, list[tuple[str, str]]] = {}
    order: list[str] = []
    for top, sub, paras in sections(root):
        if top not in groups:
            groups[top] = []
            order.append(top)
        groups[top].extend((sub, p) for p in paras)
    out = []
    for top in order:
        for subs, text in chunk_group(groups[top]):
            subs = [x for x in subs if x]
            label = top + (" › " + "; ".join(subs[:3]) + (f" (+{len(subs) - 3} more)" if len(subs) > 3 else "") if subs else "")
            out.append((label, text))
    return out


def article_rows(p: dict, xml_path: str) -> list[dict]:
    root = ET.parse(xml_path).getroot()
    title = re.sub(r"\s+", " ", "".join(root.find(".//article-meta//article-title").itertext())).strip()
    journal = root.findtext(".//journal-meta//journal-title") or ""
    chunks = article_chunks(root)
    rows = []
    for n, (sec_path, c) in enumerate(chunks, 1):
        rows.append({
            "id": f"{p['pmcid']}-{n:03d}",
            "text": f"{title}\n{sec_path}\n{c}",  # title + section give each chunk its context
            "title": title,
            "section": sec_path[:200],
            "section_top": sec_path.split(" › ")[0][:80],
            "passage": c,
            "chunk": n,
            "chunks_total": len(chunks),
            "pmid": p["pmid"],
            "pmcid": p["pmcid"],
            "journal": journal,
            "year": int(p["year"] or 0),
            "topic": p["topic"],
            "license": p["license"],
        })
    return rows


def preview(pmcid: str) -> None:
    p = next((x for x in read_jsonl(SELECTED) if x["pmcid"] == pmcid),
             {"pmcid": pmcid, "pmid": "", "year": 0, "topic": "", "license": ""})
    path = os.path.join(XML_DIR, pmcid + ".xml")
    rows = article_rows(p, path)
    print(f"{pmcid}: {len(rows)} chunks")
    for r in rows:
        w = len(r["passage"].split())
        print(f"\n--- {r['id']} | {r['section']} | {w} words\n{r['passage'][:300]} … {r['passage'][-120:]}")


def load() -> None:
    picked = read_jsonl(SELECTED)
    rows = []
    skipped = 0
    for p in picked:
        path = os.path.join(XML_DIR, p["pmcid"] + ".xml")
        if not os.path.exists(path):
            skipped += 1
            continue
        try:
            rows.extend(article_rows(p, path))
        except (ET.ParseError, AttributeError):
            skipped += 1
    print(f"{len(rows):,} chunks from {len(picked) - skipped:,} articles ({skipped} skipped)", flush=True)
    load_batches(config.NS_PMC, rows, "pmc", batch_size=100, workers=3)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["select", "fetch", "preview", "load"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--limit", type=int, default=2000)
    a = ap.parse_args()
    {"select": lambda: select(a.limit), "fetch": fetch, "preview": lambda: preview(a.arg), "load": load}[a.step]()
