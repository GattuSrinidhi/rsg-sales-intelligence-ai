# Vectorless RAG AI Agent Specification

## 1. Architectural Blueprint
The **RSG Sales Intelligence AI Assistant** implements a **Vectorless RAG (Retrieval-Augmented Generation)** architecture tailored for structured enterprise databases.

```
                  ┌──────────────────────────────┐
                  │ User Natural Language Query  │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │   Intent Interpretation      │
                  │   (Gemini 2.5 Flash Runtime) │
                  └──────────────┬───────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         │ (Success: Engine='gemini')                    │ (Error / Offline: Engine='deterministic_fallback')
         ▼                                               ▼
┌──────────────────────────────┐                ┌──────────────────────────────┐
│  Pydantic Schema Validation  │                │ Rule-Based Regex Parser      │
│  (Strict Intent & Params)    │                │ (100% Deterministic Fallback)│
└──────────────┬───────────────┘                └──────────────┬───────────────┘
               │                                               │
               └───────────────────────┬───────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │    Allowlisted Tool Security Router      │
                  │    (Rejects Arbitrary Functions & SQL)   │
                  └────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │    Deterministic Analytics Engine        │
                  │    (Pure SQL / Python Calculations)      │
                  └────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │ Grounded Factual Response Synthesis      │
                  │ (Zero Numerical Hallucinations + Audit)  │
                  └──────────────────────────────────────────┘
```

---

## 2. Why Vectorless RAG? (Interview Defense)

* **Traditional RAG vs. Vectorless RAG**:
  * *Traditional RAG* chunks unstructured documents (PDFs, wikis) into vector embeddings and performs semantic cosine similarity search.
  * For structured relational databases (financial ledgers, sales tables), vector embeddings fail because vector distance cannot calculate sums, averages, or month-over-month percentage changes.
  * **Vectorless RAG** retrieves database schema metadata and domain business rules as context, prompts the LLM to classify user intent and extract parameters into a strict schema, validates the contract via Pydantic, and executes verified, deterministic database functions.
* **Guarantee**: Eliminates numerical hallucinations. The LLM interprets the question; deterministic code calculates the answer.

---

## 3. Intent Schema & Pydantic Contracts

Defined in [`src/agent.py`](../src/agent.py):

### Intent Types
* `TOTAL_REVENUE`: Questions regarding total, gross, or net sales revenue.
* `TOP_PRODUCT`: Questions about the highest revenue or highest volume products.
* `MONTHLY_TREND`: Questions about sales performance over time or monthly trends.
* `TOP_REGION`: Questions identifying top-performing geographic sales regions.
* `REVENUE_DELTA`: Questions comparing revenue changes between two months.
* `CLARIFICATION_NEEDED`: Questions missing necessary parameters (e.g., asking for monthly comparison without naming months).
* `UNKNOWN`: Questions outside the sales domain (e.g., general knowledge, weather).

### Agent Response Schema
```python
class AgentResponse(BaseModel):
    success: bool
    query: str
    intent: str
    engine: Literal["gemini", "deterministic_fallback"]
    answer: str
    supporting_data: Dict[str, Any]
    execution_trace: Dict[str, Any]
```

---

## 4. Allowlisted Tool Routing Matrix

| Intent | Allowlisted Analytics Function | Extracted Parameters | Grounded Return Data |
|---|---|---|---|
| `TOTAL_REVENUE` | `analytics.get_total_revenue` | None | Net revenue, Gross revenue, Total discounts, Units, Category/Channel breakdown. |
| `TOP_PRODUCT` | `analytics.get_top_product` | `metric: 'revenue' \| 'units'` | Winner product, runner-ups, complete product ranking, units sold. |
| `MONTHLY_TREND` | `analytics.get_monthly_revenue_trend` | None | Chronological 6-month table, MoM absolute ($\Delta ₹$) and percentage ($\Delta \%$) deltas, peak month, average monthly revenue. |
| `TOP_REGION` | `analytics.get_top_region` | `metric: 'revenue' \| 'units'` | Revenue leader, volume leader, unanimous winner check, regional breakdown table with percentage shares. |
| `REVENUE_DELTA` | `analytics.get_revenue_delta` | `month_a`, `month_b` | Baseline revenue, target revenue, absolute delta, percentage delta, direction (`increased`/`decreased`). |
| `CLARIFICATION_NEEDED` | *None* | `clarification_message` | Guidance prompt for missing parameters. |
| `UNKNOWN` | *None* | *None* | Polite guidance specifying the 5 supported business queries. |

---

## 5. Security Guardrails & Resilience

1. **No Arbitrary SQL**: Gemini is **never** permitted to generate or execute raw SQL. All data access occurs through pre-tested, parameterized SQLite queries in [`src/analytics.py`](../src/analytics.py).
2. **Deterministic Fallback**: If `GEMINI_API_KEY` is not provided, the network is offline, or Gemini returns malformed output, the system seamlessly transitions to `classify_intent_deterministic()` with `engine = "deterministic_fallback"`.
3. **Auditability**: Every response includes an `execution_trace` recording the intent, tool called, parameters, latency in milliseconds, and safety verification.
4. **Credential Isolation**: No API keys, system prompts, or internal stack traces are ever exposed in logs or user-facing responses.
