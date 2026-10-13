"""Synthetic clinical document text for the healthcare seed. Every name, finding and value is fictional."""

CONSERVATIVE = {
    "spine": "physical therapy ({w} weeks, core stabilization and McKenzie protocol), scheduled naproxen 500 mg BID, "
             "activity modification{inj}",
    "knee": "physical therapy ({w} weeks, quadriceps strengthening), meloxicam 15 mg daily, unloader brace{inj}",
}

HPI = {
    "72148": "{age}-year-old presents with low back pain radiating to the {side} leg below the knee for {dur} weeks. "
             "Numbness along the {derm} dermatome. No bowel or bladder dysfunction, no fever or weight loss.",
    "73721": "{age}-year-old with {side} knee pain after a twisting injury {dur} weeks ago. Reports locking and catching, "
             "effusion after activity. Plain films obtained.",
    "74177": "{age}-year-old with {dur} weeks of intermittent abdominal pain, worse in the right lower quadrant, with "
             "low-grade fevers and change in bowel habits. WBC mildly elevated.",
    "78815": "{age}-year-old with biopsy-proven malignancy referred for staging PET/CT prior to treatment planning. "
             "ECOG performance status {ecog}.",
    "27447": "{age}-year-old with progressive {side} knee pain for {dur} months, night pain, difficulty with stairs and "
             "walking more than one block. KOOS JR {koos}.",
    "22630": "{age}-year-old with neurogenic claudication, walking tolerance under {walk} minutes, and mechanical back pain "
             "for {dur} months.",
    "95810": "{age}-year-old referred for loud snoring, witnessed apneas and daytime somnolence. BMI {bmi}. "
             "Neck circumference {neck} cm.",
    "J0135": "{age}-year-old with established {condition}, persistent active disease despite conventional therapy. "
             "{activity}.",
    "97110": "{age}-year-old referred for skilled therapy: {condition}. Functional limitation with ADLs and gait.",
    "E0601": "{age}-year-old with obstructive sleep apnea confirmed on recent sleep study, symptomatic with daytime "
             "sleepiness. Evaluated face to face to start PAP therapy.",
}

PLAN = {
    "72148": "MRI lumbar spine without contrast to evaluate for disc herniation and nerve root compression; "
             "consider epidural steroid injection based on findings.",
    "73721": "MRI right knee without contrast to evaluate for meniscal tear; arthroscopy if confirmed.",
    "74177": "CT abdomen and pelvis with contrast to evaluate for diverticulitis versus appendiceal or mass lesion.",
    "78815": "PET/CT skull base to mid-thigh for initial staging; tumor board review to follow.",
    "27447": "Total knee arthroplasty discussed, risks and benefits reviewed, patient wishes to proceed.",
    "22630": "Single-level lumbar interbody fusion recommended; surgical consent discussed.",
    "95810": "Attended in-lab polysomnography; home testing inappropriate given comorbid cardiopulmonary disease.",
    "J0135": "Start adalimumab 40 mg subcutaneously every 14 days. Labs every 3 months.",
    "97110": "Physical therapy 2x per week for 6 weeks, therapeutic exercise and gait training.",
    "E0601": "Order CPAP auto-titrating 5-15 cm H2O with heated humidifier; compliance download at 31-90 days.",
}

CONVENTIONAL = {
    "M05": ("methotrexate up to 20 mg weekly with folic acid", "DAS28-CRP {score}"),
    "M06": ("methotrexate up to 20 mg weekly, then hydroxychloroquine", "CDAI {score}"),
    "K50": ("azathioprine 2.5 mg/kg and a budesonide taper", "Harvey-Bradshaw Index {score}"),
    "L40": ("methotrexate 15 mg weekly", "BSA {score}%, tender joints on exam"),
}


def _sig(rng, author: str) -> str:
    return f"\n\nElectronically signed by {author} on the date of service."


