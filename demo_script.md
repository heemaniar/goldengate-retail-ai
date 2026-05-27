# MallPulse — Demo Video Script
# Target length: 2:30 – 3:00 minutes
# Record at: https://mallpulse-3f3swnt3qq-uc.a.run.app
# Tool: Loom (free), QuickTime + screen capture, or OBS

---

## SETUP BEFORE RECORDING

- [ ] Browser open to https://mallpulse-3f3swnt3qq-uc.a.run.app
- [ ] Clear the conversation (click "🗑️ Clear conversation" in sidebar)
- [ ] Enable the Looker Studio dashboard toggle in the sidebar
- [ ] Use a 1280×720 or 1920×1080 window — not fullscreen (so sidebar is visible)
- [ ] Close Slack, email, other notifications
- [ ] Do a dry run first — confirm all 5 questions return good answers

---

## SCRIPT

### [0:00 – 0:20] Hook

> *"Shopping mall managers in Istanbul oversee hundreds of tenants and millions of
> square feet of retail space — but most still rely on weekly Excel reports.
> By the time a problem shows up in a spreadsheet, it's already too late to act.
> MallPulse changes that."*

**[Show]** The MallPulse app loading. Scroll the sidebar to show the example questions.

---

### [0:20 – 0:40] Architecture in one sentence

> *"MallPulse is a four-agent AI system built on Google ADK and Gemini 2.5 Flash.
> A root orchestrator routes every question to one of three specialist agents —
> a Data Unifier, a Tenant Diagnoser, and an Action Recommender — each
> backed by a live BigQuery warehouse synced via Fivetran."*

**[Show]** Sidebar — highlight the "About" caption. Don't dwell; keep moving.

---

### [0:40 – 1:05] Demo question 1 — Revenue

**Type:** `How many transactions did Kanyon have in March 2023?`

> *"I'll start with the simplest question a GM asks every Monday morning."*

**[Wait for answer — ~5s]**

> *"208 transactions. The agent wrote the SQL, ran it against BigQuery,
> and returned the number — no manual query, no dashboard refresh."*

---

### [1:05 – 1:35] Demo question 2 — Tenant diagnosis

**Type:** `Which tenants at Kanyon have leases expiring in the next 6 months?`

> *"Now something harder — lease risk. This is where the Tenant Diagnoser
> takes over."*

**[Wait for answer — ~8s]**

> *"The agent returns a risk-flagged list with rent-to-sales ratios.
> Notice the 🔴 Critical and 🟡 Watch flags — the agent isn't just
> returning data, it's interpreting it against industry benchmarks."*

---

### [1:35 – 2:00] Demo question 3 — Fivetran pipeline (track highlight)

**Type:** `Is the Fivetran data pipeline healthy?`

> *"MallPulse is entered in the Fivetran track. The Data Unifier agent
> connects to Fivetran's API via the official MCP server — right inside
> the conversation."*

**[Wait for answer — ~6s]**

> *"Last sync time, connector state, schema config — all retrieved live
> from Fivetran, not cached. The GM knows their data is fresh before
> they trust any number."*

---

### [2:00 – 2:25] Demo question 4 — Forecast + actions

**Type:** `What are the top 3 actions I should take this week at Kanyon?`

> *"The Action Recommender pulls forecasts from BigQuery ML's ARIMA_PLUS
> model, combines them with tenant diagnosis, and returns a prioritised
> action list — with data evidence for every recommendation."*

**[Wait for answer — ~10s]**

> *"Immediate actions this week. Short-term for the next quarter.
> Every item cites the revenue figure or ratio that drives it."*

---

### [2:25 – 2:45] Dashboard

**[Click "Show Looker Studio dashboard" toggle in sidebar]**

> *"And for the visual layer — a Looker Studio dashboard embedded
> directly in the app. Revenue trends from BigQuery's aggregated tables,
> top tenants by total revenue, all live."*

---

### [2:45 – 3:00] Close

> *"MallPulse is live on Cloud Run — the link is in the Devpost
> description. The full source is on GitHub with a one-command deploy
> script. Thank you."*

**[Show]** The Cloud Run URL in the browser address bar as the final frame.

---

## TIPS

- Speak at a measured pace — judges watch these at 1.5× speed
- If an answer is slow, say "while the agent queries BigQuery..." to fill time naturally
- Don't apologise for load time — it's a live agent, not a mock
- If a question fails, skip it cleanly and move to the next one
- Keep the cursor still when the agent is thinking — don't scroll nervously

---

## AFTER RECORDING

1. Upload to YouTube (unlisted) or Loom
2. Copy the share URL
3. Paste it into `devpost_submission.md` where it says `[PASTE VIDEO URL HERE]`
4. Add the same URL to the Devpost form "Demo Video" field
