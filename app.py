"""TrialScope: patient notes, PubMed and clinical trials in one search, on turbopuffer.

    streamlit run app.py
"""
import hmac

import streamlit as st

import config
import ui

st.set_page_config(page_title="TrialScope", page_icon="🔎", layout="wide")
ui.inject_css()


def password_gate() -> None:
    """Stop the app until the visitor enters APP_PASSWORD (skipped when it isn't set)."""
    if not config.APP_PASSWORD or st.session_state.get("authed"):
        return
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("### TrialScope")
        st.caption("Personal learning project · synthetic patients · not for clinical use")
        with st.form("login", border=True):
            pw = st.text_input("Password", type="password")
            ok = st.form_submit_button("Enter", type="primary", width="stretch")
        if ok:
            if hmac.compare_digest(pw.encode(), config.APP_PASSWORD.encode()):
                st.session_state.authed = True
                st.rerun()
            st.error("Wrong password.")
    st.stop()


password_gate()

if not config.TURBOPUFFER_API_KEY:
    st.error("Set TURBOPUFFER_API_KEY in .env to start.")
    st.stop()

# ---------------------------------------------------------------- sidebar: patient picker
with st.sidebar:
    st.markdown("### TrialScope")
    st.caption(f"turbopuffer · {config.TURBOPUFFER_REGION}")
    pts = ui.patients()
    if not pts:
        st.warning("No patients yet. Run `python ingest/patients.py`.")
    else:
        if "patient_id" not in st.session_state:
            st.session_state.patient_id = min(p["id"] for p in pts)
        specialty = st.segmented_control("Panel", ["All", "Oncology", "Cardiology"], default="All", key="panel") or "All"
        shown = sorted([p for p in pts if specialty == "All" or p["specialty"] == specialty], key=lambda p: p["id"])
        ids = [p["id"] for p in shown]
        if st.session_state.patient_id not in ids and ids:
            st.session_state.patient_id = ids[0]
        st.selectbox(
            "Patient",
            ids,
            key="patient_id",
            format_func=lambda pid: next(f"{p['name']} · {p['age']} · {p['primary_dx']}" for p in shown if p["id"] == pid),
        )
        p = ui.current_patient()
        if p:
            st.markdown(
                f'<span class="ts-chip orange ts-mono">{config.patient_ns(p["id"])}</span>'
                f'<span class="ts-chip">{p["note_count"]} notes</span>',
                unsafe_allow_html=True,
            )
    st.divider()
    if config.ANTHROPIC_API_KEY:
        st.caption(f"Copilot on · {config.COPILOT_MODEL}")
    else:
        st.caption("Copilot off · set ANTHROPIC_API_KEY to enable")
    st.caption("All patients are synthetic. Not for clinical use.")

nav = st.navigation([
    st.Page("views/workspace.py", title="Patient workspace", icon=":material/description:", default=True),
    st.Page("views/search.py", title="Search", icon=":material/search:"),
])
nav.run()
