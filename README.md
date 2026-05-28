<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Babu Ceramics Agent — Project README</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&display=swap"
      rel="stylesheet"
    />
    <style>
      :root {
        --bg: #f4f0e8;
        --bg-elevated: #faf7f1;
        --ink: #1c1b19;
        --ink-soft: #5c5852;
        --line: rgba(28, 27, 25, 0.1);
        --accent: #2563eb;
        --radius: 12px;
        --font-sans: 'DM Sans', system-ui, sans-serif;
        --font-display: 'Fraunces', Georgia, serif;
      }
      * {
        box-sizing: border-box;
      }
      body {
        margin: 0;
        font-family: var(--font-sans);
        font-size: 17px;
        line-height: 1.6;
        color: var(--ink-soft);
        background: var(--bg);
        background-image: radial-gradient(
          ellipse 120% 80% at 50% -20%,
          rgba(255, 255, 255, 0.7),
          transparent 55%
        );
      }
      .doc {
        max-width: 52rem;
        margin: 0 auto;
        padding: 3rem 1.5rem 4rem;
      }
      header {
        margin-bottom: 2.5rem;
        padding-bottom: 2rem;
        border-bottom: 1px solid var(--line);
      }
      h1 {
        font-family: var(--font-display);
        font-size: clamp(2rem, 5vw, 2.75rem);
        font-weight: 600;
        color: var(--ink);
        line-height: 1.15;
        letter-spacing: -0.02em;
        margin: 0 0 0.75rem;
      }
      .lede {
        font-size: 1.125rem;
        color: var(--ink-soft);
        margin: 0 0 1rem;
        max-width: 40rem;
      }
      .meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem 1.25rem;
        align-items: center;
        font-size: 0.9rem;
      }
      .meta a {
        color: var(--accent);
        font-weight: 600;
        text-decoration: none;
      }
      .meta a:hover {
        text-decoration: underline;
        text-underline-offset: 3px;
      }
      .badge {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        background: var(--bg-elevated);
        border: 1px solid var(--line);
        color: var(--ink);
        font-weight: 500;
        font-size: 0.85rem;
      }
      section {
        margin-bottom: 2.25rem;
      }
      h2 {
        font-family: var(--font-display);
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--ink);
        letter-spacing: -0.02em;
        margin: 0 0 1rem;
        padding-top: 0.5rem;
      }
      h3 {
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--ink);
        margin: 1.5rem 0 0.65rem;
      }
      p {
        margin: 0 0 1rem;
      }
      ul,
      ol {
        margin: 0 0 1rem;
        padding-left: 1.35rem;
      }
      li {
        margin-bottom: 0.4rem;
      }
      strong {
        color: var(--ink);
        font-weight: 600;
      }
      a {
        color: var(--accent);
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 0 0 1.25rem;
        font-size: 0.95rem;
        background: var(--bg-elevated);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        overflow: hidden;
      }
      th,
      td {
        padding: 0.65rem 0.85rem;
        text-align: left;
        border-bottom: 1px solid var(--line);
        vertical-align: top;
      }
      th {
        background: rgba(28, 27, 25, 0.04);
        color: var(--ink);
        font-weight: 600;
      }
      tr:last-child td {
        border-bottom: none;
      }
      pre {
        margin: 0 0 1.25rem;
        padding: 1rem 1.15rem;
        background: #1c1b19;
        color: #e8e4dc;
        border-radius: var(--radius);
        font-size: 0.8rem;
        line-height: 1.5;
        overflow-x: auto;
        white-space: pre;
      }
      code {
        font-family: ui-monospace, 'SF Mono', Menlo, monospace;
        font-size: 0.88em;
        background: rgba(28, 27, 25, 0.06);
        padding: 0.15em 0.4em;
        border-radius: 4px;
        color: var(--ink);
      }
      pre code {
        background: none;
        padding: 0;
        color: inherit;
        font-size: inherit;
      }
      .tags {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        list-style: none;
        padding: 0;
        margin: 0;
      }
      .tags li {
        margin: 0;
        padding: 0.4rem 0.75rem;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: var(--bg-elevated);
        font-size: 0.85rem;
        color: var(--ink);
      }
      .impact-grid {
        display: grid;
        gap: 0.75rem;
      }
      @media (min-width: 540px) {
        .impact-grid {
          grid-template-columns: 1fr 1fr;
        }
      }
      .impact-card {
        padding: 1rem 1.1rem;
        background: var(--bg-elevated);
        border: 1px solid var(--line);
        border-radius: var(--radius);
      }
      .impact-card strong {
        display: block;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--ink-soft);
        margin-bottom: 0.25rem;
      }
      .impact-card span {
        font-family: var(--font-display);
        font-size: 1.15rem;
        color: var(--ink);
      }
      footer {
        margin-top: 3rem;
        padding-top: 1.5rem;
        border-top: 1px solid var(--line);
        font-size: 0.9rem;
      }
    </style>
  </head>
  <body>
    <article class="doc">
      <header>
        <h1>Babu Ceramics Agent</h1>
        <p class="lede">
          Routing workflow assistant for a ceramics shop’s customer email.
        </p>
        <div class="meta">
          <span class="badge">2025</span>
          <a
            href="https://github.com/hbeanss009/BabuCeramicsAgent"
            target="_blank"
            rel="noreferrer"
            >github.com/hbeanss009/BabuCeramicsAgent</a
          >
        </div>
      </header>
      <section id="inspiration">
        <h2>Inspiration</h2>
        <p>
          Small ceramics businesses get repetitive customer emails—catalog
          questions, style recommendations, shipping, returns, and custom
          commissions. Babu Ceramics needed replies that sound like Olivia, use
          real catalog data, and know when a human must step in—not a black-box
          agent that guesses prices or policies.
        </p>
      </section>
      <section id="problem">
        <h2>Problem</h2>
        <p>
          Olivia was spending significant time drafting and reviewing email
          replies. The work is <strong>repeatable and well-defined</strong>, but
          still needs <strong>brand voice</strong>,
          <strong>accurate structured data</strong>, and
          <strong>human judgment</strong> on shipping, returns, and custom
          orders.
        </p>
        <p>
          <strong>Goal:</strong> Cut manual effort (~<strong>3 hrs/week</strong>
          target) without sacrificing trust, tone, or correctness.
        </p>
      </section>
      <section id="product-decision">
        <h2>Product decision: routing workflow, not a pure agent</h2>
        <table>
          <thead>
            <tr>
              <th>Approach</th>
              <th>Why not default here</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Fully autonomous agent</td>
              <td>
                Higher latency/cost, harder to debug, overkill for a predictable
                intent taxonomy
              </td>
            </tr>
            <tr>
              <td>Single mega-prompt</td>
              <td>Weak tool control, hallucination risk on SKUs/prices</td>
            </tr>
            <tr>
              <td>Heavy agent framework</td>
              <td>
                Abstractions hide failure modes; harder to justify each step
              </td>
            </tr>
          </tbody>
        </table>
        <p>
          <strong>Choice:</strong> A <strong>routing agentic workflow</strong>—Python
          orchestrates the flow; the LLM runs only at defined steps:
        </p>
        <pre><code>Fixed Python orchestration
        │
        ├── [LLM] classify intent
        ├── Fixed routing logic
        ├── [LLM] extract entities (e.g. item name)
        ├── Fixed Supabase query / tool execution
        └── [LLM] write reply in Olivia's voice</code></pre>
        <p>
          <strong>Tradeoff:</strong> Balance <strong>latency, cost, and task performance</strong>
          for async email (~10–15 conversations/month), not chat-style instant
          replies.
        </p>
      </section>
      <section id="overview">
        <h2>Overview</h2>
        <p>
          <strong>Babu Ceramics Agent</strong> classifies inbound customer
          messages, routes them to specialized handlers, and uses Claude
          tool-calling where structured data is required. The server stays
          <strong>stateless</strong>; Supabase holds conversations, catalog,
          and shop knowledge. Email is ingested via
          <strong>IMAP polling</strong>; production LLM calls are traced in
          <strong>Helicone</strong>.
        </p>
        <h3>High-level flow</h3>
        <pre><code>Customer email (IMAP, ~30 min poll)
    → run_router() — intent classifier + fallback
        → item_inquiry   → tool loop (catalog, price, details, collections)
        → recommendation → grounded LLM + Supabase catalog + editorial context
        → orders         → sub-router → shipping / returns / custom / status tools
    → human-review gate on incomplete high-stakes flows
    → customer reply OR notify Olivia (no auto-send)</code></pre>
      </section>
      <section id="features">
        <h2>Features</h2>
        <ul>
          <li>
            <strong>Multi-intent routing</strong> with LLM classifier + keyword
            fallback on API failure
          </li>
          <li>
            <strong>Eight custom tools</strong> with rich schemas and
            <code>input_examples</code> (no tool-search; &lt;10 tools)
          </li>
          <li>
            <strong>Anthropic SDK directly</strong>—no LangChain; manual tool
            definitions for trace/eval visibility
          </li>
          <li>
            <strong>Supabase</strong> for catalog, conversations (~3-month
            retention), and unstructured shop guides
          </li>
          <li>
            <strong>No RAG</strong> for ~3.5k tokens of stable content—fetched
            upfront as context
          </li>
          <li>
            <strong>Full-catalog recommendations</strong> for &lt;20 SKUs—no vector
            DB
          </li>
          <li>
            <strong>Human-in-the-loop</strong> via
            <code>needs_human_review</code> on shipping/returns/custom flows
          </li>
          <li>
            <strong>Conversation memory</strong> in Supabase (decoupled from Gmail
            <code>thread_id</code> via <code>[ref: …]</code> in subject)
          </li>
          <li>
            <strong>Line-by-line prompting</strong> over paragraph blocks for
            clearer tool and routing behavior
          </li>
          <li>
            <strong>Claude Sonnet</strong> default—asks clarifying questions
            instead of assuming on customer email
          </li>
        </ul>
      </section>
      <section id="examples">
        <h2>Example capabilities</h2>
        <table>
          <thead>
            <tr>
              <th>User question</th>
              <th>Route</th>
              <th>Behavior</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>“What collections do you have?”</td>
              <td><code>item_inquiry</code></td>
              <td><code>view_collection</code></td>
            </tr>
            <tr>
              <td>“Show items in the Dot collection”</td>
              <td><code>item_inquiry</code></td>
              <td><code>view_catalog_items</code></td>
            </tr>
            <tr>
              <td>“Price of the pasta bowl?”</td>
              <td><code>item_inquiry</code></td>
              <td><code>get_item_price</code></td>
            </tr>
            <tr>
              <td>“Newlyweds—suggest pottery for our home”</td>
              <td><code>recommendation</code></td>
              <td>Catalog + editorial/collection context</td>
            </tr>
            <tr>
              <td>“Custom order with initials on a potpourri bowl”</td>
              <td><code>orders</code></td>
              <td>
                <code>custom_order_enquiry</code> → may escalate to human review
              </td>
            </tr>
            <tr>
              <td>“Return policy on opened items?”</td>
              <td><code>orders</code></td>
              <td><code>returns_enquiry</code></td>
            </tr>
            <tr>
              <td>“Shipping cost for 4 bowls to 95125”</td>
              <td><code>orders</code></td>
              <td><code>shipping_enquiry</code></td>
            </tr>
          </tbody>
        </table>
      </section>
      <section id="architecture">
        <h2>Architecture decisions</h2>
        <h3>Stateless backend + Supabase</h3>
        <p>
          DB access only through a translator module (<code>generate_thread_id</code>,
          <code>create_conversation</code>, <code>get_conversation</code>,
          <code>update_messages</code>). No scattered queries.
        </p>
        <h3>Email: IMAP polling (30 min)</h3>
        <p>
          Email doesn’t need push latency. <strong>IMAP + imaplib</strong> avoids
          Google Cloud OAuth for a side project;
          <strong>30-min poll</strong> fits low traffic and feels more human than
          instant bot replies.
        </p>
        <h3>Human review on high-stakes tools</h3>
        <p>
          Tools return <code>{complete, message}</code> → normalized to
          <code>needs_human_review</code>. If true: update DB, email Olivia,
          <strong>no</strong> customer auto-reply.
        </p>
        <h3>Unstructured knowledge without RAG</h3>
        <p>
          Collection stories, care guides, artist notes, FAQs, editorial picks
          (~3.5k tokens, rarely changing) are passed as context—not vector search.
        </p>
        <h3>Observability (Helicone)</h3>
        <p>
          Multiple Claude calls per email (intent, tools, synthesis). Helicone
          instruments all calls with headers for
          <strong>handler, intent, thread</strong>—no refactor across handlers.
        </p>
      </section>
      <section id="evals">
        <h2>Evals</h2>
        <p>
          Evaluation was a <strong>must-have</strong> before treating replies as
          shippable. The system makes several Claude calls per request; without
          structured checks, production issues would be guesswork.
        </p>
        <h3>1. Foundation testing (integration)</h3>
        <p>Before agent evals, validated Supabase plumbing in isolation:</p>
        <ul>
          <li>Does <code>generate_thread_id</code> produce a valid UUID?</li>
          <li>Can we write conversations to Supabase?</li>
          <li>Can we read back what we wrote?</li>
        </ul>
        <p>
          Separate Python test functions, run individually, results confirmed in
          the Supabase UI.
        </p>
        <h3>2. Golden dataset + manual labeling</h3>
        <ul>
          <li>Built an initial set of <strong>~50 questions</strong>; ran each through the agent.</li>
          <li>Exported traces to <strong>CSV</strong>; <strong>manually labeled</strong> each output on the dimensions that mattered.</li>
          <li>
            Used <strong>spreadsheet rules</strong> to check human-review behavior:
            <ul>
              <li><strong>(a)</strong> Accurately flagged (or not flagged) for human review</li>
              <li><strong>(b)</strong> Handoff included the information Olivia needs before she replies</li>
            </ul>
          </li>
        </ul>
        <h3>3. Code-based evals (automated, repeatable)</h3>
        <table>
          <thead>
            <tr>
              <th>Dimension</th>
              <th>What it checks</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Routing accuracy</strong></td>
              <td>
                Correct route handler (<code>item_inquiry</code>,
                <code>recommendation</code>, <code>orders</code>)
              </td>
            </tr>
            <tr>
              <td><strong>Factual accuracy</strong></td>
              <td>
                Correct price, material, dimensions for named items (structured
                data)
              </td>
            </tr>
            <tr>
              <td><strong>Human-review escalation</strong></td>
              <td>
                Correct flag / no-flag on shipping, returns, custom-order flows
              </td>
            </tr>
          </tbody>
        </table>
        <p>
          These are the evals that <strong>scale in scripts</strong>—rerun on every
          prompt or routing change without re-labeling everything by hand.
        </p>
        <h3>4. LLM-as-judge evals (subjective quality)</h3>
        <table>
          <thead>
            <tr>
              <th>Dimension</th>
              <th>What it checks</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Tone accuracy</strong></td>
              <td>Matches Olivia’s voice</td>
            </tr>
            <tr>
              <td><strong>Completeness</strong></td>
              <td>Answers the question without dropping key details</td>
            </tr>
            <tr>
              <td><strong>Clarifying-question quality</strong></td>
              <td>One focused question when needed; doesn’t over-ask</td>
            </tr>
            <tr>
              <td><strong>Recommendation quality</strong></td>
              <td>Grounded, occasion/style-aware picks</td>
            </tr>
          </tbody>
        </table>
        <h3>5. LLM-judge workflow</h3>
        <ol>
          <li>
            <strong>Build golden test set</strong> — hand-picked queries covering key
            scenarios (start ~10 per slice; grew toward ~50).
          </li>
          <li>
            <strong>Generate agent outputs</strong> — run each query through
            <code>run_router()</code> (scripted batch or form).
          </li>
          <li>
            <strong>Run LLM judge</strong> — <code>run_eval.py</code> +
            <code>llm_judge.py</code>: Claude scores each response
            <strong>good / average / bad</strong> per criterion.
          </li>
          <li>
            <strong>Compare with human labels</strong> — agreement rate between
            manual labels and the judge.
          </li>
          <li>
            <strong>Iterate</strong> — low agreement → fix judge prompt; high
            agreement → trust judge and improve system prompts; rerun and check
            score movement.
          </li>
        </ol>
        <h3>6. Scaling evals going forward</h3>
        <ul>
          <li>
            <strong>Code-based</strong> (routing, facts, escalation) → repeatable
            scripts after router/tool/schema changes.
          </li>
          <li>
            <strong>LLM-judge</strong> (tone, completeness, rec quality) → calibrate
            against human labels before trusting automation.
          </li>
          <li>
            <strong>Dogfooding &amp; real-world testing</strong> before wider rollout.
          </li>
          <li>
            <strong>Synthetic inputs at scale</strong> — define
            <strong>dimensions</strong> (query type, collection, occasion, intent)
            for diverse edge-case coverage.
          </li>
          <li>
            <strong>Qualitative synthesis</strong> —
            <strong>open codes</strong> on failure notes, then
            <strong>axial coding</strong> into themes (vague recs, missing item names,
            wrong escalation).
          </li>
        </ul>
        <h3>7. What evals proved before prod</h3>
        <ul>
          <li>Routing and tool paths behave predictably on labeled sets</li>
          <li>Human-review gates fire when policy data is incomplete</li>
          <li>Subjective quality is measurable via judge + human agreement</li>
          <li>Supabase conversation layer works end-to-end for follow-up threads</li>
        </ul>
      </section>
      <section id="impact">
        <h2>Impact</h2>
        <div class="impact-grid">
          <div class="impact-card">
            <strong>Owner time saved</strong>
            <span>~3 hrs/week</span>
          </div>
          <div class="impact-card">
            <strong>Intent routing</strong>
            <span>90%+ accuracy</span>
          </div>
          <div class="impact-card">
            <strong>Traffic fit</strong>
            <span>10–15 convos/mo</span>
          </div>
          <div class="impact-card">
            <strong>Risk control</strong>
            <span>Human-review gate</span>
          </div>
        </div>
      </section>
      <section id="tech-stack">
        <h2>Tech stack</h2>
        <table>
          <thead>
            <tr>
              <th>Layer</th>
              <th>Choice</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>LLM</td>
              <td>Anthropic Claude (Sonnet default)</td>
            </tr>
            <tr>
              <td>SDK</td>
              <td>Anthropic Python SDK (no LangChain)</td>
            </tr>
            <tr>
              <td>Data</td>
              <td>Supabase (catalog, conversations, guides)</td>
            </tr>
            <tr>
              <td>Email</td>
              <td>IMAP polling + SMTP; <code>gmail_listener.py</code></td>
            </tr>
            <tr>
              <td>Observability</td>
              <td>Helicone (production traces)</td>
            </tr>
            <tr>
              <td>Evals</td>
              <td>Code-based checks + LLM-as-judge + golden CSV</td>
            </tr>
            <tr>
              <td>Runtime</td>
              <td>Python 3, <code>python-dotenv</code></td>
            </tr>
          </tbody>
        </table>
      </section>
      <section id="reviewer">
        <h2>What I’d tell a technical reviewer</h2>
        <ol>
          <li>
            <strong>Why routing, not a pure agent?</strong> Predictable intents; cost/latency;
            evaluable steps.
          </li>
          <li>
            <strong>Why no LangChain?</strong> Scope, learning, and debug clarity on a
            first multi-route build.
          </li>
          <li>
            <strong>Why no RAG?</strong> Small, stable context; full pass is cheaper and
            simpler.
          </li>
          <li>
            <strong>Why human review?</strong> Shipping/returns/custom orders are
            incomplete-by-design without order details.
          </li>
          <li>
            <strong>Why IMAP + 30 min?</strong> Email channel; low volume; human-like
            pacing.
          </li>
          <li>
            <strong>How do you know it works?</strong> Foundation DB tests + ~50-query
            golden set + code evals + calibrated LLM judge + thematic failure coding.
          </li>
        </ol>
      </section>
      <section id="tags">
        <h2>Tags</h2>
        <ul class="tags">
          <li>AI Agents</li>
          <li>Routing Workflows</li>
          <li>Tool Calling</li>
          <li>Code-based Evals</li>
          <li>LLM-as-Judge</li>
          <li>Observability</li>
          <li>Supabase</li>
          <li>Python</li>
        </ul>
      </section>
      <footer>
        <p>
          Harini Rao · Portfolio project doc ·
          <a
            href="https://github.com/hbeanss009/BabuCeramicsAgent"
            target="_blank"
            rel="noreferrer"
            >View repository</a
          >
        </p>
      </footer>
    </article>
  </body>
</html>
