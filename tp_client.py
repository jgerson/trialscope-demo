"""Thin wrapper around the turbopuffer SDK: schemas, writes and the three search modes.

Every searchable namespace stores its searchable text in one `text` attribute that is
both BM25-indexed and natively embedded, so one attribute serves vector, BM25 and hybrid.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import turbopuffer

import config

# ---------------------------------------------------------------- schemas

_TEXT = {
    "type": "string",
    "full_text_search": True,
    "embed": config.EMBED_MODEL,
}
_STORED = {"type": "string", "filterable": False}  # returned for display only

SCHEMAS = {
    "trials": {
        "text": _TEXT,
        "title": _STORED,
        "summary": _STORED,
        "nct_id": {"type": "string"},
        "status": {"type": "string"},
        "phases": {"type": "[]string"},
        "conditions": {"type": "[]string"},
        "countries": {"type": "[]string"},
        "sponsor": {"type": "string"},
        "start_year": {"type": "int"},
        "min_age": {"type": "int"},
        "max_age": {"type": "int"},
        "sex": {"type": "string"},
    },
    "pubmed": {
        "text": _TEXT,
        "title": _STORED,
        "abstract": _STORED,
        "pmid": {"type": "string"},
        "journal": {"type": "string"},
        "year": {"type": "int"},
        "pub_types": {"type": "[]string"},
        "mesh": {"type": "[]string"},
        "topic": {"type": "string"},
    },
    "notes": {
        "text": _TEXT,
        "title": _STORED,
        "body": _STORED,
        "note_type": {"type": "string"},
        "visit_date": {"type": "string"},
        "author": {"type": "string"},
    },
}

# What each kind returns in search results
DISPLAY_ATTRS = {
    "trials": ["title", "summary", "nct_id", "status", "phases", "conditions", "countries", "sponsor", "start_year"],
    "pubmed": ["title", "abstract", "pmid", "journal", "year", "pub_types", "topic"],
    "notes": ["title", "body", "note_type", "visit_date", "author"],
}


def kind_of(namespace: str) -> str:
    if namespace == config.NS_TRIALS:
        return "trials"
    if namespace == config.NS_PUBMED:
        return "pubmed"
    return "notes"


# ---------------------------------------------------------------- client


@lru_cache(maxsize=1)
def client() -> turbopuffer.Turbopuffer:
    if not config.TURBOPUFFER_API_KEY:
        raise RuntimeError("TURBOPUFFER_API_KEY is not set (add it to .env)")
    return turbopuffer.Turbopuffer(
        api_key=config.TURBOPUFFER_API_KEY,
        region=config.TURBOPUFFER_REGION,
        max_retries=4,
    )


def ns(name: str):
    return client().namespace(name)


def _row_dict(row) -> dict:
    d = row.model_dump() if hasattr(row, "model_dump") else dict(row)
    extra = getattr(row, "model_extra", None) or {}
    d.update(extra)
    d.pop("vector", None)
    return d


# ---------------------------------------------------------------- writes


def upsert(namespace: str, rows: list[dict], kind: str | None = None, attempts: int = 6) -> float:
    """Upsert rows with the namespace's schema. Retries on rate limits. Returns seconds taken."""
    kind = kind or kind_of(namespace)
    schema = SCHEMAS.get(kind)
    kwargs = {"upsert_rows": rows}
    if schema:
        kwargs["schema"] = schema
        if any(v.get("embed") for v in schema.values()):
            kwargs["distance_metric"] = config.DISTANCE_METRIC
    t0 = time.perf_counter()
    for i in range(attempts):
        try:
            ns(namespace).write(**kwargs)
            return time.perf_counter() - t0
        except turbopuffer.RateLimitError:
            time.sleep(min(60, 5 * 2**i))
        except turbopuffer.APIStatusError as e:
            if e.status_code >= 500 and i < attempts - 1:
                time.sleep(3 * (i + 1))
                continue
            raise
    raise RuntimeError(f"upsert to {namespace} kept hitting rate limits")


# ---------------------------------------------------------------- search

MODES = ("hybrid", "vector", "bm25")
RRF_K = 60  # reciprocal rank fusion constant, turbopuffer's default


