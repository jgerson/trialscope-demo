"""Custom results view: result list plus a slide-in Explain drawer.

Built with Streamlit's v2 component API (rendered in the page, not an iframe). Python does the
searching and passes plain data in; all clicking, highlighting and drawer motion happens in the
browser, so exploring results needs no round trip to the server.
"""
from __future__ import annotations

import json
import re

import streamlit as st

import config
import ui

CSS = r"""
:host { --ink:#14202B; --muted:#5A6876; --line:#DDE3E8; --soft:#F5F7F9; --accent:#0B6E69;
  --notes:#8A4E0E; --notes-bg:#FBF0E1; --pubmed:#3346A8; --pubmed-bg:#ECEFFB; --trials:#0B6E69; --trials-bg:#E2F1EE;
  display:block; color:var(--ink); font-family:inherit; }
* { box-sizing:border-box; }
.tsr { container-type:inline-size; }
.grid { display:grid; grid-template-columns:minmax(0,1fr) 380px; gap:24px; align-items:start; }
.head { display:flex; align-items:baseline; gap:12px; margin:0 0 4px; }
.head h2 { font-size:22px; font-weight:700; letter-spacing:-0.015em; margin:0; }
.head .sub { color:var(--muted); font-size:13.5px; }
.list { display:flex; flex-direction:column; gap:10px; margin-top:14px; }

.card { position:relative; background:#fff; border:1px solid var(--line); border-radius:12px; padding:15px 18px 12px;
  cursor:pointer; transition:border-color .15s, box-shadow .15s; }
.card:hover { border-color:#C3CDD5; }
.card.sel { border-color:var(--accent); box-shadow:0 0 0 3px rgba(11,110,105,.12); }
.meta { display:flex; flex-wrap:wrap; column-gap:14px; row-gap:4px; align-items:center; font-size:12.5px; color:var(--muted); }
.meta .rank { margin-left:auto; font-variant-numeric:tabular-nums; }
.src { display:inline-flex; align-items:center; gap:6px; font-weight:600; }
.src::before { content:""; width:8px; height:8px; border-radius:2px; background:currentColor; }
.src.notes{color:var(--notes)} .src.pubmed{color:var(--pubmed)} .src.trials{color:var(--trials)}
.code { font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:12px; color:#3B4754; }
.card h3 { font-size:16px; font-weight:650; line-height:1.35; margin:7px 0 6px; letter-spacing:-0.01em; }
.card p { margin:0; font-size:14px; line-height:1.55; color:#3B4754; }
mark { background:#FFF0B8; color:var(--ink); padding:0 2px; border-radius:3px; }
.card .foot { display:flex; gap:16px; align-items:center; margin-top:10px; }
.btn { font:inherit; font-size:13px; color:var(--muted); background:none; border:0; padding:4px 0; cursor:pointer;
  display:inline-flex; align-items:center; gap:6px; }
.btn:hover, .card.sel .btn.explain { color:var(--accent); }
.btn:focus-visible, .card:focus-visible, .x:focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:6px; }
a.btn { text-decoration:none; }

.drawer { position:sticky; top:16px; background:#fff; border:1px solid var(--line); border-radius:14px;
  max-height:calc(100vh - 32px); overflow:auto; }
.drawer .in { padding:20px 20px 22px; animation:slide .22s ease-out; }
@keyframes slide { from { opacity:0; transform:translateX(12px); } to { opacity:1; transform:none; } }
@media (prefers-reduced-motion: reduce) { .drawer .in { animation:none; } .card { transition:none; } }
.dh { display:flex; align-items:flex-start; gap:10px; }
.dh h4 { font-size:15.5px; font-weight:650; margin:4px 0 0; line-height:1.35; flex:1; }
.x { font:inherit; border:0; background:var(--soft); color:var(--muted); width:30px; height:30px; border-radius:8px; cursor:pointer;
  flex:none; font-size:18px; line-height:1; }
.x:hover { color:var(--ink); }
.pos { display:flex; align-items:baseline; gap:10px; margin:18px 0 4px; }
.pos .big { font-size:34px; font-weight:700; letter-spacing:-0.02em; font-variant-numeric:tabular-nums; }
.pos .lbl { color:var(--muted); font-size:13.5px; }
.sec { margin-top:18px; }
.sec h5 { font-size:13px; font-weight:650; margin:0 0 8px; color:var(--ink); }
.sig { padding:10px 12px; border:1px solid var(--line); border-radius:10px; margin-bottom:8px; }
.sig .top { display:flex; justify-content:space-between; align-items:baseline; font-size:13.5px; }
.sig .top b { font-weight:600; }
.sig .r { font-variant-numeric:tabular-nums; color:var(--muted); font-size:13px; }
.bar { height:6px; background:var(--soft); border-radius:3px; margin:8px 0 6px; overflow:hidden; }
.bar i { display:block; height:100%; background:var(--accent); border-radius:3px; }
.sig .why { font-size:12.5px; color:var(--muted); line-height:1.45; }
.sig.off { background:var(--soft); }
.sig.off .top b { color:var(--muted); }
.math { font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:12.5px; background:var(--soft); border-radius:10px;
  padding:10px 12px; line-height:1.8; color:#2B3742; white-space:pre-wrap; }
.math .sum { border-top:1px solid var(--line); margin-top:4px; padding-top:4px; font-weight:600; color:var(--ink); }
.note { font-size:12.5px; color:var(--muted); line-height:1.5; margin-top:6px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip { font-size:12px; padding:3px 9px; border-radius:7px; background:var(--soft); color:#3B4754; }
.nsrow { display:grid; grid-template-columns:auto 1fr auto; gap:2px 10px; align-items:baseline; padding:12px 0;
  border-top:1px solid var(--line); font-size:13px; }
.nsrow:first-of-type { border-top:0; }
.nsrow .name { font-weight:600; }
.nsrow .ms { font-variant-numeric:tabular-nums; color:var(--ink); font-weight:600; }
.nsrow .docs { color:var(--muted); font-size:12.5px; }
.nsrow .det { grid-column:1 / 4; color:var(--muted); font-size:12.5px; line-height:1.5; }
details { margin-top:4px; grid-column:1 / 4; }
summary { cursor:pointer; color:var(--muted); font-size:12.5px; }
pre { font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:11.5px; background:var(--soft); border-radius:8px;
  padding:10px; overflow:auto; max-height:220px; margin:6px 0 0; }
.ext { margin-top:18px; display:inline-flex; align-items:center; gap:6px; color:var(--accent); font-size:13.5px;
  font-weight:600; text-decoration:none; }
.ext:hover { text-decoration:underline; text-underline-offset:3px; }
.empty { color:var(--muted); font-size:14px; padding:24px 0; }

@container (max-width: 860px) {
  .grid { grid-template-columns:minmax(0,1fr); }
  .drawer { position:fixed; left:12px; right:12px; bottom:12px; top:auto; max-height:70vh; z-index:50;
    box-shadow:0 12px 40px rgba(20,32,43,.18); display:none; }
  .drawer.open { display:block; }
}
"""