def clinical_note(rng, *, cpt: str, dx: list[tuple[str, str]], age: int, author: str, specialty: str,
                  therapy_weeks: int | None = None, conventional_months: int | None = None, epworth: int | None = None,
                  extra: str | None = None) -> tuple[str, str, dict]:
    side = rng.choice(["right", "left"])
    facts: dict = {}
    hpi = HPI[cpt].format(
        age=age, side=side, dur=rng.randint(6, 30), derm=rng.choice(["L4", "L5", "S1"]), ecog=rng.choice([0, 1, 1, 2]),
        koos=rng.randint(38, 58), walk=rng.choice([5, 10, 10, 15]), bmi=round(rng.uniform(29, 41), 1), neck=rng.randint(40, 47),
        condition=dx[0][1].lower(), activity="",
    )
    parts = [f"{specialty} progress note", "", f"HPI: {hpi}"]
    if therapy_weeks:
        kind = "knee" if cpt in ("27447", "73721") else "spine"
        inj = ", one corticosteroid injection without durable relief" if therapy_weeks >= 12 else ""
        parts.append("Conservative care to date: " + CONSERVATIVE[kind].format(w=therapy_weeks, inj=inj)
                     + f". Total duration {therapy_weeks} weeks with persistent symptoms.")
        facts["conservative_therapy_weeks"] = therapy_weeks
    if conventional_months:
        drug, measure = CONVENTIONAL.get(dx[0][0][:3], CONVENTIONAL["M05"])
        score = {"M05": round(rng.uniform(4.6, 6.1), 1), "M06": rng.randint(23, 38), "K50": rng.randint(9, 14),
                 "L40": rng.randint(8, 18)}.get(dx[0][0][:3], 5.2)
        parts.append(f"Prior therapy: {drug} for {conventional_months} months with inadequate response. "
                     f"Disease activity today: {measure.format(score=score)}.")
        facts.update(conventional_therapy_months=conventional_months, prior_therapy=drug)
    if epworth is not None:
        parts.append(f"Epworth Sleepiness Scale {epworth}/24. STOP-BANG {rng.randint(5, 8)}/8.")
        facts["epworth_score"] = epworth
    if extra:
        parts.append(extra)
    exam = {"72148": f"Positive straight-leg raise on the {side} at {rng.randint(30, 60)} degrees; EHL strength 4/5.",
            "73721": "Medial joint line tenderness, positive McMurray, small effusion.",
            "27447": f"Varus deformity, crepitus, ROM 5-{rng.randint(95, 110)} degrees, antalgic gait.",
            "22630": "Reduced lumbar extension, diminished ankle reflexes bilaterally, gait wide-based.",
            }.get(cpt, "Exam documented; see flowsheet.")
    parts += [f"Exam: {exam}",
              "Assessment: " + "; ".join(f"{d[1]} ({d[0]})" for d in dx) + ".",
              f"Plan: {PLAN[cpt]}"]
    title = f"{specialty} {'consult' if cpt in ('95810', 'J0135') else 'progress'} note"
    return title, "\n".join(parts) + _sig(rng, author), facts


def pt_note(rng, *, dx: list[tuple[str, str]], weeks: int, plan_of_care: bool, author: str) -> tuple[str, str, dict]:
    visits = max(2, round(weeks * rng.uniform(1.4, 2.0)))
    if plan_of_care:
        title = "Physical therapy evaluation and plan of care"
        body = (f"Diagnosis: {dx[0][1]} ({dx[0][0]}). Evaluation completed. Goals: independent home exercise program, "
                f"Oswestry improvement of 10 points, gait without device within 6 weeks. Frequency 2x/week x 6 weeks. "
                f"Plan of care certified by referring physician.")
        facts = {"plan_of_care": True}
        if weeks:
            facts["conservative_therapy_weeks"] = weeks
    else:
        title = f"Physical therapy progress summary ({weeks} weeks)"
        body = (f"Diagnosis: {dx[0][1]} ({dx[0][0]}). Patient attended {visits} visits over {weeks} weeks: therapeutic "
                f"exercise, manual therapy, home program. Pain {rng.randint(5, 8)}/10 at start, {rng.randint(4, 7)}/10 now. "
                f"Plateaued; limited functional gains despite adherence. Recommend physician follow-up.")
        facts = {"conservative_therapy_weeks": weeks, "visits": visits}
    return title, body + _sig(rng, author), facts


def imaging_report(rng, *, cpt: str, dx: list[tuple[str, str]], author: str, kl_grade: int | None = None) -> tuple[str, str, dict]:
    facts: dict = {}
    if cpt in ("27447", "73721") or kl_grade:
        grade = kl_grade or rng.choice([1, 2, 2, 3])
        title = "XR knee, 3 views, weight-bearing"
        findings = {1: "Minimal joint space narrowing, no osteophytes.", 2: "Mild joint space narrowing, small osteophytes.",
                    3: "Moderate medial joint space narrowing, multiple osteophytes, subchondral sclerosis.",
                    4: "Bone-on-bone medial compartment, large osteophytes, subchondral cysts, varus alignment."}[grade]
        body = f"FINDINGS: {findings}\nIMPRESSION: Osteoarthritis, Kellgren-Lawrence grade {grade}."
        facts["kl_grade"] = grade
    elif cpt == "22630":
        title = "MRI lumbar spine without contrast"
        body = (f"FINDINGS: Grade {rng.choice([1, 1, 2])} anterolisthesis of L4 on L5 with severe central canal stenosis and "
                "bilateral foraminal narrowing. Facet effusions.\nIMPRESSION: Degenerative spondylolisthesis L4-5 with severe stenosis.")
        facts["finding"] = "spondylolisthesis_with_stenosis"
    else:
        title = "XR lumbar spine, 2-3 views"
        body = ("FINDINGS: Mild disc space narrowing at L4-5 and L5-S1. No fracture or listhesis. Alignment normal.\n"
                "IMPRESSION: Mild degenerative changes. No acute abnormality.")
    return title, body + f"\n\nDictated by {author}, Radiology.", facts


