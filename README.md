Inspiration
Small ceramics businesses get repetitive customer emails—catalog questions, style recommendations, shipping, returns, and custom commissions. Babu Ceramics needed replies that sound like Olivia, use real catalog data, and know when a human must step in—not a black-box agent that guesses prices or policies.

Problem
Olivia was spending significant time drafting and reviewing email replies. The work is repeatable and well-defined, but still needs brand voice, accurate structured data, and human judgment on shipping, returns, and custom orders.

Goal: Cut manual effort (~3 hrs/week target) without sacrificing trust, tone, or correctness.

Product decision: routing workflow, not a pure agent
Approach	Why not default here
Fully autonomous agent
Higher latency/cost, harder to debug, overkill for a predictable intent taxonomy
Single mega-prompt
Weak tool control, hallucination risk on SKUs/prices
Heavy agent framework
Abstractions hide failure modes; harder to justify each step
Choice: A routing agentic workflow—Python orchestrates the flow; the LLM runs only at defined steps:

Fixed Python orchestration
        │
        ├── [LLM] classify intent
        ├── Fixed routing logic
        ├── [LLM] extract entities (e.g. item name)
        ├── Fixed Supabase query / tool execution
        └── [LLM] write reply in Olivia's voice
Tradeoff: Balance latency, cost, and task performance for async email (~10–15 conversations/month), not chat-style instant replies.

Overview
Babu Ceramics Agent classifies inbound customer messages, routes them to specialized handlers, and uses Claude tool-calling where structured data is required. The server stays stateless; Supabase holds conversations, catalog, and shop knowledge. Email is ingested via IMAP polling; production LLM calls are traced in Helicone.

High-level flow

Customer email (IMAP, ~30 min poll)
    → run_router() — intent classifier + fallback
        → item_inquiry   → tool loop (catalog, price, details, collections)
        → recommendation → grounded LLM + Supabase catalog + editorial context
        → orders         → sub-router → shipping / returns / custom / status tools
    → human-review gate on incomplete high-stakes flows
    → customer reply OR notify Olivia (no auto-send)
Features
Multi-intent routing with LLM classifier + keyword fallback on API failure
Eight custom tools with rich schemas and input_examples (no tool-search; <10 tools)
Anthropic SDK directly—no LangChain; manual tool definitions for trace/eval visibility
Supabase for catalog, conversations (~3-month retention), and unstructured shop guides
No RAG for ~3.5k tokens of stable content—fetched upfront as context
Full-catalog recommendations for <20 SKUs—no vector DB
Human-in-the-loop via needs_human_review on shipping/returns/custom flows
Conversation memory in Supabase (decoupled from Gmail thread_id via [ref: …] in subject)
Line-by-line prompting over paragraph blocks for clearer tool and routing behavior
Claude Sonnet default—asks clarifying questions instead of assuming on customer email
Example capabilities
User question	Route	Behavior
“What collections do you have?”
item_inquiry
view_collection
“Show items in the Dot collection”
item_inquiry
view_catalog_items
“Price of the pasta bowl?”
item_inquiry
get_item_price
“Newlyweds—suggest pottery for our home”
recommendation
Catalog + editorial/collection context
“Custom order with initials on a potpourri bowl”
orders
custom_order_enquiry → may escalate to human review
“Return policy on opened items?”
orders
returns_enquiry
“Shipping cost for 4 bowls to 95125”
orders
shipping_enquiry
Architecture decisions (defensible to eng / product)
Stateless backend + Supabase
DB access only through a translator module (generate_thread_id, create_conversation, get_conversation, update_messages). No scattered queries.

Email: IMAP polling (30 min)
Email doesn’t need push latency. IMAP + imaplib avoids Google Cloud OAuth for a side project; 30-min poll fits low traffic and feels more human than instant bot replies.

Human review on high-stakes tools
Tools return {complete, message} → normalized to needs_human_review. If true: update DB, email Olivia, no customer auto-reply.

Unstructured knowledge without RAG
Collection stories, care guides, artist notes, FAQs, editorial picks (~3.5k tokens, rarely changing) are passed as context—not vector search.

Observability (Helicone)
Multiple Claude calls per email (intent, tools, synthesis). Helicone instruments all calls with headers for handler, intent, thread—no refactor across handlers.

