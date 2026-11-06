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
.block-container {padding-top: 4.25rem; max-width: 1500px;}
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
