"""Shared Streamlit helpers: styling, cached data, result and citation cards."""
from __future__ import annotations

import html
import re

import streamlit as st

import config
import tp_client

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1500px;}
.ts-chip {display:inline-block; font-size:12px; padding:3px 9px; border-radius:999px; margin:0 6px 6px 0;
  background:#EEF0F3; color:#3F4A55;}
.ts-chip.teal {background:#E6F4F2; color:#0A524C;}
.ts-chip.orange {background:#FDF1E6; color:#7A3A06;}
.ts-chip.blue {background:#EAF0FE; color:#1E3A8A;}
.ts-mono {font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px;}
.ts-card {background:#FFFFFF; border:1px solid #E3E6EA; border-radius:12px; padding:14px 16px; margin-bottom:10px;}
.ts-card h4 {margin:4px 0 4px; font-size:15px; font-weight:600; line-height:1.35;}
.ts-card p {margin:0; font-size:13.5px; line-height:1.5; color:#3F4A55;}
.ts-meta {display:flex; flex-wrap:wrap; gap:8px; align-items:center; font-size:12px; color:#5B6672;}
.ts-meta .score {margin-left:auto;}
.ts-card mark {background:#FFF3C4; color:#17212B; padding:0 1px;}
.ts-badge {font-size:11.5px; font-weight:600; padding:2px 8px; border-radius:999px;}
.ts-badge.notes {background:#FDF1E6; color:#7A3A06;}
.ts-badge.pubmed {background:#EAF0FE; color:#1E3A8A;}
.ts-badge.trials {background:#E6F4F2; color:#0A524C;}
.ts-step {font-size:12.5px; color:#3F4A55; padding:2px 0;}
.ts-step b {color:#0E6E66;}
</style>
"""

LABEL = {"notes": "Patient note", "pubmed": "PubMed", "trials": "Clinical trial"}


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(ttl=600, show_spinner=False)
def patients() -> list[dict]:
    return tp_client.list_patients()


def patient_by_id(pid: str | None) -> dict | None:
    return next((p for p in patients() if p["id"] == pid), None)


def current_patient() -> dict | None:
    return patient_by_id(st.session_state.get("patient_id"))


def _highlight(text: str, query: str) -> str:
    safe = html.escape(text)
    terms = sorted({t for t in re.findall(r"[A-Za-z0-9\-]{4,}", query or "")}, key=len, reverse=True)
    for t in terms:
        safe = re.sub(rf"(?i)\b({re.escape(html.escape(t))})", r"<mark>\1</mark>", safe)
    return safe


def link_for(h: dict) -> str | None:
    if h["_kind"] == "pubmed":
        return f"https://pubmed.ncbi.nlm.nih.gov/{h.get('pmid')}/"
    if h["_kind"] == "trials":
        return f"https://clinicaltrials.gov/study/{h.get('nct_id')}"
    return None


def result_card(h: dict, query: str = "", tag: str | None = None, show_score: bool = True) -> None:
    k = h["_kind"]
    title = html.escape(h.get("title") or "")
    url = link_for(h)
    if url:
        title = f'<a href="{url}" target="_blank" style="color:#17212B;text-decoration:none">{title}</a>'
    if k == "notes":
        meta = f"{h.get('visit_date', '')} · {html.escape(h.get('note_type') or '')} · {html.escape(h.get('author') or '')}"
        body = h.get("body") or ""
    elif k == "pubmed":
        meta = f"PMID {h.get('pmid')} · {html.escape(h.get('journal') or '')} · {h.get('year')}"
        body = h.get("abstract") or ""
    else:
        meta = f"{h.get('nct_id')} · {h.get('status')} · {', '.join(h.get('phases') or [])}"
        conds = ", ".join((h.get("conditions") or [])[:4])
        body = (f"Conditions: {conds}. " if conds else "") + (h.get("summary") or "")
    snippet = _highlight(body[:420] + ("…" if len(body) > 420 else ""), query)
    score = ""
    if show_score and h.get("_rrf") is not None:
        score = f'<span class="score ts-mono">rrf {h["_rrf"]:.4f}</span>'
    tag_html = f'<span class="ts-mono" style="font-weight:600;color:#0E6E66">[{tag}]</span>' if tag else ""
    st.markdown(
        f'<div class="ts-card"><div class="ts-meta">{tag_html}<span class="ts-badge {k}">{LABEL[k]}</span>'
        f"<span>{meta}</span>{score}</div><h4>{title}</h4><p>{snippet}</p></div>",
        unsafe_allow_html=True,
    )


def latency_chips(parts: list[dict], wall_ms: float | None = None) -> None:
    color = {"notes": "orange", "pubmed": "blue", "trials": "teal"}
    chips = []
    for p in parts:
        name = p["namespace"].replace(config.NS_PREFIX, "")
        server = f" · server {p['server_ms']} ms" if p.get("server_ms") is not None else ""
        chips.append(f'<span class="ts-chip ts-mono {color[p["kind"]]}">{name} · {p["ms"]:.0f} ms{server} · {len(p["hits"])} hits</span>')
    if wall_ms is not None:
        chips.append(f'<span class="ts-chip ts-mono">total {wall_ms:.0f} ms (parallel)</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)
