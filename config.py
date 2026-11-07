"""Shared settings for TrialScope.

Settings are read, in order, from Streamlit secrets (Streamlit Community Cloud, or a local
.streamlit/secrets.toml), environment variables, and a local .env file.
"""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _setting(name: str, default: str = "") -> str:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets file, or not running under Streamlit
        pass
    return os.environ.get(name, default)


TURBOPUFFER_API_KEY = _setting("TURBOPUFFER_API_KEY")
TURBOPUFFER_REGION = _setting("TURBOPUFFER_REGION", "aws-us-east-1")

# Optional: the copilot turns on when this is set.
ANTHROPIC_API_KEY = _setting("ANTHROPIC_API_KEY")
COPILOT_MODEL = _setting("COPILOT_MODEL", "claude-sonnet-5-5")

# Optional: set READ_ONLY = "true" on a public deployment so visitors can't edit notes.
READ_ONLY = _setting("READ_ONLY", "false").lower() in ("1", "true", "yes")

# turbopuffer native embedding: text is embedded on write and at query time.
EMBED_MODEL = "voyage/voyage-4-lite"
DISTANCE_METRIC = "cosine_distance"

# Namespace names
NS_PREFIX = "ts-"
NS_TRIALS = NS_PREFIX + "trials"
NS_PUBMED = NS_PREFIX + "pubmed"
NS_PMC = NS_PREFIX + "pmc"  # full-text article chunks (PMC Open Access)
NS_PATIENTS = NS_PREFIX + "patients"  # patient directory (one row per patient)


def patient_ns(patient_id: str) -> str:
    """Each patient's notes live in their own namespace."""
    return f"{NS_PREFIX}patient-{patient_id}"


TOP_K = 10

# Optional: when set, visitors must enter this password before using the app.
APP_PASSWORD = _setting("APP_PASSWORD")
