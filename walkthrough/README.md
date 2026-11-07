# TrialScope walkthrough

A notebook that rebuilds TrialScope's data layer on turbopuffer one step at a time, from loading records with
upserts to hybrid search with filters across several namespaces. Run it before showing the app, so the app's
screens map to steps the audience has already seen.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/jgerson/trialscope-demo)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jgerson/trialscope-demo/blob/main/walkthrough/trialscope_walkthrough.ipynb)

## Run it

**GitHub Codespaces.** First add a Codespaces secret named `TURBOPUFFER_API_KEY` (GitHub → Settings →
Codespaces → Secrets, with this repository selected). Then use the badge above, or **Code → Codespaces →
Create codespace on main**. The codespace installs the dependencies and opens the notebook; pick the
Python 3.12 kernel and run the cells in order.

**Google Colab.** Use the Colab badge, add `TURBOPUFFER_API_KEY` under the key icon (Secrets), and run the
cells. The data files load from this repository.

Anywhere else: `pip install -r walkthrough/requirements.txt`, set `TURBOPUFFER_API_KEY`, and open the notebook
from the `walkthrough` folder.

## What it touches

Only namespaces starting with `wt-`: `wt-trials`, `wt-pubmed`, `wt-patients` and one `wt-patient-<id>` per
patient (23 in all). The app uses `ts-`, and the notebook refuses any other prefix. The last cell deletes the
`wt-` namespaces (set `CLEAN_UP = True`). Loading costs a few cents of turbopuffer usage, mostly embedding.

## The data (`data/`)

| File | Records | Source |
| --- | --- | --- |
| `patients.json` | 20 | The app's first 20 synthetic patients (`ingest/patients.py`, same seed) |
| `notes.json` | 83 | Those patients' notes |
| `trials.json` | 20 | ClinicalTrials.gov, matched to the patients' conditions, through `ingest/trials.py`'s `to_row` |
| `pubmed.json` | 20 | PubMed abstracts on the same conditions, through `ingest/pubmed.py`'s `to_row` |

All patients are synthetic. Trial and abstract records are public data and may be out of date.
`python walkthrough/build_data.py` rebuilds the files from the live sources.