def search_namespace(namespace: str, query: str, mode: str = "hybrid", filters=None, top_k: int = config.TOP_K) -> dict:
    """Search one namespace. Returns {"hits": [...], "ms": client ms, "server_ms": ..., "embedding_ms": ...}."""
    kind = kind_of(namespace)
    include = DISPLAY_ATTRS[kind]
    base = {"top_k": top_k, "include_attributes": include}
    if filters:
        base["filters"] = filters
    vec = {**base, "rank_by": ("text", "ANN", ("Embed", query))}
    txt = {**base, "rank_by": ("text", "BM25", query)}

    request = {"vector": vec, "bm25": txt, "hybrid": {"queries": [vec, txt]}}[mode]

    t0 = time.perf_counter()
    try:
        if mode == "vector":
            res = ns(namespace).query(**vec)
            lists, perf = {"vector": res.rows or []}, res.performance
        elif mode == "bm25":
            res = ns(namespace).query(**txt)
            lists, perf = {"bm25": res.rows or []}, res.performance
        else:
            # One request, two ranked lists back. They are fused below with the same RRF formula
            # turbopuffer's rerank_by=("RRF",) uses (k=60), keeping each list's rank for the explainer.
            res = ns(namespace).multi_query(queries=[vec, txt])
            results = res.results or []
            lists = {"vector": results[0].rows or [] if results else [],
                     "bm25": results[1].rows or [] if len(results) > 1 else []}
            perf = res.performance
    except turbopuffer.NotFoundError:
        return {"namespace": namespace, "kind": kind, "hits": [], "ms": 0, "server_ms": 0, "embedding_ms": 0,
                "mode": mode, "filters": filters, "request": request, "perf": {}}
    ms = (time.perf_counter() - t0) * 1000

    # Collect each document's rank and score in every list it appeared in.
    docs: dict[str, dict] = {}
    for list_name, rows in lists.items():
        for rank, r in enumerate(rows, 1):
            d = _row_dict(r)
            score = d.pop("$dist", None)
            doc = docs.setdefault(d["id"], {**d, "_explain": {}})
            doc["_explain"][list_name] = {"rank": rank, "score": score, "of": len(rows)}

    for doc in docs.values():
        ex = doc["_explain"]
        doc["_fused"] = sum(1.0 / (RRF_K + v["rank"]) for v in ex.values())
    ordered = sorted(docs.values(), key=lambda d: d["_fused"], reverse=True)[:top_k]

    hits = []
    for rank, d in enumerate(ordered, 1):
        d["_rank"] = rank
        d["_score"] = d["_fused"] if mode == "hybrid" else next(iter(d["_explain"].values()))["score"]
        d["_namespace"] = namespace
        d["_kind"] = kind
        hits.append(d)

    perf_fields = ("server_total_ms", "query_execution_ms", "embedding_ms", "embedding_tokens", "cache_temperature",
                   "cache_hit_ratio", "approx_namespace_size", "exhaustive_search_count")
    return {
        "namespace": namespace,
        "kind": kind,
        "hits": hits,
        "ms": round(ms, 1),
        "server_ms": getattr(perf, "server_total_ms", None),
        "embedding_ms": getattr(perf, "embedding_ms", None),
        "mode": mode,
        "filters": filters,
        "request": request,
        "perf": {f: getattr(perf, f, None) for f in perf_fields},
    }


def search_many(targets: list[tuple[str, object]], query: str, mode: str = "hybrid", top_k: int = config.TOP_K,
                rrf_k: int = RRF_K) -> dict:
    """Query several namespaces in parallel and merge with reciprocal rank fusion.

    targets: list of (namespace, filters_or_None).
    """
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(targets)))) as pool:
        parts = list(pool.map(lambda t: search_namespace(t[0], query, mode, t[1], top_k), targets))
    wall_ms = (time.perf_counter() - t0) * 1000

    merged = []
    for p in parts:
        for h in p["hits"]:
            h["_rrf"] = 1.0 / (rrf_k + h["_rank"])
            merged.append(h)
    # Ties (same rank in different namespaces) keep the order of the targets list.
    merged.sort(key=lambda h: h["_rrf"], reverse=True)
    for pos, h in enumerate(merged, 1):
        h["_overall"] = pos
    return {"hits": merged, "parts": parts, "wall_ms": round(wall_ms, 1), "rrf_k": rrf_k}


# ---------------------------------------------------------------- filters


def build_filters(kind: str, opts: dict | None):
    """Turn simple UI/copilot options into a turbopuffer filter expression (or None)."""
    opts = opts or {}
    f = []
    if kind == "trials":
        if opts.get("status"):
            f.append(("status", "In", list(opts["status"])))
        if opts.get("phases"):
            f.append(("phases", "ContainsAny", list(opts["phases"])))
        if opts.get("country"):
            f.append(("countries", "Contains", opts["country"]))
        if opts.get("age"):
            f.append(("min_age", "Lte", int(opts["age"])))
            f.append(("max_age", "Gte", int(opts["age"])))
        if opts.get("sex"):
            f.append(("sex", "In", [opts["sex"], "All"]))
        if opts.get("start_year_from"):
            f.append(("start_year", "Gte", int(opts["start_year_from"])))
    elif kind == "pubmed":
        if opts.get("year_from"):
            f.append(("year", "Gte", int(opts["year_from"])))
        if opts.get("topic"):
            f.append(("topic", "Eq", opts["topic"]))
        if opts.get("pub_types"):
            f.append(("pub_types", "ContainsAny", list(opts["pub_types"])))
    elif kind == "notes":
        if opts.get("note_type"):
            f.append(("note_type", "In", list(opts["note_type"])))
    if not f:
        return None
    return f[0] if len(f) == 1 else ("And", f)


# ---------------------------------------------------------------- directory helpers


def list_patients() -> list[dict]:
    try:
        res = ns(config.NS_PATIENTS).query(
            rank_by=("name", "asc"), top_k=1000, include_attributes=True
        )
    except turbopuffer.NotFoundError:
        return []
    return [_row_dict(r) for r in res.rows or []]


def list_notes(patient_id: str, limit: int = 200) -> list[dict]:
    try:
        res = ns(config.patient_ns(patient_id)).query(
            rank_by=("visit_date", "desc"), top_k=limit, include_attributes=DISPLAY_ATTRS["notes"]
        )
    except turbopuffer.NotFoundError:
        return []
    return [_row_dict(r) for r in res.rows or []]
