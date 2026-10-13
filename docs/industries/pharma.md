# Pharma and life sciences: Kelvaro Biosciences

Laboratory data retrieval. API reference: `/docs/pharma`. Base path: `/pharma`.

## Data

10 studies (preclinical to Phase III; open-label and double-blind; active, locked and closed), 60 sites, 19 protocol
versions, 16 validated methods in 22 versions, 13 instruments (one 9 days past calibration, one out of service), 29
study assays, 929 pseudonymized subjects, about 8,300 samples, 284 analytical runs with QC detail and about 13,400
results.

## Sample records

| Record | Situation | What the data shows |
|---|---|---|
| `KLV-101-201` | Phase II double-blind RA (oral JAK1 inhibitor), active | IL-6 at Week 12 by arm: placebo -5%, 50 mg -39%, 150 mg -61% from baseline |
| `KLV-204-101` | Phase I open-label KRAS G12C, three dose cohorts | PK rises with cohort dose; the latest PK run is flagged `instrument_calibration_overdue` |
| `KLV-310-301` | Phase III double-blind psoriatic arthritis (anti-IL-17A/F mAb), CRO lab | Three protocol versions; ADA positivity climbs from 2.6% at Day 1 to 6% at Week 24 |
| `BAT-200001` | Latest IL-6 run on KLV-101-201, about 2 days ago | Failed QC (2 of 6 QCs in limits); 50 results rejected, excluded by default (`include_failed_qc=true` returns them), reanalysis pending |
| `SUBJ-1001` | KLV-101-201 subject, 150 mg arm, completed | Hemolyzed Week 4 serum sample, flagged on IL-6 and CRP |
| `INS-0102` | Vantoro TQ-6800 #2 | Calibration 9 days overdue; KLV-204 PK runs after the due date are flagged |

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"
Q='{"question":"What were IL-6 levels at week 4 in the KLV-101 phase 2 RA study?","max_rows":5}'

# resolves KLV-101-201 (compound and phase), IL6 (synonym) and W4; stats overall and by arm, provenance, warnings
curl -s -H "$T" -H "$J" -X POST $B/pharma/data-requests -d "$Q"
# excludes the 23 Week 12 results from BAT-200001 (failed QC) and says so
curl -s -H "$T" -H "$J" -X POST $B/pharma/data-requests -d '{"study":"KLV-101","analyte":"interleukin 6","visit":"week 12"}'
curl -s -H "$T" "$B/pharma/studies/KLV-101-201/results/summary?analyte=IL-6&by_arm=true"
curl -s -H "$T" "$B/pharma/studies/KLV-101-201/results?analyte=PK&visit=W4&arm=HIGH"
curl -s -H "$T" $B/pharma/batches/BAT-200001                      # QC levels, failure reason, rejected results
curl -s -H "$T" "$B/pharma/studies/KLV-204-101/batches?calibration_overdue=true"
curl -s -H "$T" $B/pharma/instruments/INS-0102
curl -s -H "$T" "$B/pharma/studies/KLV-310-301/results/summary?analyte=ADA"
```
