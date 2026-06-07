# Babu Ceramics Agent

**Routing workflow email assistant for a handmade ceramics business. 87% accuracy on 50 test queries, saves owner ~15 hrs/month, costs $0.15/month to operate.**

## Inspiration

Small ceramics businesses receive 10–20 customer emails per week asking about product details, style recommendations, shipping, returns, and custom commissions. These queries are repetitive and well-defined, but they demand brand voice, accurate catalog data, and human judgment on high-stakes flows. Babu Ceramics needed a system that could handle the volume while preserving trust and tone—not a black-box agent that guesses prices or policies.

## Problem

Olivia was spending **15+ hours per month** drafting and reviewing email replies manually. The work is predictable (intent taxonomy is small and stable), but still requires:
- Consistent brand voice (creator-to-creator, warm, first-person singular)
- Accurate structured data (prices, materials, dimensions, care instructions)
- Human judgment (shipping policy, returns case-by-case, custom order feasibility)

**Goal:** Cut manual effort without sacrificing trust, tone, or correctness.

## Solution: Routing Workflow, Not a Pure Agent

Rather than a fully autonomous agent, I chose a **routing agentic workflow**—Python orchestrates the flow deterministically; the LLM runs only at defined, measured steps:

```
Fixed Python orchestration
        │
        ├── [LLM] classify intent
        ├── Fixed routing logic
        ├── [LLM] extract entities (e.g., item name)
        ├── Fixed Supabase query / tool execution
        └── [LLM] write reply in Olivia's voice
```

**Why this approach?**

| Approach | Problem |
|----------|---------|
| Fully autonomous agent | Higher latency/cost, harder to debug, overkill for predictable intents |
| Single mega-prompt | Weak tool control, hallucination risk on SKUs and prices |
| Heavy agent framework (LangChain) | Abstractions hide failure modes; each step harder to justify and debug |

**Tradeoff:** Designed for **async email** (~10–15 conversations/month), not chat-style instant replies. 1.5-second latency is acceptable; instant replies are unnecessary.

## Architecture

Babu Ceramics Agent classifies inbound customer messages, routes them to specialized handlers, and uses Claude tool-calling where structured data is required. The server stays stateless; Supabase holds conversations, catalog, and shop knowledge. Email is ingested via IMAP polling (~30 min); production LLM calls are traced in Helicone for observability.

### High-Level Flow

```
Customer email (IMAP, ~30 min poll)
    ↓
[run_router()] — intent classifier + keyword fallback
    ├── item_inquiry   → catalog tools (price, details, collections)
    ├── recommendation → grounded LLM + catalog + editorial context
    └── orders         → sub-router (shipping / returns / custom / status)
    ↓
[Human-review gate] on incomplete high-stakes flows
    ↓
[Customer reply OR notify Olivia] (no unsafe auto-send)
```

### Key Features

- **Multi-intent routing** with LLM classifier + keyword fallback on API failure
- **Eight custom tools** with rich schemas and input_examples (no tool-search; <10 tools justifies manual definition)
- **Anthropic SDK directly**—no LangChain; manual tool definitions for full trace/eval visibility
- **Supabase** for catalog, conversations (~3-month retention), and unstructured shop guides
- **No RAG**—~3.5k tokens of stable content passed upfront as context (cheaper and simpler than vector DB)
- **No vector DB**—full-catalog recommendations for <20 SKUs
- **Human-in-the-loop** via `needs_human_review` flag on shipping/returns/custom flows
- **Conversation memory** decoupled from Gmail thread_id via `[ref: …]` in subject (survives email client quirks)
- **Line-by-line prompting** over paragraph blocks for clearer routing and tool behavior
- **Claude Sonnet default**—asks clarifying questions instead of assuming on ambiguous customer email

### Example Capabilities

| User Question | Route | Behavior |
|---|---|---|
| "What collections do you have?" | item_inquiry | Lists Spring, Fall, Summer with descriptions |
| "Price of the pasta bowl?" | item_inquiry | Fetches exact price + availability |
| "Newlyweds—suggest pottery for our home" | recommendation | Grounded suggestions using collection stories + editorial picks |
| "Custom order with initials on a potpourri bowl" | orders → custom_order_enquiry | Extracts specs, may escalate if incomplete |
| "Return policy on opened items?" | orders → returns_enquiry | Answers from FAQ, escalates if case-specific |
| "Shipping cost for 4 bowls to 95125?" | orders → shipping_enquiry | Calculates cost + timeline |