JS = r"""
export default function (component) {
  const { data, parentElement } = component;
  if (!data) return;
  let root = parentElement.querySelector('.tsr');
  if (!root) { root = document.createElement('div'); root.className = 'tsr'; parentElement.appendChild(root); }

  const STOP = new Set(['mark', 'after', 'before', 'with', 'from', 'that', 'this', 'what', 'does', 'into', 'about',
    'have', 'which', 'patient', 'patients', 'their', 'there', 'when', 'were']);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const words = [...new Set((data.query.toLowerCase().match(/[a-z0-9\-]{4,}/g) || []))]
    .filter((w) => !STOP.has(w)).sort((a, b) => b.length - a.length);
  const hl = (s) => { let t = esc(s); for (const w of words) t = t.replace(new RegExp('\\b(' + w + ')', 'gi'), '<mark>$1</mark>'); return t; };
  const nsBy = Object.fromEntries(data.namespaces.map((n) => [n.name, n]));
  const k = data.rrf_k;
  const icon = (d) => `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const infoIcon = icon('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>');
  const extIcon = icon('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>');
  let selected = null;

  function card(h) {
    const meta = h.meta.map((m) => `<span>${esc(m)}</span>`).join('');
    const code = h.code ? `<span class="code">${esc(h.code)}</span>` : '';
    const open = h.url ? `<a class="btn" href="${esc(h.url)}" target="_blank" rel="noopener">${extIcon}Open on ${h.kind === 'pubmed' ? 'PubMed' : 'ClinicalTrials.gov'}</a>` : '';
    return `<article class="card${selected === h.id ? ' sel' : ''}" data-id="${esc(h.id)}" tabindex="0">
      <div class="meta"><span class="src ${h.kind}">${esc(h.label)}</span>${code}${meta}<span class="rank">#${h.overall}</span></div>
      <h3>${hl(h.title)}</h3><p>${hl(h.snippet)}</p>
      <div class="foot"><button class="btn explain" data-id="${esc(h.id)}" aria-expanded="${selected === h.id}">${infoIcon}Explain</button>${open}</div>
    </article>`;
  }

  function signal(name, s, of, why) {
    if (!s) return `<div class="sig off"><div class="top"><b>${name}</b><span class="r">not in top ${of}</span></div>
      <div class="why">${why}</div></div>`;
    const pct = Math.max(6, Math.round(((s.of - s.rank + 1) / s.of) * 100));
    return `<div class="sig"><div class="top"><b>${name}</b><span class="r">#${s.rank} of ${s.of}</span></div>
      <div class="bar"><i style="width:${pct}%"></i></div><div class="why">${why}</div></div>`;
  }

  function explain(h) {
    const ns = nsBy[h.ns];
    const of = data.top_k;
    let html = `<div class="in"><div class="dh"><div style="flex:1"><span class="src ${h.kind}" style="font-size:12.5px">${esc(h.label)}</span>
      <h4>${esc(h.title)}</h4></div><button class="x" aria-label="Back to search overview">&times;</button></div>
      <div class="pos"><span class="big">#${h.overall}</span><span class="lbl">overall${data.multi ? `, #${h.ns_rank} in ${esc(ns.short)}` : ''}</span></div>`;

    html += `<div class="sec"><h5>What matched</h5>`;
    if (data.mode !== 'bm25') {
      html += signal('Meaning (vector)', h.vector, of, h.vector
        ? `Cosine distance ${h.vector.score.toFixed(3)} between your query and this document, both embedded with ${esc(data.embed_model)}. Lower is closer.`
        : 'Its meaning was not among the closest matches, so it arrived through keywords.');
    }
    if (data.mode !== 'vector') {
      const t = h.terms.length ? h.terms.map((w) => `<b>${esc(w)}</b>`).join(', ') : 'words in text not shown on the card';
      html += signal('Keywords (BM25)', h.bm25, of, h.bm25
        ? `Score ${h.bm25.score.toFixed(2)}. Found ${t}. Rare words that appear often in a document score higher.`
        : 'No strong keyword match, so it was found by meaning alone.');
    }
    html += `</div>`;

    if (data.mode === 'hybrid') {
      const lines = [];
      if (h.vector) lines.push(`vector  1/(${k}+${h.vector.rank}) = ${(1 / (k + h.vector.rank)).toFixed(4)}`);
      if (h.bm25) lines.push(`bm25    1/(${k}+${h.bm25.rank}) = ${(1 / (k + h.bm25.rank)).toFixed(4)}`);
      html += `<div class="sec"><h5>How the two rankings were combined</h5><div class="math">${lines.map(esc).join('\n')}<div class="sum">fused = ${h.fused.toFixed(4)}  →  #${h.ns_rank} in ${esc(ns.short)}</div></div>
        <div class="note">Reciprocal rank fusion adds 1/(${k} + rank) from each list, so appearing in both lists beats a high rank in one.</div></div>`;
    }
    if (data.multi) {
      html += `<div class="sec"><h5>Merged with the other sources</h5><div class="math">1/(${k}+${h.ns_rank}) = ${h.rrf.toFixed(4)}<div class="sum">#${h.overall} of ${data.hits.length} overall</div></div>
        <div class="note">Every source's #1 scores the same, then #2, and so on. Ties keep the source order.</div></div>`;
    }
    html += `<div class="sec"><h5>Filters on ${esc(ns.short)}</h5><div class="chips">${
      ns.filters.length ? ns.filters.map((f) => `<span class="chip">${esc(f)}</span>`).join('') : '<span class="chip">none</span>'}</div></div>`;
    if (h.url) html += `<a class="ext" href="${esc(h.url)}" target="_blank" rel="noopener">${extIcon}Open the full record</a>`;
    return html + `</div>`;
  }

  function overview() {
    const n = data.namespaces.length;
    const how = { hybrid: 'Each request runs a vector search and a BM25 keyword search together in one multi_query, then the two lists are fused.',
                  vector: 'Each request is a vector search: turbopuffer embeds the query and walks its nearest-neighbor index.',
                  bm25: 'Each request is a BM25 keyword search over the inverted index.' }[data.mode];
    let html = `<div class="in"><div class="dh"><h4 style="font-size:16px">How turbopuffer ran this search</h4></div>
      <div class="pos"><span class="big">${Math.round(data.wall_ms)} ms</span><span class="lbl">${n} request${n > 1 ? 's' : ''} in parallel</span></div>
      <div class="note" style="margin-top:0">${how}${n > 1 ? ' Results from each source are then merged by rank.' : ''}</div><div class="sec">`;
    for (const ns of data.namespaces) {
      html += `<div class="nsrow"><span class="src ${ns.kind}">${esc(ns.short)}</span>
        <span class="docs">${ns.docs ? '~' + ns.docs.toLocaleString() + ' docs' : ''}</span>
        <span class="ms">${ns.server_ms ?? 0} ms</span>
        <span class="det">${ns.hits} hits. Server time includes ${ns.embedding_ms ?? 0} ms to embed the query; ${esc(ns.cache || 'unknown')} cache; ${Math.round(ns.round_ms)} ms round trip from this app.</span>
        <details><summary>Request sent</summary><pre>${esc(ns.request)}</pre></details></div>`;
    }
    return html + `</div><div class="note" style="margin-top:14px">Select any result to see why it ranked where it did.</div></div>`;
  }

  function render() {
    const hit = data.hits.find((h) => h.id === selected);
    root.innerHTML = `<div class="grid"><div>
        <div class="head"><h2>${data.hits.length} results</h2><span class="sub">${esc(data.summary)}</span></div>
        <div class="list">${data.hits.length ? data.hits.map(card).join('') : '<div class="empty">No matches. Try fewer filters or a different scope.</div>'}</div>
      </div><aside class="drawer${hit ? ' open' : ''}" aria-live="polite">${hit ? explain(hit) : overview()}</aside></div>`;
  }

  function select(id) { selected = selected === id ? null : id; render(); }
  root.onclick = (e) => {
    if (e.target.closest('a')) return;
    if (e.target.closest('.x')) { selected = null; render(); return; }
    const el = e.target.closest('[data-id]');
    if (el) select(el.getAttribute('data-id'));
  };
  root.onkeydown = (e) => {
    if (e.key === 'Escape' && selected) { selected = null; render(); return; }
    const c = e.target.closest('.card');
    if (c && (e.key === 'Enter' || e.key === ' ') && e.target === c) { e.preventDefault(); select(c.getAttribute('data-id')); }
  };
  render();
}
"""

