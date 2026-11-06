"""Generate synthetic oncology and cardiology patients with visit notes and load them.

    python ingest/patients.py --count 100

Every patient is fictional. Notes are built from clinical templates with seeded variation,
so reruns produce the same patients. The first four patients are fixed so demos are repeatable.
Each patient gets their own namespace (ts-patient-0001, ...) plus a row in the ts-patients directory.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from common import load_batches  # noqa: F401  (sets up sys.path)

import config
import tp_client

FIRST_F = ["Dana", "Lena", "Maria", "Grace", "Aisha", "Hannah", "Priya", "Rosa", "Elena", "Naomi", "Claire", "Yuki",
           "Fatima", "Joan", "Ingrid", "Tamara", "Beatriz", "Leah", "Mei", "Sofia", "Ruth", "Carmen", "Alice", "Nadia"]
FIRST_M = ["Marcus", "Raj", "David", "Samuel", "Luis", "Kenji", "Omar", "Thomas", "Andre", "Victor", "Paul", "Wei",
           "Jamal", "Peter", "Ethan", "Hector", "Ivan", "George", "Noah", "Felix", "Arjun", "Daniel", "Frank", "Malik"]
LAST = ["Whitfield", "Okafor", "Sorensen", "Patel", "Alvarez", "Kim", "Nakamura", "Brennan", "Haddad", "Novak",
        "Fischer", "Osei", "Romano", "Lindqvist", "Mendez", "Cohen", "Adeyemi", "Kowalski", "Duarte", "Byrne",
        "Takahashi", "Moreau", "Singh", "Larsen", "Ortiz", "Walsh", "Mbeki", "Petrov", "Reyes", "Gallagher"]
PLACES = [("Westchester", "NY"), ("White Plains", "NY"), ("Yonkers", "NY"), ("Stamford", "CT"),
          ("Hackensack", "NJ"), ("Bronx", "NY"), ("Brooklyn", "NY"), ("Manhattan", "NY"), ("Newark", "NJ"),
          ("Boston", "MA"), ("Philadelphia", "PA"), ("Baltimore", "MD"), ("Cleveland", "OH"), ("Chicago", "IL"),
          ("Houston", "TX"), ("Denver", "CO"), ("Seattle", "WA"), ("Atlanta", "GA")]

ONC = "Dr. Rivera (Oncology)"
CARD = "Dr. Chen (Cardiology)"


# ---------------------------------------------------------------- condition profiles
# Each profile returns (patient fields, list of (days_after_start, note_type, title, author, body)).

def breast_her2(p, r):
    stage = p.get("stage") or r.choice(["II", "IIA", "IIB", "IIIA"])
    ef = r.choice([60, 62, 64, 65])
    p.update(specialty="Oncology", primary_dx="HER2-positive breast cancer", stage=stage,
             biomarkers="ER+/PR-/HER2 3+" if r.random() < 0.5 else "ER-/PR-/HER2 3+")
    side = r.choice(["left", "right"])
    return p, [
        (0, "Visit note", "Initial consult",
         ONC, f"""## Subjective
{p['age']}-year-old {p['sex_word']} referred after screening mammogram showed a {r.choice([1.8, 2.4, 3.1])} cm {side} breast mass. Core biopsy confirmed invasive ductal carcinoma. No prior cancer history. Family history: mother with breast cancer in her 60s.

## Assessment
Invasive ductal carcinoma, {side} breast, clinical stage {stage}. Receptors {p['biomarkers']}.

## Plan
- Staging CT chest/abdomen/pelvis and bone scan.
- Baseline echocardiogram before HER2-directed therapy.
- Discuss neoadjuvant chemotherapy with trastuzumab and pertuzumab.
- Refer to genetics for BRCA testing."""),
        (6, "Result", "Pathology summary", ONC,
         f"""Core needle biopsy, {side} breast: invasive ductal carcinoma, grade 3. Receptors: {p['biomarkers']} by IHC. Ki-67 {r.choice([35, 40, 55])}%. Lymphovascular invasion not identified on biopsy."""),
        (12, "Result", "Baseline echocardiogram", CARD,
         f"""Transthoracic echo before trastuzumab. LVEF {ef}%. Normal wall motion. No valvular disease. Global longitudinal strain -20%. Cleared to start HER2-directed therapy with echo every 3 months."""),
        (21, "Visit note", "Cycle 1 neoadjuvant therapy", ONC,
         """## Subjective
Starts cycle 1 of docetaxel, carboplatin, trastuzumab and pertuzumab (TCHP). Anxious but well informed.