## Architecture Decisions

### Stateless Backend + Supabase

All DB access flows through a translator module (`generate_thread_id`, `create_conversation`, `get_conversation`, `update_messages`). No scattered queries. This decouples state from the agent, enabling horizontal scaling if needed.

### Email: IMAP Polling (30 min)

Email doesn't need push latency. IMAP + `imaplib` avoids Google Cloud OAuth setup for a side project; 30-min poll fits low traffic and feels more human than instant bot replies.

### Human Review on High-Stakes Tools

Tools return `{complete, message}` → normalized to `needs_human_review`. If `true`: update DB, email owner, **no auto-reply sent**. This prevents the agent from committing to policy (refund, shipping timeline, custom feasibility) without order context.

### Unstructured Knowledge Without RAG

Collection stories, care guides, artist notes, FAQs, editorial picks (~3.5k tokens, rarely changing) are passed as full context upfront—not fetched via vector search. For stable, small content, this is cheaper and eliminates retrieval failures.

### Observability (Helicone)

Multiple Claude calls per email (intent, tools, synthesis). Helicone instruments all calls with custom headers (handler, intent, thread)—no refactor across handlers. This gives instant visibility into latency, token usage, and cost breakdown by intent type.

## Testing & Evals: From Manual Labels to Automation

Evaluation was a must-have before treating replies as production-ready. Without structured checks, multi-step LLM workflows are guesswork.

### 1. Foundation Testing (Integration)

Before agent evals, validated Supabase plumbing in isolation:
- Does `generate_thread_id()` produce a valid UUID?
- Can we write conversations to Supabase?
- Can we read back what we wrote?

Separate Python test functions, run individually, results confirmed in the Supabase UI.

### 2. Golden Dataset + Manual Labeling

Built an initial set of ~50 real-world-style questions; ran each through the agent. Exported traces to CSV; manually labeled each output on dimensions that mattered:
- Routing correctness (right handler called?)
- Factual accuracy (correct price, material, dimensions?)
- Tone (sounds like Olivia?)
- Completeness (answered fully without dropping details?)
- Human-review appropriateness (correctly flagged or not?)

Used spreadsheet rules to verify escalation behavior:
- (a) Accurately flagged (or not flagged) for human review
- (b) Handoff included the information Olivia needs before she replies

### 3. Code-Based Evals (Automated, Repeatable)

| Dimension | What It Checks | Result |
|---|---|---|
| **Routing accuracy** | Correct route handler (item_inquiry, recommendation, orders)? | 97.3% (improved from 76% after qualitative confidence labels) |
| **Factual accuracy** | Correct price, material, dimensions for named items? | 93% (26/28 passing) |
| **Human-review escalation** | Correct flag / no-flag on shipping, returns, custom-order flows? | 89% (improved from 61% after intent gates + deterministic phrase matching) |

These are the evals that scale in scripts—rerun on every prompt or routing change without re-labeling everything by hand.

### 4. LLM-as-Judge Evals (Subjective Quality)

| Dimension | What It Checks |
|---|---|
| **Tone accuracy** | Matches Olivia's voice (warm, creator-to-creator, first-person singular) |
| **Completeness** | Answers the question without dropping key details |
| **Clarifying-question quality** | One focused question when needed; doesn't over-ask |
| **Recommendation quality** | Grounded, occasion/style-aware, uses editorial picks appropriately |

### 5. LLM-Judge Workflow

1. **Build golden test set** — hand-picked queries covering key scenarios (~10–50 per intent type)
2. **Generate agent outputs** — run each query through `run_router()` (batch script)
3. **Run LLM judge** — `llm_judge.py` scores each response `good / average / bad` per criterion
4. **Compare with human labels** — agreement rate between manual labels and judge
5. **Iterate** — low agreement → fix judge prompt; high agreement → trust judge, improve system prompts, rerun

### 6. What Evals Proved Before Production

✅ Routing and tool paths behave predictably on labeled sets
✅ Human-review gates fire when policy data is incomplete (prevents unsafe auto-replies)
✅ Subjective quality is measurable and calibrated (judge + human agreement >85%)
✅ Supabase conversation layer works end-to-end for follow-up threads
✅ Hallucination rate <3% after prompting constraints (never invents prices/policies)

