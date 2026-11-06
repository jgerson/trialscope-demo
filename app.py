"""TrialScope: patient notes, PubMed and clinical trials in one search, on turbopuffer.

    streamlit run app.py
"""
import hmac

import streamlit as st

import config
import ui

st.set_page_config(page_title="TrialScope", page_icon="assets/icon.svg", layout="wide")
ui.inject_css()


def login_page() -> None:
    st.markdown(ui.LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="ts-login">{ui.ICON_SVG}<h1>TrialScope</h1>'
        "<p>Search patient notes, PubMed and ClinicalTrials.gov in one place.</p></div>",
        unsafe_allow_html=True)
    with st.form("login", border=True):
        pw = st.text_input("Password", type="password", placeholder="Enter the demo password")
        ok = st.form_submit_button("Sign in", type="primary", width="stretch")
    if ok:
        if hmac.compare_digest(pw.encode(), config.APP_PASSWORD.encode()):
            st.session_state.authed = True
            st.rerun()
        st.error("That password didn't match. Try again.")
    st.caption("A personal learning project. Every patient is synthetic; not for clinical use.")


# Until the visitor signs in, the only page is the sign-in page and the sidebar stays hidden.
if config.APP_PASSWORD and not st.session_state.get("authed"):
    st.navigation([st.Page(login_page, title="Sign in")], position="hidden").run()
    st.stop()

if not config.TURBOPUFFER_API_KEY:
    st.error("Add TURBOPUFFER_API_KEY to the app's Secrets (or .env locally) to start.")
    st.stop()

st.logo("assets/logo.svg", icon_image="assets/icon.svg", size="large")

# ---------------------------------------------------------------- sidebar: patient picker
with st.sidebar:
    pts = ui.patients()
    if not pts:
        st.warning("No patients yet. Run `python ingest/patients.py`.")
    else:
        if "patient_id" not in st.session_state:
            st.session_state.patient_id = min(p["id"] for p in pts)
        specialty = st.segmented_control("Patients", ["All", "Oncology", "Cardiology"], default="All", key="panel") or "All"
        shown = sorted([p for p in pts if specialty == "All" or p["specialty"] == specialty], key=lambda p: p["id"])
        ids = [p["id"] for p in shown]
        if st.session_state.patient_id not in ids and ids:
            st.session_state.patient_id = ids[0]
        st.selectbox(
            "Patient",
            ids,
            key="patient_id",
            label_visibility="collapsed",
            format_func=lambda pid: next(f"{p['name']}, {p['age']}" for p in shown if p["id"] == pid),
        )
        p = ui.current_patient()
        if p:
            ui.sidebar_patient_card(p)
    st.markdown("")
    copilot = f"Copilot on, {config.COPILOT_MODEL}" if config.ANTHROPIC_API_KEY else "Copilot off until ANTHROPIC_API_KEY is set"
    st.markdown(
        f'<div class="ts-foot">turbopuffer {config.TURBOPUFFER_REGION}<br>{copilot}<br>'
        "Synthetic patients. Not for clinical use.</div>", unsafe_allow_html=True)

nav = st.navigation([
    st.Page("views/workspace.py", title="Patient workspace", icon=":material/description:", default=True),
    st.Page("views/search.py", title="Search", icon=":material/search:"),
])
nav.run()
