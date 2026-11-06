"""Shared Streamlit helpers: styling, cached data, result and citation cards."""
from __future__ import annotations

import html
import json
import re

import streamlit as st

import config
import tp_client

CSS = """
<style>
:root {
  --ink: #14202B; --muted: #5A6876; --line: #DDE3E8; --paper: #F5F7F9; --accent: #0B6E69;
  --notes: #8A4E0E; --notes-bg: #FBF0E1; --pubmed: #3346A8; --pubmed-bg: #ECEFFB;
  --trials: #0B6E69; --trials-bg: #E2F1EE;
}
[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1440px;}
h1, h2, h3, h4 {letter-spacing: -0.015em;}
mark {background: #FFF0B8; color: var(--ink); padding: 0 2px; border-radius: 3px;}

/* hero search */
.st-key-hero [data-baseweb="input"] {min-height: 56px; background: #FFFFFF; border-radius: 14px;}
.st-key-hero input {font-size: 17px; padding-left: 18px;}

/* explain buttons sit quietly under each card */
[data-testid="stPopover"] {margin: -10px 0 8px;}
[data-testid="stPopover"] > div > button {border: none; background: transparent; min-height: 30px;
  padding: 0 6px; color: var(--muted); font-size: 13px;}
[data-testid="stPopover"] > div > button:hover {color: var(--accent); background: transparent;}

/* sidebar */
section[data-testid="stSidebar"] [data-testid="stButtonGroup"] button {padding-left: 10px; padding-right: 10px;}
.st-key-filters {background: #FFFFFF;}

/* source tags */
.ts-src {display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600;}
.ts-src::before {content: ""; width: 8px; height: 8px; border-radius: 2px; background: currentColor;}
.ts-src.notes {color: var(--notes);} .ts-src.pubmed {color: var(--pubmed);} .ts-src.trials {color: var(--trials);}

/* result card */
.ts-card {background: #FFFFFF; border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px 14px;
  margin: 0 0 6px;}
.ts-card:hover {border-color: #C3CDD5;}
.ts-card h4 {margin: 6px 0 6px; font-size: 16px; font-weight: 650; line-height: 1.35; padding: 0;}
.ts-card h4 a {color: var(--ink); text-decoration: none;}
.ts-card h4 a:hover {color: var(--accent); text-decoration: underline; text-underline-offset: 3px;}
.ts-card p {margin: 0; font-size: 14px; line-height: 1.55; color: #3B4754; max-width: 82ch;}
.ts-meta {display: flex; flex-wrap: wrap; column-gap: 14px; row-gap: 4px; align-items: center; font-size: 12.5px;
  color: var(--muted);}
.ts-meta .score {margin-left: auto; font-variant-numeric: tabular-nums;}
.ts-code {font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px; color: #3B4754;}
.ts-cite {font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px; font-weight: 600; color: var(--accent);}

/* chips */
.ts-chip {display: inline-flex; align-items: baseline; gap: 6px; font-size: 12.5px; padding: 4px 10px;
  border-radius: 8px; margin: 0 6px 6px 0; background: #EEF2F5; color: #3B4754;}
.ts-chip b {font-weight: 600;}
.ts-chip.notes {background: var(--notes-bg); color: var(--notes);}
.ts-chip.pubmed {background: var(--pubmed-bg); color: var(--pubmed);}
.ts-chip.trials {background: var(--trials-bg); color: var(--trials);}
.ts-num {font-variant-numeric: tabular-nums;}

/* patient header + sidebar card */
.ts-patient h1 {font-size: 28px; font-weight: 700; margin: 0 0 4px; padding: 0;}
.ts-patient .sub {color: var(--muted); font-size: 14px; margin-bottom: 10px;}
.ts-pcard {border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; background: #FFFFFF;}
.ts-pcard .name {font-weight: 650; font-size: 15.5px;}
.ts-pcard .dx {font-size: 13.5px; color: #3B4754; margin: 0 0 10px; line-height: 1.45;}
.ts-foot {font-size: 12px; color: var(--muted); line-height: 1.5;}

/* copilot steps */
.ts-step {font-size: 12.5px; color: #3B4754; padding: 2px 0;}
.ts-step b {color: var(--accent);}

/* sign-in */
.ts-login {text-align: left; margin: 9vh 0 18px;}
.ts-login h1 {font-size: 30px; font-weight: 700; margin: 14px 0 6px; padding: 0;}
.ts-login p {color: var(--muted); font-size: 15px; margin: 0; line-height: 1.5;}
</style>
"""