### 7. Prompt Engineering Insights

**Line-by-line rules beat paragraph guidance.** Instead of "Consider the customer's needs when recommending," I used explicit rules: "If customer has answered any question, STOP asking. Make your best recommendation from what you know." This reduced unnecessary clarifying questions by 68%.

**Qualitative confidence labels (high/medium/low) beat numeric scores.** Initial numeric confidence scores (0.75) were unreliable for multi-intent routing. Switching to qualitative labels with explicit routing rules reduced multi-intent collisions from 24% to 0%.

**Recommendation quality improved from 58% to 89% "Great"** after restructuring the prompt to show Claude different request types (specific, style, occasion, vague) with explicit handling rules per type.

## Performance & Observability

### Metrics (Measured via Helicone)

- **Latency:** 1.5 sec average (p50: 1.1s, p95: 3.0s) — acceptable for async email
- **Cost:** $0.0025 per query, **~$0.16/month** on current volume (15 queries/week)
- **Accuracy:** 87% on 50 diverse test queries
- **Autonomous handling:** 85% (queries resolved without human intervention)
- **Token efficiency:** ~1,900 tokens average per query (multi-step orchestration)

### Impact

✅ **~15 hours/month saved** for shop owner (was manually replying to every email)
✅ **87% accuracy** on diverse test queries
✅ **85% autonomous** (queries resolved without escalation)
✅ **$0.15/month cost** (negligible; pays for itself in minutes)
✅ **Eval loop made every decision defensible** — routing, tool choice, escalation logic

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| **LLM** | Anthropic Claude (Sonnet default) | Asks clarifying questions instead of assuming; strong tool-calling |
| **SDK** | Anthropic Python SDK (no LangChain) | Manual tool definitions → full trace/eval visibility |
| **Data** | Supabase (catalog, conversations, guides) | Stateless backend; conversation memory decoupled from Gmail |
| **Email** | IMAP polling + SMTP (`gmail_listener.py`) | No OAuth needed; 30-min poll acceptable for async email |
| **Observability** | Helicone (production traces) | Instruments all LLM calls with custom headers; zero refactor |
| **Evals** | Code-based checks + LLM-as-judge + golden CSV | Foundation tests → manual labels → automated judges → iteration |
| **Runtime** | Python 3, `python-dotenv` | Simple, familiar, easy to debug |

## Architecture Decisions Explained

### Why routing, not a pure agent?
Predictable intent taxonomy; cost/latency constraints; each step is measurable and defensible.

### Why no LangChain?
First multi-route agent build. Abstractions would hide failure modes. Scope is small enough (8 tools, 3 intents) to justify manual definition for full debug clarity.

### Why no RAG?
~3.5k tokens of stable content (collection stories, care guides, FAQs). Vector DB adds complexity with minimal benefit. Full context upfront is cheaper and simpler.

### Why human review?
Shipping, returns, and custom orders are incomplete-by-design without order context. The agent should never guess—escalate instead.

### Why IMAP + 30 min?
Email channel; low volume (10–15 convos/month); human-like response pacing feels right. OAuth overhead of Gmail API not justified.

### How do you know it works?
Foundation DB tests + ~50-query golden set + code evals (routing, facts, escalation) + calibrated LLM judge (tone, completeness, rec quality) + thematic failure analysis on edge cases.

## What This Demonstrates

- **Systems thinking:** Fixed orchestration for clarity + strategic LLM placement for efficiency
- **Evaluating agentic systems:** Golden datasets, code-based evals, LLM-as-judge, calibration against human labels, thematic failure coding
- **Prompt engineering:** Line-by-line rules, qualitative signals, explicit handling for different query types
- **Observability:** End-to-end tracing for debugging and cost analysis
- **Trade-off analysis:** When to use RAG (didn't), when to use frameworks (didn't), when to hand-code (did), why

## Tags

`AI Agents` `Routing Workflows` `Tool Calling` `Code-based Evals` `LLM-as-Judge` `Observability` `Supabase` `Python` `Claude API`

---

**Harini Rao** · Portfolio project · [View repository](https://github.com/hbeanss009/BabuCeramicsAgent)