## Plan
- Premedication per protocol.
- Growth factor support.
- Labs before each cycle."""),
        (63, "Visit note", "Cycle 3 check-in", ONC,
         f"""## Subjective
Mild fatigue and diarrhea grade 1, managed with loperamide. No neuropathy.

## Objective
Breast mass smaller on exam, now about {r.choice([1.0, 1.2, 1.5])} cm.

## Plan
Continue TCHP. Echo before cycle 4."""),
        (80, "Result", "Echo before cycle 4", CARD,
         f"""LVEF {ef - r.choice([2, 4, 6])}%, a small drop from baseline {ef}%. No symptoms of heart failure. Continue trastuzumab with routine cardiac monitoring every 3 months."""),
        (84, "Visit note", "Follow-up after cycle 4", ONC,
         """## Subjective
Completed cycle 4 of neoadjuvant therapy. Mild fatigue, no neuropathy. Appetite good. Asked whether any clinical trials could fit her after surgery.

## Assessment
Responding on exam. Ejection fraction stable on last echo.

## Plan
- Surgical consult after cycle 6.
- Review recruiting adjuvant trials near home.
- Repeat echo before surgery."""),
        (90, "Phone call", "Phone call about trial options", ONC,
         """Patient called to ask about clinical trials for adjuvant HER2 therapy and about cardiac protection while on trastuzumab. Told her we will review options at the next visit."""),
    ]


def breast_hr(p, r):
    stage = r.choice(["I", "IIA", "IIB"])
    p.update(specialty="Oncology", primary_dx="HR-positive, HER2-negative breast cancer", stage=stage,
             biomarkers="ER+/PR+/HER2-")
    return p, [
        (0, "Visit note", "Initial consult", ONC,
         f"""{p['age']}-year-old {p['sex_word']} with newly diagnosed ER+/PR+/HER2- invasive lobular carcinoma, clinical stage {stage}. Oncotype DX recurrence score {r.choice([14, 19, 23, 31])} pending review.

## Plan
- Lumpectomy with sentinel node biopsy.
- Adjuvant endocrine therapy after surgery.
- Bone density scan before aromatase inhibitor."""),
        (30, "Result", "Surgical pathology", ONC,
         f"""Lumpectomy: {r.choice([1.4, 2.2])} cm invasive lobular carcinoma, margins negative, 0/{r.choice([2, 3])} sentinel nodes positive."""),
        (60, "Visit note", "Adjuvant therapy start", ONC,
         """Starting letrozole. Discussed joint pain and hot flashes. Considering CDK4/6 inhibitor given risk features; will discuss trials of ribociclib or abemaciclib in the adjuvant setting."""),
        (150, "Visit note", "3-month follow-up", ONC,
         """Arthralgias grade 1, manageable. No signs of recurrence on exam. Continue letrozole. Calcium and vitamin D."""),
        (240, "Visit note", "6-month follow-up", ONC,
         """Doing well. Mammogram clear. Interested in exercise programs and survivorship trials."""),
    ]


def nsclc(p, r):
    mut = r.choice(["EGFR exon 19 deletion", "EGFR L858R", "ALK rearrangement", "KRAS G12C", "PD-L1 TPS 70%"])
    stage = r.choice(["IIIB", "IVA", "IVB"])
    p.update(specialty="Oncology", primary_dx="Non-small cell lung cancer", stage=stage, biomarkers=mut)
    drug = {"EGFR exon 19 deletion": "osimertinib", "EGFR L858R": "osimertinib", "ALK rearrangement": "alectinib",
            "KRAS G12C": "sotorasib", "PD-L1 TPS 70%": "pembrolizumab"}[mut]
    return p, [
        (0, "Visit note", "Initial consult", ONC,
         f"""{p['age']}-year-old {p['sex_word']}, former smoker ({r.choice([20, 30, 45])} pack-years), presenting with cough and weight loss. CT shows right upper lobe mass with mediastinal nodes. Biopsy: adenocarcinoma of the lung, stage {stage}.

