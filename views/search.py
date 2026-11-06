"""Scoped search across the patient's notes, PubMed and clinical trials."""
import streamlit as st

import config
import tp_client
import ui

p = ui.current_patient()

SCOPES = ["This patient", "Literature", "Trials", "All"]
query = st.text_input("Search", key="sq", placeholder="Search notes, PubMed and trials…  e.g. trastuzumab cardiotoxicity monitoring",
                      label_visibility="collapsed")
c1, c2, _ = st.columns([2, 1.4, 1.6], vertical_alignment="bottom")
scope = c1.segmented_control("Search in", SCOPES, default="All", key="scope") or "All"
mode = c2.segmented_control("Retrieval", ["hybrid", "vector", "bm25"], default="hybrid", key="mode") or "hybrid"

fcol, rcol = st.columns([1, 3.2], gap="large")

with fcol:
    st.markdown("**Trials**")
    status = st.multiselect("Status", ["Recruiting", "Not yet recruiting", "Active not recruiting", "Completed",
                                       "Enrolling by invitation", "Terminated", "Withdrawn"], default=[])
    phases = st.multiselect("Phase", ["Early phase 1", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "N/A"])
    country = st.text_input("Country", placeholder="United States")
    use_patient = st.checkbox("Match patient age and sex", value=False, disabled=p is None,
                              help="Filters trials to ones whose age range and sex include the selected patient.")
    st.markdown("**PubMed**")
    year_from = st.slider("Published from", 2015, 2026, 2015)
    topic = st.selectbox("Topic", ["Any", "oncology", "cardiology"])
    top_k = st.slider("Results per source", 5, 30, 10)

trial_opts = {"status": status, "phases": phases, "country": country.strip() or None}
if use_patient and p:
    trial_opts.update(age=p["age"], sex=p["sex"])
pub_opts = {"year_from": year_from if year_from > 2015 else None, "topic": None if topic == "Any" else topic}

targets = []
if scope in ("This patient", "All") and p:
    targets.append((config.patient_ns(p["id"]), None))
if scope in ("Literature", "All"):
    targets.append((config.NS_PUBMED, tp_client.build_filters("pubmed", pub_opts)))
if scope in ("Trials", "All"):
    targets.append((config.NS_TRIALS, tp_client.build_filters("trials", trial_opts)))

with rcol:
    if not query:
        st.markdown("#### Search notes, PubMed and trials together")
        st.caption(
            "Exact terms such as drug names, genes and NCT ids are matched with BM25; questions in plain language are "
            "matched with vectors. Hybrid sends both in one turbopuffer request and fuses the two lists with RRF. "
            "With scope All, each namespace is queried in parallel and the lists are merged by rank. "
            "Click Explain under any result to see how it got there.")
        if p:
            st.caption(f"Patient scope uses {p['name']}'s namespace `{config.patient_ns(p['id'])}`.")
        st.stop()

    res = tp_client.search_many(targets, query, mode=mode, top_k=top_k)
    st.markdown(f"**{len(res['hits'])} results** from {len(targets)} namespace{'s' if len(targets) > 1 else ''} · "
                f"{mode}{' · merged with reciprocal rank fusion' if len(targets) > 1 else ''}")
    ui.latency_chips(res["parts"], res["wall_ms"])
    ui.explain_search(res, query, mode)

    parts = {p["namespace"]: p for p in res["parts"]}
    multi = len(res["parts"]) > 1
    for h in res["hits"]:
        ui.result_card(h, query)
        with st.popover("Explain this result", icon=":material/info:"):
            st.markdown(ui.explain_hit(h, query, parts[h["_namespace"]], res["rrf_k"], multi))

    if config.ANTHROPIC_API_KEY and res["hits"]:
        if st.button("Ask the copilot to summarize these results", type="primary"):
            st.session_state["copilot_prefill"] = f"Summarize what the {scope.lower()} sources say about: {query}"
            st.switch_page("views/workspace.py")