Evals
Evaluation was a must-have before treating replies as shippable. The system makes several Claude calls per request; without structured checks, production issues would be guesswork.

1. Foundation testing (integration)
Before agent evals, validated Supabase plumbing in isolation:

Does generate_thread_id produce a valid UUID?
Can we write conversations to Supabase?
Can we read back what we wrote?
Separate Python test functions, run individually, results confirmed in the Supabase UI.

2. Golden dataset + manual labeling
Built an initial set of ~50 questions; ran each through the agent.
Exported traces to CSV; manually labeled each output on the dimensions that mattered.
Used spreadsheet rules to check human-review behavior:
(a) Accurately flagged (or not flagged) for human review
(b) Handoff included the information Olivia needs before she replies
3. Code-based evals (automated, repeatable)
Dimension	What it checks
Routing accuracy
Correct route handler (item_inquiry, recommendation, orders)
Factual accuracy
Correct price, material, dimensions for named items (structured data)
Human-review escalation
Correct flag / no-flag on shipping, returns, custom-order flows
These are the evals that scale in scripts—rerun on every prompt or routing change without re-labeling everything by hand.

4. LLM-as-judge evals (subjective quality)
Dimension	What it checks
Tone accuracy
Matches Olivia’s voice
Completeness
Answers the question without dropping key details
Clarifying-question quality
One focused question when needed; doesn’t over-ask
Recommendation quality
Grounded, occasion/style-aware picks
5. LLM-judge workflow (how it runs)
Build golden test set — hand-picked queries covering key scenarios (start ~10 per slice; grew toward ~50).
Generate agent outputs — run each query through run_router() (scripted batch or form).
Run LLM judge — run_eval.py + llm_judge.py: Claude scores each response good / average / bad per criterion.
Compare with human labels — agreement rate between your manual labels and the judge.
Iterate — low agreement → fix judge prompt; high agreement → trust judge and improve system prompts; rerun and check score movement.
Per query in the dataset: review output and label across criteria (routing, facts, tone, escalation, etc.).

6. Scaling evals going forward
Code-based (routing, facts, escalation) → keep in repeatable scripts; run after changes to router, tools, or schemas.

LLM-judge (tone, completeness, rec quality) → use when labels are subjective; calibrate judge against human labels before trusting automation.

Dogfooding & real-world testing — use the system yourself and with friendly customers before wider rollout.

Synthetic inputs at scale — don’t rely on generic “plausible questions”; define dimensions (query type, collection, occasion, customer intent, luxury vs standard, etc.) and synthesize diverse queries to hit edge cases—aligned with eval practices from Amal Khan and Hamel Hussain (dimensions → varied test set).

Qualitative synthesis — open codes on failure notes (individual issues), then axial coding into themes (e.g. vague recommendations, missing item names, wrong escalation) to see systemic gaps.

7. What evals proved before prod
Routing and tool paths behave predictably on labeled sets
Human-review gates fire when policy data is incomplete
Subjective quality (tone, recs) is measurable and iterable via judge + human agreement
Supabase conversation layer works end-to-end for follow-up email threads
Impact
Outcome	Result
Owner time saved
~3 hrs/week less manual drafting/review
Intent routing
90%+ accuracy on labeled test cases
Traffic fit
~10–15 conversations/month; 30-min poll; human-paced replies
Risk
Human-review path blocks auto-send on incomplete order flows
Operability
Helicone traces + eval harness make every routing/tool decision reviewable
Tech stack
Layer	Choice
LLM
Anthropic Claude (Sonnet default)
SDK
Anthropic Python SDK (no LangChain)
Data
Supabase (catalog, conversations, guides)
Email
IMAP polling + SMTP; gmail_listener.py
Observability
Helicone (production traces)
Evals
Code-based checks + LLM-as-judge + golden CSV
Runtime
Python 3, python-dotenv
What I’d tell a technical reviewer
Why routing, not a pure agent? Predictable intents; cost/latency; evaluable steps.
Why no LangChain? Scope, learning, and debug clarity on a first multi-route build.
Why no RAG? Small, stable context; full pass is cheaper and simpler.
Why human review? Shipping/returns/custom orders are incomplete-by-design without order details.
Why IMAP + 30 min? Email channel; low volume; human-like pacing.
How do you know it works? Foundation DB tests + ~50-query golden set + code evals + calibrated LLM judge + thematic failure coding.