## Plan
- Next-generation sequencing on tissue and blood.
- Brain MRI.
- Pulmonary function tests."""),
        (14, "Result", "Molecular testing", ONC, f"""NGS result: {mut}. PD-L1 TPS {r.choice([1, 20, 50, 70])}%. TMB {r.choice([4, 9, 14])} mut/Mb."""),
        (18, "Visit note", "Treatment plan", ONC,
         f"""Discussed first-line {drug} based on {mut}. Reviewed side effects. ECOG performance status {r.choice([0, 1])}."""),
        (90, "Result", "Restaging CT", ONC, """Partial response, primary mass decreased 40%. No new lesions. Brain MRI clear."""),
        (200, "Visit note", "Progression visit", ONC,
         f"""CT shows new liver lesions, progression on {drug}. Biopsy for resistance mechanism. Patient wants to know about clinical trials after progression on {drug}."""),
    ]


def colorectal(p, r):
    stage = r.choice(["III", "IVA", "IVB"])
    msi = r.choice(["MSS", "MSI-high"])
    ras = r.choice(["KRAS wild-type", "KRAS G12D", "BRAF V600E"])
    p.update(specialty="Oncology", primary_dx="Colorectal adenocarcinoma", stage=stage, biomarkers=f"{msi}, {ras}")
    return p, [
        (0, "Visit note", "Initial consult", ONC,
         f"""{p['age']}-year-old {p['sex_word']} with sigmoid colon adenocarcinoma found on colonoscopy for rectal bleeding. Stage {stage}. Tumor is {msi}, {ras}. CEA {r.choice([4.1, 12.8, 56.0])} ng/mL."""),
        (21, "Visit note", "Chemotherapy start", ONC,
         """Starting FOLFOX. Port placed. Discussed neuropathy, nausea and cold sensitivity."""),
        (110, "Visit note", "Mid-treatment review", ONC,
         """Grade 2 peripheral neuropathy. Dropping oxaliplatin, continuing 5-FU. CEA trending down."""),
        (220, "Result", "Surveillance CT", ONC, """No evidence of disease in chest, abdomen or pelvis. Continue surveillance with CEA every 3 months."""),
    ]


def melanoma(p, r):
    stage = r.choice(["IIIB", "IIIC", "IV"])
    p.update(specialty="Oncology", primary_dx="Melanoma", stage=stage, biomarkers=r.choice(["BRAF V600E", "BRAF wild-type"]))
    return p, [
        (0, "Visit note", "Initial consult", ONC,
         f"""{p['age']}-year-old {p['sex_word']} with melanoma of the upper back, Breslow depth {r.choice([2.1, 3.4, 4.8])} mm, ulcerated. Sentinel node positive. Stage {stage}. {p['biomarkers']}."""),
        (30, "Visit note", "Adjuvant immunotherapy", ONC, """Starting adjuvant nivolumab. Baseline TSH, cortisol and liver tests normal."""),
        (120, "Visit note", "Immune side effects", ONC, """Grade 2 colitis. Holding nivolumab, starting prednisone taper. Will discuss rechallenge."""),
        (200, "Result", "PET-CT", ONC, """No evidence of recurrence. Thyroid function now low; started levothyroxine."""),
    ]


def hfref(p, r):
    ef = r.choice([25, 30, 35])
    cause = r.choice(["ischemic", "non-ischemic dilated", "anthracycline-related"])
    p.update(specialty="Cardiology", primary_dx="Heart failure with reduced ejection fraction", stage=f"NYHA {r.choice(['II', 'III'])}",
             biomarkers=f"LVEF {ef}%")
    return p, [
        (0, "Visit note", "New heart failure consult", CARD,
         f"""{p['age']}-year-old {p['sex_word']} admitted with dyspnea and leg swelling. Echo LVEF {ef}%, {cause} cardiomyopathy. NT-proBNP {r.choice([2400, 4100, 6800])} pg/mL.