LOGIN_CSS = """
<style>
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarNav"] {display: none;}
.block-container {max-width: 440px;}
</style>
"""

ICON_SVG = ('<svg width="40" height="40" viewBox="0 0 36 36" fill="none" stroke="#0B6E69" stroke-width="2.6" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="15" cy="15" r="10"/>'
            '<path d="M29 29l-6.8-6.8"/><path d="M15 10.5v9M10.5 15h9"/></svg>')

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


def _spans(*items) -> str:
    return "".join(f"<span>{i}</span>" for i in items if i)


def result_card(h: dict, query: str = "", tag: str | None = None, show_score: bool = True) -> None:
    k = h["_kind"]
    esc = html.escape
    title = esc(h.get("title") or "")
    url = link_for(h)
    if url:
        title = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>'
    if k == "notes":
        meta = _spans(esc(h.get("visit_date") or ""), esc(h.get("note_type") or ""), esc(h.get("author") or ""))
        body = h.get("body") or ""
    elif k == "pubmed":
        meta = _spans(f'<span class="ts-code">PMID {esc(str(h.get("pmid")))}</span>', esc(h.get("journal") or ""),
                      str(h.get("year") or ""))
        body = h.get("abstract") or ""
    else:
        meta = _spans(f'<span class="ts-code">{esc(h.get("nct_id") or "")}</span>', esc(h.get("status") or ""),
                      esc(", ".join(h.get("phases") or [])))
        conds = ", ".join((h.get("conditions") or [])[:4])
        body = (f"Conditions: {conds}. " if conds else "") + (h.get("summary") or "")
    snippet = _highlight(body[:420] + ("…" if len(body) > 420 else ""), query)
    score = ""
    if show_score and h.get("_rrf") is not None:
        score = f'<span class="score">#{h.get("_overall", h["_rank"])} overall</span>'
    tag_html = f'<span class="ts-cite">[{tag}]</span>' if tag else ""
    st.markdown(
        f'<div class="ts-card"><div class="ts-meta">{tag_html}<span class="ts-src {k}">{LABEL[k]}</span>'
        f"{meta}{score}</div><h4>{title}</h4><p>{snippet}</p></div>",
        unsafe_allow_html=True,
    )


def latency_chips(parts: list[dict], wall_ms: float | None = None) -> None:
    chips = []
    for p in parts:
        name = p["namespace"].replace(config.NS_PREFIX, "")
        server = f", server {p['server_ms']} ms" if p.get("server_ms") is not None else ""
        chips.append(f'<span class="ts-chip {p["kind"]}"><b>{name}</b><span class="ts-num">{len(p["hits"])} hits in '
                     f'{p["ms"]:.0f} ms{server}</span></span>')
    if wall_ms is not None and len(parts) > 1:
        chips.append(f'<span class="ts-chip"><b>All</b><span class="ts-num">{wall_ms:.0f} ms in parallel</span></span>')
    st.markdown("".join(chips), unsafe_allow_html=True)


def sidebar_patient_card(p: dict) -> None:
    dx = f"{p['primary_dx']}" + (f", {p['stage'] if str(p['stage']).startswith(('NYHA', 'Post', 'Parox', 'Persis')) else 'stage ' + p['stage']}" if p.get("stage") else "")
    st.markdown(
        f'<div class="ts-pcard"><div class="dx">{html.escape(dx)}</div>'
        f'<span class="ts-chip notes"><b>{config.patient_ns(p["id"])}</b></span>'
        f'<span class="ts-chip"><span class="ts-num">{p["note_count"]} notes</span></span></div>',
        unsafe_allow_html=True)


# ---------------------------------------------------------------- explain

_STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "what", "how", "does", "into", "about",
         "after", "before", "have", "has", "not", "can", "who", "which", "patients", "patient"}


def _terms_found(h: dict, query: str) -> list[str]:
    text = " ".join(str(h.get(k) or "") for k in ("title", "summary", "abstract", "body")).lower()
    terms = [t for t in dict.fromkeys(re.findall(r"[a-z0-9\-]{3,}", query.lower())) if t not in _STOP]
    return [t for t in terms if re.search(rf"\b{re.escape(t)}", text)]


