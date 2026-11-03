# Validation report

The project was executed from a clean generated-data state with `python run_project.py` in the current environment (Python 3.13). The command exited with status 0.

## Checks passed

- The supplied `generate_data.py` and `mock_llm.py` are byte-for-byte identical to the uploaded originals.
- Deterministic generator output: 1,200 customers, 40 products, 13,084 raw orders and 164 tickets.
- Clean order table: 12,309 unique orders (11,110 completed; 1,199 cancelled); completed revenue INR 2,998,668.80.
- All seven SQL queries execute and return 30, 30, 11, 25, 550, 1,175 and 183 rows respectively.
- RFM contains 1,175 customers; K-means diagnostics cover K=2..8; lapse cohort is 1,156 with 443 lapsed.
- Ticket output contains 164 rows; few-shot classification statuses are 135 JSON, 12 keyword, 9 invalid, 4 long and 4 empty. No PII patterns remain in redacted prompts.
- Policy evaluation contains 14 questions; 12 answerable questions match expected document/fact, and 2 unknown questions trigger fallback.
- All seven agent scenarios execute; token and timeout stop-safe demonstrations execute; S1 resumes without replaying the first two tool calls.
- Clean one-pass refund ledger contains two issue-refund events and one escalation event.

## Known rubric deviations / implementation limitations

- The zero-shot 6,000-token demonstration classifies 128 tickets before budget exhaustion (20 tickets are budget-exhausted); it does not reach 147 classified tickets. The observed accuracy is 109/128 (85.16%).
- Measured lapse model metrics are recorded as observed. Random Forest selected max_depth=5 and min_samples_leaf=5; Logistic Regression F1 is 0.6433 and Random Forest F1 is 0.6627. These may differ from approximate reference metrics in the assignment brief.
- Part D uses deterministic Python tool orchestration for its scenarios, not a model-decided ReAct loop. It demonstrates tools, guardrails, checkpoint/resume and ledger behavior, but does not fully implement an autonomous ReAct agent.
- The policy mock is a deterministic offline stand-in, not a hosted language model.
- Execution was tested in the provided runtime with Python 3.13, not separately in a fresh Python 3.11 installation.

Do not describe these known deviations as passing rubric checkpoints. Review the assignment handout and instructor expectations before final submission.
