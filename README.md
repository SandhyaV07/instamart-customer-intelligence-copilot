# Instamart Customer Intelligence & Support Copilot

Educational capstone implementation using deterministic synthetic Instamart-style data. The project runs locally with Python, SQLite and an offline rule-based LLM stand-in. No API key, hosted LLM, paid service or network access is required.

## Overview

The project demonstrates four connected workflows:

- **Part A — Data foundation:** audit raw CSV exports, standardize and clean records, persist trusted tables to CSV and SQLite, and query them with SQL.
- **Part B — Customer intelligence:** create RFM features, compare K-means cluster counts, visualize dimensionality with PCA, and train/evaluate a leakage-aware lapse classifier.
- **Part C — Support triage:** redact personal information, enforce input/token guardrails, call the offline classifier with retries, validate responses, and route tickets.
- **Part D — Policy and support agent:** retrieve policy chunks with TF-IDF, evaluate answerability, and run bounded refund workflows with checkpoints, a ledger and safe fallbacks.

All customer, product, order and ticket records are fictional.

## Reproduce

### Requirements

- Python 3.11 or newer recommended
- SQLite (Python's standard-library `sqlite3` module)
- Packages listed in `requirements.txt`: pandas, numpy, scikit-learn and joblib

### Run on Windows PowerShell

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_project.py
```

`run_project.py` runs `run_all.py`, which executes the unchanged supplied `generate_data.py`, then Parts A–D. The generator writes raw CSVs and policy text files under `data/raw/` and `data/policies/`. Cleaned CSVs, the SQLite database, model artifacts, evaluation outputs and agent state are created by the pipeline.

To run an individual part after generating data and running Part A, use:

```bash
python -m src.part_a
python -m src.part_b
python -m src.part_c
python -m src.part_d
```

The pipeline is deterministic except for timestamps written to the refund audit ledger. Re-running Part D appends new ledger audit events; for a pristine demonstration, delete `outputs/refund_ledger.jsonl` before rerunning Part D.

## Part A

### Data generation and raw audit

The original supplied generator was retained unchanged. Its deterministic output is:

| Raw entity | Rows |
|---|---:|
| Customers | 1,200 |
| Products | 40 |
| Orders | 13,084 |
| Tickets | 164 |

Raw order audit findings: 119 exact duplicate rows; 656 pending records; 12,309 distinct order IDs; 120 nonnumeric order amounts; 106 negative delivery durations; and 2,541 blank delivery durations. Customer audit: 61 blank ages, 6 ages outside 10–100, 24 distinct raw city spellings, 10 nonblank gender spellings and 30 blank genders.

### Cleaning and persisted tables

- City and gender values are standardized. City counts: Pune 227, Delhi 210, Bengaluru 197, Chennai 191, Hyderabad 191, Mumbai 184.
- Gender counts: Female 610, Male 560, Unknown 30.
- Invalid ages are converted to missing and imputed using the median age within each city.
- Exact duplicate rows are removed; duplicate order IDs are resolved by retaining the latest timestamp; pending rows are excluded from the analytical orders table.
- Nonnumeric/missing amounts are imputed from catalogue price, quantity and discount. Negative delivery durations become missing. Missing completed-order delivery times are imputed using completed-order category medians. Cancelled orders retain missing delivery times.

| Clean table | Rows |
|---|---:|
| customers | 1,200 |
| products | 40 |
| orders | 12,309 |
| Completed orders | 11,110 |
| Cancelled orders | 1,199 |

Completed-order revenue: **INR 2,998,668.80**. The cleaned order table has no missing amounts. Completed-order delivery durations are imputed; cancelled-order delivery durations remain missing.

### SQL

Seven queries are provided in `sql/queries.sql`: high-volume customers (top 30), city/category revenue, products above average catalogue price, customers without completed orders, above-average customer spend using a CTE, within-city customer ranking, and cumulative daily revenue.

Validated result counts: Q1 30 rows; Q2 30 city/category rows with total revenue INR 2,998,668.80 (largest city/category pair: Bengaluru/Electronics, INR 233,909.45); Q3 11 products; Q4 25 customers; Q5 550 customers above average completed spend (average customer spend INR 2,552.06); Q6 1,175 ranked customers; Q7 183 daily rows with final cumulative revenue INR 2,998,668.80.

## Part B

### RFM and segments

RFM snapshot date: **2025-10-01**. The completed-order RFM table contains 1,175 customers. Recency median is 19 days (minimum 0, maximum 180); mean frequency is 9.46 orders (maximum 33); mean monetary value is INR 2,552.06 (maximum INR 14,766.55).

K-means diagnostics for K=2 through K=8 are saved in `outputs/kmeans_diagnostics.csv`. The reproducible segment solution uses K=4. Segment sizes are 436, 138, 419 and 182. Segment labels are assigned by ascending mean monetary value: At Risk, Regular, Loyal and Premium. PCA explained variance is 0.634 and 0.218 (total 0.852).

### Lapse model

The feature cutoff is 2025-09-01 and the outcome window is September 2025. The cohort contains 1,156 customers; 443 are labelled lapsed (38.32%). The train/test split is 80/20 with stratification. Preprocessing is fitted inside scikit-learn pipelines; oversampling is applied only to the training data.

| Model | Selected parameters | Accuracy | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|
| Logistic Regression | C=1 | 0.7404 | 0.6707 | 0.6180 | 0.6433 |
| Random Forest | max_depth=5, min_samples_leaf=5 | 0.7574 | 0.7000 | 0.6292 | 0.6627 |

The selected model is persisted as `outputs/lapse_model.joblib` and reloaded to verify prediction consistency. Training-only oversampled Logistic Regression metrics are saved in `outputs/oversampled_lr_metrics.csv` (precision 0.5750, recall 0.7753, F1 0.6603). The top 10 Premium customers in the test set by predicted lapse probability are saved to `outputs/retention_list.csv`.

**Interpretation note:** Premium membership is derived from full-window RFM, while the lapse model uses a pre-September feature window. The retention list is therefore an illustrative post-hoc business list, not an independent leakage-free segment evaluation.

## Part C

The triage pipeline processes all 164 tickets in source-file order. Empty tickets are marked `skipped_empty`; tickets longer than 400 whitespace-token estimates are marked `flagged_long`. Email, 10-digit phone and order-ID patterns are redacted before the model call. The redaction counts in the supplied data are 55 emails, 91 phone numbers and 132 order IDs (278 total); no matching PII patterns remain in the redacted prompts.

The mock classifier is reset before each experiment. Transient errors are retried up to three times after the initial attempt with exponential jitter. Valid JSON categories are allow-listed; malformed output is accepted as a keyword category only if exactly one permitted category word is present.

### Few-shot run (100,000-token budget)

| Status | Tickets |
|---|---:|
| classified_json | 135 |
| classified_keyword | 12 |
| flagged_invalid_output | 9 |
| flagged_long | 4 |
| skipped_empty | 4 |
| **Total** | **164** |

147 tickets were classified; accuracy against the synthetic `true_category` labels was 100% (147/147). There were 19 transient errors, all recovered. Results are in `outputs/triage_results.csv`.

### Zero-shot budget demonstration (6,000-token budget)

| Status | Tickets |
|---|---:|
| classified_json | 118 |
| classified_keyword | 10 |
| flagged_invalid_output | 8 |
| budget_exhausted | 20 |
| flagged_long | 4 |
| skipped_empty | 4 |
| **Total** | **164** |

128 tickets were classified before the budget guard stopped further calls; accuracy on those classified tickets was 85.16% (109/128). The run used 6,013 estimated tokens because the budget is checked before a call and the final call can cross the limit. There were 16 transient errors. Results are in `outputs/triage_budget_demo.csv`.

Routing sends fraud to the security team, Premium customers to the premium desk, and other classified tickets to the support queue. Guardrail and invalid-output cases go to human review. The CSV output includes ticket/customer IDs, status, category, segment, priority, route and token count.

## Part D

### Policy retrieval

Five policy files are split into 40-word chunks with 10-word overlap, giving 15 chunks: refund 4, delivery 3, escalation 3, payment 3 and privacy 2. Retrieval uses TF-IDF vectors and cosine similarity, returning the top three chunks. The answer function abstains when the best retrieval score is below 0.05.

The 14-question evaluation is saved in `outputs/policy_eval_results.csv`: 12 answerable questions match the expected document and contain the expected fact in retrieved context; both unanswerable questions trigger fallback (14/14 document/fallback checks and 14/14 fact/fallback checks).

### Refund tools and scenarios

The tools are `get_order`, `search_policy`, `calculate_refund`, `issue_refund` and `escalate_to_human`. The deterministic support workflow has a maximum of six iterations, a 6,000-token guard and a time guard. Refunds apply only to completed orders delivered in more than 45 minutes; amounts above INR 1,000 are escalated to a human lead. The local JSONL ledger is an audit simulation, not a payment integration.

| Scenario | Expected outcome | Observed outcome |
|---|---|---|
| S1 | Refund INR 128.25 | REFUND INR 128.25 |
| S2 | Refund INR 135.00 | REFUND INR 135.00 |
| S3 | Escalate INR 1,999 | ESCALATE |
| S4 | Cancelled order | DENIED |
| S5 | Delivery not over 45 minutes | DENIED |
| S6 | Unknown order | NOT_FOUND |
| S7 | Repeated tool loop | FALLBACK_MAX_ITERATIONS |

Stop-safe demonstrations: token-limit run returns `FALLBACK_TOKEN_LIMIT`; zero-second timeout run returns `FALLBACK_TIMEOUT`. S1 is deliberately interrupted after `get_order` and `search_policy`, then resumed. The saved S1 sequence is `get_order`, `search_policy`, `calculate_refund`, `issue_refund`; the first two tools are not replayed during resume. The refund ledger records one issue-refund action for S1 in a clean one-pass run.

The agent's tool plan is deterministic Python orchestration for this teaching dataset; it is not an autonomous production agent. `outputs/agent_runs.jsonl`, `outputs/refund_ledger.jsonl` and `state/` contain run records, audit events and checkpoints.

## Limitations and Next Steps

- This is a synthetic teaching project. It does not connect to Instamart, payment providers, customer accounts or a hosted language model.
- `mock_llm.py` is the supplied offline deterministic stand-in, not a real LLM.
- The support-agent tool sequence is deterministic orchestration rather than an LLM-decided ReAct loop. It demonstrates bounded tools, state persistence, resume and fallbacks, but should not be represented as a production agent.
- The zero-shot 6,000-token demo classifies 128 tickets before budget exhaustion; this is the observed run, not a 147-ticket result.
- Model metrics are the measured results from this implementation and may differ from approximate targets in the capstone handout. Do not replace measured values with target values.
- The retention list is illustrative because Premium status is assigned from the full RFM window.
- The refund ledger is a local JSONL audit trail; it does not transfer money. Production use would require authentication, authorization, idempotency keys, secure PII handling, monitoring, data lineage, drift checks and mandatory human approval.