_component = st.components.v2.component("trialscope.results", css=CSS, js=JS)

KIND_LABEL = {"notes": "Patient note", "pubmed": "PubMed", "trials": "Clinical trial"}


def _fmt_filter(f) -> list[str]:
    if not f:
        return []
    if f[0] == "And":
        return [x for sub in f[1] for x in _fmt_filter(sub)]
    attr, op, val = f[0], f[1], f[2]
    if isinstance(val, (list, tuple)):
        val = ", ".join(map(str, val))
    words = {"In": "is", "Eq": "is", "ContainsAny": "includes", "Contains": "includes", "Gte": "≥", "Lte": "≤"}
    return [f"{attr} {words.get(op, op)} {val}"]


def _hit_payload(h: dict, query: str) -> dict:
    k = h["_kind"]
    if k == "notes":
        body = re.sub(r"(^|\n)\s*#+\s*([^\n]+)\n+", r"\1\2: ", h.get("body") or "")
        body = re.sub(r"(^|\n|:\s)\s*-\s*", r"\1", body)
        meta, code = [h.get("visit_date", ""), h.get("note_type", ""), h.get("author", "")], ""
        body = re.sub(r"\s*\n\s*", " ", body).strip()
    elif k == "pubmed":
        meta, code, body = [h.get("journal", ""), str(h.get("year") or "")], f"PMID {h.get('pmid')}", h.get("abstract") or ""
    else:
        meta, code = [h.get("status", ""), ", ".join(h.get("phases") or [])], h.get("nct_id", "")
        conds = ", ".join((h.get("conditions") or [])[:4])
        body = (f"Conditions: {conds}. " if conds else "") + (h.get("summary") or "")
    ex = h.get("_explain", {})
    return {
        "id": f"{h['_namespace']}:{h['id']}",
        "kind": k,
        "label": KIND_LABEL[k],
        "title": h.get("title") or "",
        "url": ui.link_for(h),
        "meta": [m for m in meta if m],
        "code": code,
        "snippet": body[:420] + ("…" if len(body) > 420 else ""),
        "overall": h.get("_overall", h["_rank"]),
        "ns": h["_namespace"],
        "ns_rank": h["_rank"],
        "fused": h.get("_fused", 0.0),
        "rrf": h.get("_rrf", 0.0),
        "vector": ex.get("vector"),
        "bm25": ex.get("bm25"),
        "terms": ui._terms_found(h, query),
    }