## Plan
- Start guideline-directed therapy: sacubitril/valsartan, metoprolol succinate, spironolactone, dapagliflozin.
- Daily weights, 2 g sodium diet.
- Repeat echo in 3 months."""),
        (30, "Visit note", "Titration visit", CARD, """Tolerating therapy. BP 108/70. Potassium 4.8. Uptitrating metoprolol. Symptoms improving."""),
        (100, "Result", "Repeat echocardiogram", CARD, f"""LVEF {ef + r.choice([0, 5, 10])}%. Moderate functional mitral regurgitation."""),
        (110, "Visit note", "Device discussion", CARD,
         """Discussed ICD for primary prevention if LVEF stays at or below 35%. Patient asked about remote monitoring and trials of new heart failure drugs."""),
    ]


def afib(p, r):
    p.update(specialty="Cardiology", primary_dx="Atrial fibrillation", stage=r.choice(["Paroxysmal", "Persistent"]),
             biomarkers=f"CHA2DS2-VASc {r.choice([2, 3, 4, 5])}")
    return p, [
        (0, "Visit note", "Palpitations consult", CARD,
         f"""{p['age']}-year-old {p['sex_word']} with intermittent palpitations. ECG shows atrial fibrillation with rapid ventricular response. {p['biomarkers']}. Started apixaban and diltiazem."""),
        (45, "Result", "Holter monitor", CARD, f"""AF burden {r.choice([12, 28, 45])}%. Average heart rate 88."""),
        (60, "Visit note", "Rhythm control discussion", CARD,
         """Symptoms persist despite rate control. Referred for catheter ablation, pulsed field ablation option discussed."""),
        (150, "Visit note", "Post-ablation follow-up", CARD, """In sinus rhythm since ablation. Continue anticoagulation for at least 3 months."""),
    ]


def cad(p, r):
    p.update(specialty="Cardiology", primary_dx="Coronary artery disease after myocardial infarction", stage="Post-MI",
             biomarkers=f"LDL {r.choice([68, 92, 130])} mg/dL")
    return p, [
        (0, "Visit note", "Post-MI follow-up", CARD,
         f"""{p['age']}-year-old {p['sex_word']} seen 4 weeks after anterior STEMI treated with drug-eluting stent to the LAD. On aspirin, ticagrelor, atorvastatin 80 mg, metoprolol. {p['biomarkers']}."""),
        (60, "Visit note", "Lipid management", CARD, """LDL above goal on high-intensity statin. Adding ezetimibe; discussed PCSK9 inhibitor and inclisiran trials."""),
        (120, "Visit note", "Cardiac rehab check-in", CARD, """Completed 18 sessions of cardiac rehab. No angina. Walking 30 minutes daily."""),
    ]


PROFILES = [breast_her2, breast_hr, nsclc, colorectal, melanoma, hfref, afib, cad]

FIXED = [
    dict(name="Dana Whitfield", age=58, sex="Female", city="Westchester", state="NY", profile=breast_her2, stage="II"),
    dict(name="Marcus Okafor", age=71, sex="Male", city="Bronx", state="NY", profile=nsclc),
    dict(name="Lena Sorensen", age=44, sex="Female", city="Stamford", state="CT", profile=melanoma),
    dict(name="Raj Patel", age=63, sex="Male", city="Hackensack", state="NJ", profile=colorectal),
]


def build(count: int, seed: int = 7):
    r = random.Random(seed)
    used = set()
    patients, notes_by_patient = [], {}
    for i in range(count):
        pid = f"{i + 1:04d}"
        if i < len(FIXED):
            spec = dict(FIXED[i])
            profile = spec.pop("profile")
        else:
            profile = r.choice(PROFILES)
            sex = "Female" if profile in (breast_her2, breast_hr) or r.random() < 0.45 else "Male"
            while True:
                name = f"{r.choice(FIRST_F if sex == 'Female' else FIRST_M)} {r.choice(LAST)}"
                if name not in used:
                    break
            city, state = r.choice(PLACES)
            spec = dict(name=name, age=r.randint(34, 84), sex=sex, city=city, state=state)
        used.add(spec["name"])
        spec["sex_word"] = "woman" if spec["sex"] == "Female" else "man"
        p, notes = profile(spec, r)
        start = date(2026, 1, 1) + timedelta(days=r.randint(0, 220))
        if i == 0:
            start = date(2026, 8, 12)  # Dana's cycle-4 visit lands on Nov 4
        rows = []
        for n, (offset, ntype, title, author, body) in enumerate(notes, 1):
            d = start + timedelta(days=offset)
            if d > date(2026, 11, 5):
                continue
            rows.append({
                "id": f"{pid}-n{n:02d}",
                "title": title,
                "body": body,
                "text": f"{title}\n{body}",
                "note_type": ntype,
                "visit_date": d.isoformat(),
                "author": author,
            })
        patients.append({
            "id": pid, "name": p["name"], "age": p["age"], "sex": p["sex"], "city": p["city"], "state": p["state"],
            "specialty": p["specialty"], "primary_dx": p["primary_dx"], "stage": p["stage"],
            "biomarkers": p.get("biomarkers", ""), "note_count": len(rows), "synthetic": True,
        })
        notes_by_patient[pid] = rows
    return patients, notes_by_patient


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    args = ap.parse_args()
    patients, notes = build(args.count)
    tp_client.upsert(config.NS_PATIENTS, patients, kind="directory")
    print(f"directory: {len(patients)} patients")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda pid: tp_client.upsert(config.patient_ns(pid), notes[pid], kind="notes"), notes))
    print(f"notes: {sum(len(v) for v in notes.values())} notes across {len(notes)} patient namespaces")