def _fmt_filter(f) -> str:
    if not f:
        return "none"
    if f[0] == "And":
        return " AND ".join(_fmt_filter(x) for x in f[1])
    attr, op, val = f[0], f[1], f[2]
    return f"`{attr} {op} {val}`"


def explain_hit(h: dict, query: str, part: dict, rrf_k: int, multi: bool) -> str:
    ex = h.get("_explain", {})
    ns_name = part["namespace"]
    lines = [f"**How `{ns_name}` ranked this result**", ""]
    lines.append(f"- **Filters:** {_fmt_filter(part.get('filters'))}")

    v = ex.get("vector")
    if part["mode"] in ("hybrid", "vector"):
        emb = part["perf"].get("embedding_ms")
        if v:
            lines.append(
                f"- **Meaning (vector):** #{v['rank']} of {v['of']}. turbopuffer embedded your query with "
                f"`{config.EMBED_MODEL}`{f' in {emb} ms' if emb else ''} and compared it with this document's stored "
                f"embedding: cosine distance **{v['score']:.3f}** (0 = identical meaning).")
        else:
            lines.append("- **Meaning (vector):** not in the vector top list.")

    b = ex.get("bm25")
    found = _terms_found(h, query)
    if part["mode"] in ("hybrid", "bm25"):
        if b:
            words = ", ".join(f"`{t}`" for t in found) or "matches are in text not shown on the card"
            lines.append(
                f"- **Keywords (BM25):** #{b['rank']} of {b['of']}, score **{b['score']:.2f}**. Query words found: "
                f"{words}. BM25 scores rare words that appear often in a document higher.")
        else:
            lines.append("- **Keywords (BM25):** not in the keyword top list"
                         + (", so it was found by meaning alone." if v else "."))

    if part["mode"] == "hybrid":
        parts = [f"1/({rrf_k}+{x['rank']})" for x in ex.values()]
        lines.append(f"- **Hybrid fusion (RRF):** {' + '.join(parts)} = **{h['_fused']:.4f}**, "
                     f"which ranks it **#{h['_rank']}** in `{ns_name}`. Showing up in both lists beats a high rank in one.")
    if multi:
        lines.append(f"- **Merged with other namespaces:** 1/({rrf_k}+{h['_rank']}) = {h['_rrf']:.4f} "
                     f"→ **#{h['_overall']} overall**. Each namespace's #1 ties, and so on down the lists.")
    return "\n".join(lines)


def explain_search(res: dict, query: str, mode: str) -> None:
    with st.expander("How turbopuffer ran this search"):
        n = len(res["parts"])
        st.markdown(
            f"The app sent **{n} request{'s' if n > 1 else ''} in parallel**, one per namespace, and got everything "
            f"back in **{res['wall_ms']:.0f} ms**. "
            + {"hybrid": "Each request carries two subqueries in one `multi_query`: a vector search and a BM25 "
                         "keyword search. The two ranked lists are fused with reciprocal rank fusion (RRF).",
               "vector": "Each request is a vector search: turbopuffer embeds the query and finds the nearest documents "
                         "with its approximate nearest neighbor index.",
               "bm25": "Each request is a BM25 keyword search over the inverted index."}[mode]
            + (" Results from different namespaces are then merged by rank with RRF." if n > 1 else ""))
        for p in res["parts"]:
            perf = p.get("perf") or {}
            size = perf.get("approx_namespace_size")
            st.markdown(f"**`{p['namespace']}`**" + (f" · ~{size:,} documents" if size else ""))
            cols = st.columns(4)
            cols[0].metric("Server time", f"{perf.get('server_total_ms') or 0} ms")
            cols[1].metric("Query embedding", f"{perf.get('embedding_ms') or 0} ms")
            cols[2].metric("Cache", str(perf.get("cache_temperature") or "n/a"))
            cols[3].metric("Round trip", f"{p['ms']:.0f} ms")
            unindexed = perf.get("exhaustive_search_count")
            if unindexed:
                st.caption(f"{unindexed:,} documents were scanned exhaustively rather than through the index, "
                           "typically recent writes that indexing hasn't folded in yet.")
            st.code(json.dumps(_strip_display(p["request"]), indent=2, default=str), language="json")


def _strip_display(req):
    """The request as sent, minus the list of display attributes, to keep it readable."""
    if isinstance(req, dict):
        return {k: _strip_display(v) for k, v in req.items() if k != "include_attributes"}
    if isinstance(req, list):
        return [_strip_display(x) for x in req]
    return req