def pathology_report(rng, *, dx: list[tuple[str, str]], author: str) -> tuple[str, str, dict]:
    code, desc = dx[0]
    specimen = {"C34": "CT-guided core biopsy, right upper lobe lung", "C18": "Colonoscopic biopsy, sigmoid colon",
                "C83": "Excisional biopsy, left cervical lymph node", "C50": "Ultrasound-guided core biopsy, right breast"}.get(code[:3], "Core biopsy")
    dxtext = {"C34": "Adenocarcinoma, acinar predominant", "C18": "Invasive adenocarcinoma, moderately differentiated",
              "C83": "Diffuse large B-cell lymphoma, germinal center type", "C50": "Invasive ductal carcinoma, grade 2, ER+/PR+/HER2-"}.get(code[:3], desc)
    body = f"SPECIMEN: {specimen}.\nFINAL DIAGNOSIS: {dxtext}.\nComment: Findings discussed with the treating oncologist."
    return "Surgical pathology report", body + f"\n\nSigned out by {author}, Pathology.", {"malignancy_confirmed": True}


def sleep_study(rng, *, ahi: float, author: str) -> tuple[str, str, dict]:
    sev = "severe" if ahi >= 30 else "moderate" if ahi >= 15 else "mild"
    body = (f"Home sleep apnea test, 1 night. Monitoring time 7.1 h. AHI {ahi} events/h (3% rule), ODI {round(ahi * 0.9, 1)}, "
            f"nadir SpO2 {84 if ahi >= 15 else 88}%.\nIMPRESSION: Obstructive sleep apnea, {sev}. Recommend PAP therapy.")
    return "Sleep study report (HSAT)", body + f"\n\nInterpreted by {author}, Sleep Medicine.", {"ahi": ahi, "severity": sev}


LABS = {
    "tb": ("Interferon-gamma release assay (TB)", "Result: NEGATIVE. TB1 antigen minus nil 0.02 IU/mL; mitogen response adequate.", {"tb_result": "negative"}),
    "hepb": ("Hepatitis B panel", "HBsAg non-reactive; anti-HBc total non-reactive; anti-HBs 48 mIU/mL (immune).", {"hbsag": "negative"}),
    "cmp": ("Comprehensive metabolic panel", "Sodium 139, potassium 4.2, creatinine 0.9, ALT 22, AST 19, glucose 104 mg/dL.", {}),
    "a1c": ("Hemoglobin A1c", "HbA1c 6.9 %.", {"a1c": 6.9}),
    "cbc": ("Complete blood count", "WBC 11.8 (H), Hgb 13.6, platelets 288.", {}),
    "hiv": ("HIV-1 RNA viral load and CD4 count", "HIV-1 RNA <20 copies/mL (undetectable). CD4 612 cells/uL.", {"viral_load": "undetectable"}),
}


def lab(kind: str) -> tuple[str, str, dict]:
    title, body, facts = LABS[kind]
    return title, body + "\n\nCalderwick Health Core Laboratory. Verified by laboratory medical director.", dict(facts)


def medication_list(meds: list[str]) -> tuple[str, str, dict]:
    return ("Active medication list", "Reconciled at visit:\n" + "\n".join(f"- {m}" for m in meds), {"count": len(meds)})


def behavioral_health_note(rng, *, dx: tuple[str, str], author: str) -> tuple[str, str, dict]:
    body = (f"Psychiatry follow-up. Diagnosis: {dx[1]} ({dx[0]}). PHQ-9 {rng.randint(8, 16)}, GAD-7 {rng.randint(6, 14)}. "
            "Patient discussed stressors at work and sleep disruption. Continue SSRI, CBT weekly. Safety plan reviewed; "
            "denies SI/HI.")
    return "Behavioral health follow-up note", body + _sig(rng, author), {"phq9": True}


def substance_use_note(rng, *, dx: tuple[str, str], author: str) -> tuple[str, str, dict]:
    body = (f"Calderwick Recovery Program (42 CFR Part 2 program). Diagnosis: {dx[1]} ({dx[0]}). In sustained remission on "
            "buprenorphine-naloxone 8/2 mg daily. Urine drug screen as expected. Continue group counseling.\n"
            "NOTICE: This record is protected by 42 CFR Part 2 and may not be redisclosed without written consent.")
    return "Substance use treatment progress note", body + _sig(rng, author), {"part2": True}


GENETIC = {
    "BRCA2": ("Hereditary cancer panel", "Pathogenic variant detected: BRCA2 c.5946delT (p.Ser1982fs). Genetic counseling completed."),
    "F5": ("Thrombophilia genetic panel", "Factor V Leiden (F5 c.1601G>A) heterozygous. Prothrombin G20210A not detected."),
    "APOE": ("APOE genotyping", "APOE e3/e4 genotype. Results discussed with patient; no clinical action recommended."),
}


def genetic_report(marker: str, author: str) -> tuple[str, str, dict]:
    title, body = GENETIC[marker]
    return title, body + f"\n\nReported by Calderwick Genomics Laboratory; reviewed by {author}.", {"marker": marker}
