"""Patient workspace: a Notion-style note editor per patient, with the copilot alongside."""
import re
from datetime import date

import streamlit as st

import config
import notes as notes_mod
import tp_client
import ui

NOTE_TYPES = ["Visit note", "Result", "Phone call", "Treatment plan", "Other"]

p = ui.current_patient()
if not p:
    st.info("Pick a patient in the sidebar.")
    st.stop()
pid = p["id"]


@st.cache_data(ttl=300, show_spinner=False)
def load_notes(patient_id: str, version: int) -> list[dict]:
    return tp_client.list_notes(patient_id)


st.session_state.setdefault("notes_version", 0)
note_list = load_notes(pid, st.session_state.notes_version)

left, right = st.columns([1.65, 1], gap="large")

# ================================================================ notes
with left:
    import html as _html
    stage = p.get("stage") or ""
    stage_txt = stage if stage.startswith(("NYHA", "Post", "Parox", "Persis")) else (f"stage {stage}" if stage else "")
    st.markdown(
        f'<div class="ts-patient"><h1>{_html.escape(p["name"])}</h1>'
        f'<div class="sub">{p["age"]}-year-old {p["sex"].lower()}, {p["city"]}, {p["state"]}</div></div>'
        f'<span class="ts-chip trials"><b>{_html.escape(p["primary_dx"])}</b></span>'
        + (f'<span class="ts-chip">{stage_txt}</span>' if stage_txt else "")
        + (f'<span class="ts-chip">{_html.escape(p["biomarkers"])}</span>' if p.get("biomarkers") else ""),
        unsafe_allow_html=True)
    st.markdown("")

    NEW = "__new__"
    options = [n["id"] for n in note_list] + [NEW]
    sel_key = f"note_sel_{pid}"
    if st.session_state.get(sel_key) not in options:
        st.session_state[sel_key] = options[0]
    labels = {n["id"]: f"{n['visit_date']}   {n['title']}" for n in note_list}
    labels[NEW] = "New note"
    sel = st.selectbox("Note", options, key=sel_key, format_func=lambda i: labels[i], label_visibility="collapsed")
    note = next((n for n in note_list if n["id"] == sel), None)

    edit_tab, view_tab = st.tabs(["Edit", "Read"])
    with edit_tab:
        with st.form(f"form_{sel}", border=False):
            title = st.text_input("Title", value=note["title"] if note else "", placeholder="Visit note title")
            c1, c2 = st.columns(2)
            ntype = c1.selectbox("Type", NOTE_TYPES,
                                 index=NOTE_TYPES.index(note["note_type"]) if note and note["note_type"] in NOTE_TYPES else 0)
            vdate = c2.date_input("Visit date", value=date.fromisoformat(note["visit_date"]) if note else date.today())
            body = st.text_area("Note", value=note["body"] if note else "## Subjective\n\n\n## Assessment\n\n\n## Plan\n- ",
                                height=340, help="Markdown: ## headings, - lists")
            saved = st.form_submit_button("Save note", type="primary", disabled=config.READ_ONLY,
                                          help="Saving is turned off on this deployment" if config.READ_ONLY else None)
        if saved:
            with st.spinner("Saving to turbopuffer…"):
                res = notes_mod.save_note(pid, title, body, ntype, vdate.isoformat(),
                                          author=note["author"] if note else "Dr. Rivera (Oncology)",
                                          note_id=note["id"] if note else None)
            st.session_state.notes_version += 1
            st.session_state[sel_key] = res["id"]
            st.session_state["last_save"] = res
            st.rerun()
        if st.session_state.get("last_save"):
            r = st.session_state.last_save
            st.markdown(
                f'<span class="ts-chip trials"><b>Saved</b><span class="ts-num">written in {r["write_s"]:.2f} s, '
                f'searchable {r["visible_s"]*1000:.0f} ms later</span></span>', unsafe_allow_html=True)
    with view_tab:
        if note:
            st.markdown(f"### {note['title']}")
            st.caption(f"{note['visit_date']}, {note['note_type'].lower()} by {note['author']}")
            st.markdown(note["body"])
        else:
            st.caption("Save the note to read it here.")

    st.markdown("")
    with st.expander(f"Search {p['name'].split()[0]}'s notes", expanded=False):
        q = st.text_input("Search this patient", key=f"pq_{pid}", placeholder="e.g. ejection fraction",
                          label_visibility="collapsed")
        if q:
            r = tp_client.search_namespace(config.patient_ns(pid), q, "hybrid", None, 5)
            ui.latency_chips([r])
            for h in r["hits"]:
                ui.result_card(h, q, show_score=False)

# ================================================================ copilot
with right:
    st.markdown("### Copilot")
    st.caption("Ask about this patient, the literature or open trials. Answers cite their sources.")
    if not config.ANTHROPIC_API_KEY:
        with st.container(border=True):
            st.markdown("**The copilot is off.** Add `ANTHROPIC_API_KEY` to the app's Secrets (or `.env` locally) "
                        "and reboot to turn it on. Search and notes work without it.")
        st.stop()

    import copilot

    chats = st.session_state.setdefault("chats", {})
    turns = chats.setdefault(pid, [])
    mode = st.segmented_control("Retrieval", ["hybrid", "vector", "bm25"], default="hybrid", key="cp_mode",
                                label_visibility="collapsed")

    box = st.container(height=560, border=True)
    with box:
        if not turns:
            st.caption("Try: “Is there a recruiting trial this patient might qualify for?” or "
                       "“What does recent literature say about monitoring cardiotoxicity on trastuzumab?”")
        for t in turns:
            with st.chat_message("user"):
                st.markdown(t["q"])
            with st.chat_message("assistant"):
                res = t["res"]
                if res.get("error"):
                    st.error(res["error"])
                    continue
                steps = res["steps"]
                st.markdown(
                    "".join(f'<div class="ts-step"><b>{i}</b> {s["tool"]}({", ".join(f"{k}={v}" for k, v in s["input"].items() if v)}) '
                            f'· {s["results"]} results · {s["ms"]:.0f} ms</div>' for i, s in enumerate(steps, 1)),
                    unsafe_allow_html=True)
                st.markdown(res["answer"])
                used = [tag for tag in res["citations"] if re.search(rf"\[{tag}\]", res["answer"])]
                if used:
                    with st.expander(f"Sources ({len(used)})"):
                        for tag in used:
                            ui.result_card(res["citations"][tag], tag=tag, show_score=False)
                st.caption(f"{res['seconds']:.1f} s total")

    prefill = st.session_state.pop("copilot_prefill", None)
    q = st.chat_input("Ask about this patient, the literature or trials…")
    q = q or prefill
    if q:
        history = turns[-1]["res"].get("history", []) if turns else []
        with box:
            with st.chat_message("user"):
                st.markdown(q)
            with st.chat_message("assistant"):
                with st.spinner("Searching…"):
                    try:
                        res = copilot.ask(q, history, p, mode=mode or "hybrid")
                    except Exception as e:  # show API/key problems in the panel
                        res = {"error": f"Copilot error: {e}"}
        turns.append({"q": q, "res": res})
        st.rerun()
