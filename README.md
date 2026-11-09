# Instamart Customer Intelligence & Support Copilot

## Overview
This capstone builds a reproducible offline analytics and support workflow using synthetic Instamart-style data. It combines data quality and SQL, customer segmentation and lapse prediction, support-ticket triage, and a retrieval/tool-using support copilot. All LLM-like behavior is simulated locally through `mock_llm.py`; no API key, network call, or paid service is needed.

**Important reproducibility note:** Run the pipeline from the repository root. The supplied data generator is deterministic. Outputs are generated locally and are not intended to represent real customers or actual Instamart operations.

## Reproduce
1. Install Python 3.11 or newer.
2. Create a virtual environment: `python -m venv .venv`
3. Activate it (Windows: `.venv\Scripts\activate`; macOS/Linux: `source .venv/bin/activate`).
4. Upgrade pip: `python -m pip install --upgrade pip`
5. Install dependencies: `pip install -r requirements.txt`
6. Generate the raw data: `python generate_data.py`
7. Run the complete pipeline: `python run_all.py`
8. Inspect cleaned tables in `data/clean/`, SQLite database at `data/instamart.db`, SQL at `sql/queries.sql`, and generated files in `outputs/`.

## Part A
### Audit and cleaning
The pipeline reads customer, product, and order CSVs; normalizes city/gender values, parses dates and numeric values, removes duplicate rows and duplicate order IDs, derives missing amounts from price × quantity × (1 − discount), removes invalid negative delivery times, and imputes missing delivery duration for completed orders using category medians. Cancelled orders retain missing delivery time.

The validation script checks customer/product counts, unique order IDs, nonmissing amounts, valid ages, allowed gender categories, no negative delivery times, and existence of all SQLite tables. A successful run prints `ALL CHECKPOINTS PASSED`.

### SQL and analysis
`sql/queries.sql` contains seven queries demonstrating filtering and aggregation, three-table joins, scalar subqueries, anti-joins, CTEs, window ranking, and cumulative revenue. The queries are intended to be run against `data/instamart.db`. Monetary values are in INR.

### Interpretation
- Data cleaning is not a substitute for validating business rules with the source system.
- Revenue in this exercise means the sum of amounts on completed orders after the cleaning rules.
- City and category summaries are descriptive; correlations do not establish causation.

## Part B
### RFM segmentation
RFM features are recency (days since last completed order relative to 2025-10-01), frequency (distinct completed orders), and monetary (completed spend). The clustering pipeline scales these features and uses KMeans with `random_state=42`, `n_init=10`, and four clusters. Cluster IDs are arbitrary; segment names are assigned from relative monetary profiles, so labels should be interpreted through the profile table rather than by cluster number. PCA reports a two-component projection for exploratory interpretation.

### Lapse model
The prediction cohort consists of customers with at least one completed order before 2025-09-01. A customer is labelled lapsed when no completed order occurs during 2025-09-01 through 2025-09-30. Features are aggregated only from orders before the cutoff, alongside customer attributes. A stratified train/test split is used; preprocessing is fitted through a pipeline to avoid fitting encoders/scalers on test data. Logistic regression and random forest are tuned with cross-validation using F1. Training-only random oversampling is compared against the original, unchanged test set. The selected pipeline is persisted to `outputs/lapse_model.joblib` and reloaded to check prediction parity.

`outputs/retention_list.csv` contains up to ten premium-segment test customers ranked by predicted lapse probability. This list is illustrative: premium membership is derived from full-window RFM and therefore is not a fully leakage-free operational targeting feature. A production version should compute segment membership as-of the prediction cutoff.

## Part C
Ticket text is redacted in the required order: email, phone number, then order ID. Empty and overlong messages are routed to human review without a model call. Eligible tickets are classified using an offline zero-shot or few-shot prompt, JSON validation, keyword fallback, bounded retries with exponential backoff, and a running token budget. A separate low-budget run demonstrates budget exhaustion. The final output is `outputs/triage_results.csv`; the budget demonstration is `outputs/triage_budget_demo.csv`.

Routing policy:
- skipped, too long, invalid output, or budget-exhausted tickets → `human_review`, NORMAL.
- fraud → `security_team`, HIGH.
- other valid tickets for Premium customers → `premium_desk`, HIGH.
- other valid tickets → `support_queue`, NORMAL.

The mock model intentionally injects occasional transient errors and malformed/invalid category outputs. Metrics therefore describe this local simulation, not a real language model.

## Part D
### Retrieval-augmented policy answers
Five short policy documents are chunked into word windows with overlap. TF-IDF vectors and cosine similarity retrieve the top three chunks. The policy answer prompt requires grounding in the retrieved context. Retrieval quality is evaluated using expected source documents and fact substring checks. A no-overlap run can be used to discuss how chunk boundaries may split relevant policy details.

### Tools and agent
The agent exposes order lookup, policy search, refund calculation, refund issuance, and human escalation. It checks order status and delivery duration before a refund is issued. Tool observations are checkpointed under `state/`, and an S1 crash/resume demonstration preserves completed tool calls. Stop-safe demonstrations cover token-limit and timeout fallbacks; a bounded iteration count prevents endless tool loops.

The JSONL logs in `outputs/agent_runs.jsonl` contain scenario outcomes, final answer, model-call/token estimates, and tool steps. `outputs/refund_ledger.jsonl` records simulated side effects. This is a learning exercise, not a payment system; production code would need idempotency keys, transaction guarantees, authorization, audit controls, and secure secrets management.

## Limitations and Next Steps
- The datasets and LLM behavior are synthetic. Results are not evidence about actual customers.
- A production model needs temporal validation, drift monitoring, calibrated probabilities, fairness checks, and business-approved intervention thresholds.
- RFM clustering is sensitive to scaling, outliers, snapshot dates, and the chosen number of clusters.
- Lapse labels and feature windows need to be versioned; segments should be computed as-of the prediction date to avoid leakage.
- The offline mock classifier is keyword-driven and cannot represent the quality or failure modes of a production LLM.
- TF-IDF retrieval is lexical rather than semantic. Improve it with a reviewed corpus, better chunking, retrieval evaluation, and grounded-answer checks.
- Refund actions must be idempotent and require authorization and durable transactional records before production use.

### Refund-policy data limitation

The written policy defines lateness as more than 45 minutes **after the promised delivery time**. The supplied `orders` table contains `delivery_minutes` (delivery duration) but does not contain a promised-delivery timestamp or an actual delay-from-promise field. These values are not interchangeable. The copilot therefore fails closed and routes refund requests requiring this comparison to human review; it does not automatically issue a refund based only on delivery duration. The refund tool independently verifies that the order exists, is completed, and has a matching charged amount before any refund can be recorded.

### Model and budget safeguards

The lapse-model preprocessing imputes missing values inside the training pipeline, and the oversampled Logistic Regression candidate is evaluated alongside the other candidates before selecting the saved model. Ticket triage reserves a conservative completion-token allowance before each model call so the configured budget is not exceeded.