def results_view(res: dict, query: str, mode: str, top_k: int, key: str = "results") -> None:
    multi = len(res["parts"]) > 1
    namespaces = []
    for p in res["parts"]:
        perf = p.get("perf") or {}
        namespaces.append({
            "name": p["namespace"],
            "short": p["namespace"].replace(config.NS_PREFIX, ""),
            "kind": p["kind"],
            "docs": perf.get("approx_namespace_size"),
            "server_ms": perf.get("server_total_ms"),
            "embedding_ms": perf.get("embedding_ms"),
            "cache": perf.get("cache_temperature"),
            "round_ms": p["ms"],
            "hits": len(p["hits"]),
            "filters": _fmt_filter(p.get("filters")),
            "request": json.dumps(ui._strip_display(p["request"]), indent=2, default=str),
        })
    label = {"hybrid": "Hybrid", "vector": "Vector", "bm25": "BM25"}[mode]
    summary = f"{label} search across {len(namespaces)} source{'s' if multi else ''}, {res['wall_ms']:.0f} ms"
    data = {
        "query": query, "mode": mode, "rrf_k": res["rrf_k"], "multi": multi, "wall_ms": res["wall_ms"],
        "top_k": top_k, "embed_model": config.EMBED_MODEL, "summary": summary, "namespaces": namespaces,
        "hits": [_hit_payload(h, query) for h in res["hits"]],
    }
    _component(data=data, key=key)
