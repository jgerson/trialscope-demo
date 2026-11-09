# TrialScope walkthrough

A short notebook that shows what TrialScope does with turbopuffer, on 8 real ClinicalTrials.gov studies typed
into the notebook itself: load documents with native embedding, search by keyword, by meaning and both at once,
filter to trials a patient could join, and keep each patient's notes in their own namespace. It takes about ten
minutes and nothing is downloaded. Run it before showing the app.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jgerson/trialscope-demo/blob/main/walkthrough/trialscope_walkthrough.ipynb)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/jgerson/trialscope-demo)

## Run it

**Google Colab.** Use the Colab badge. Click the key icon (Secrets) in the left sidebar, add
`TURBOPUFFER_API_KEY`, and switch on **Notebook access**. Run the cells top to bottom. The saved outputs show what
to expect before you run anything. To keep your own edits, use **File → Save a copy in Drive**.

**GitHub Codespaces.** Add a Codespaces secret named `TURBOPUFFER_API_KEY` (GitHub → Settings → Codespaces →
Secrets, with this repository selected), then use the badge. Pick the Python 3.12 kernel and run the cells.

Anywhere else: `pip install -r walkthrough/requirements.txt`, set `TURBOPUFFER_API_KEY`, and open the notebook.

## What it touches

Only its own two namespaces, named fresh for each run (`quickstart-<random>-trials` and
`quickstart-<random>-patient-dana`), so several people can run it at once on the same key. It loads its own sample
data and never reads any other namespace. The last cell deletes the pair. A run costs a fraction of a cent.

## The data

The 8 trials are real ClinicalTrials.gov records (five breast cancer, three heart), shortened to their title and
first sentence or two. Dana and her four notes are made up. Trial records are public data and may be out of date.

## The detailed version

`trialscope_walkthrough_detailed.ipynb` is the longer original: 20 trials, 20 PubMed abstracts and 20 synthetic
patients loaded from `data/` (rebuilt by `build_data.py`), with every app query rebuilt step by step in `wt-`
namespaces. [Open it in Colab](https://colab.research.google.com/github/jgerson/trialscope-demo/blob/main/walkthrough/trialscope_walkthrough_detailed.ipynb).
