# Kampung Grid

**SGSecure finds the helpers. Kampung Grid finds who needs help.**
An AI system that helps neighbours look after each other in a crisis, keeps working when the grid fails,
and shows authorities how fast each block can reach its most vulnerable residents.

SIMYEN Hackathon 2026 · AI & Security. All residents in this project are fictional.

## What's in here

```
backend/    Python (FastAPI) server: data, live updates, Claude calls
  app/        main.py (routes), models.py (tables), live.py (WebSockets), ai.py (Claude)
  seed/       block123.json: the fictional demo blocks (edit freely)
  tests/      messages.json: messy-message test set; test_parse.py scores it
frontend/   React app: /dashboard, /control, /phone
docs/       api.md: the agreed API (change it before changing a route)
```

## Project structure and runtime files

The app runs as two cooperating processes: the Python backend serves data and AI features, while
the React frontend provides the browser screens. The frontend sends API and WebSocket requests
through the Vite development server to the backend.

```text
.
|-- .gitignore
|-- README.md
|-- start.bat                     Windows setup and launcher
|-- start.sh                      macOS/Linux setup and launcher
|-- docs/
|   `-- api.md                    Shared API contract
|-- backend/
|   |-- requirements.txt          Python runtime dependencies
|   |-- .env.example              Safe template; copy to the ignored .env for local secrets/settings
|   |-- ai_cache.json             Saved AI answers for offline/rehearsal fallback
|   |-- app/
|   |   |-- __init__.py
|   |   |-- main.py               FastAPI entry point, routes, and startup lifecycle
|   |   |-- ai.py                 Claude calls, prompt handling, and cached/fallback answers
|   |   |-- db.py                 SQLite connection and table setup
|   |   |-- models.py             Database and API data models
|   |   |-- live.py               WebSocket updates
|   |   |-- authority.py          Authority access logic
|   |   |-- briefing.py           Incident briefings and after-action summaries
|   |   |-- crisis.py             Crisis workflow and task coordination
|   |   |-- keys.py               Local encryption key handling
|   |   |-- messaging.py          Message/report processing
|   |   |-- people.py             Resident and helper data operations
|   |   |-- risk.py               Risk assessment
|   |   |-- rumours.py            Rumour detection and handling
|   |   |-- silence.py            Silence-alert workflow
|   |   |-- sim.py                Scenario simulation and what-if calculations
|   |   |-- telegram_bot.py       Optional Telegram integration
|   |   |-- trust.py              Report trust checks
|   |   |-- vault.py              Protected profile and unlock operations
|   |   `-- voice.py              Optional voice-note transcription
|   |-- seed/
|   |   |-- __init__.py
|   |   |-- seed.py               Loads demo data into SQLite
|   |   |-- block123.json         Fictional sample block/resident data
|   |   `-- README.md             Seed-data notes
|   |-- sim/
|   |   `-- assumptions.yaml      Simulation assumptions
|   `-- tests/
|       |-- messages.json         AI/report parsing test fixtures
|       |-- test_crisis.py
|       |-- test_parse.py
|       |-- test_sim.py
|       |-- test_trust.py
|       |-- test_vault.py
|       |-- test_week5.py
|       `-- test_week6.py
|-- frontend/
|   |-- package.json              Frontend dependencies and scripts
|   |-- package-lock.json          Locked npm dependency versions
|   |-- README.md
|   |-- .gitignore
|   |-- index.html                 Browser entry document
|   |-- vite.config.ts             Vite, React/Tailwind plugins, and backend proxy
|   |-- tsconfig.json              TypeScript project configuration
|   |-- tsconfig.app.json          Browser app TypeScript configuration
|   |-- tsconfig.node.json         Vite config TypeScript configuration
|   |-- .oxlintrc.json             Linter configuration
|   |-- public/
|   |   `-- favicon.svg
|   `-- src/
|       |-- main.tsx               React entry point
|       |-- App.tsx                Routes and application shell
|       |-- index.css              Global styles
|       |-- lib/api.ts             Shared API/WebSocket client and frontend types
|       |-- components/
|       |   |-- Block125Card.tsx
|       |   |-- BlockView.tsx
|       |   |-- BriefPanels.tsx
|       |   |-- ConnectionDot.tsx
|       |   |-- ReportFeed.tsx
|       |   |-- SilencePanel.tsx
|       |   |-- TTLKPanel.tsx
|       |   `-- UnlockLog.tsx
|       `-- pages/
|           |-- Control.tsx
|           |-- Dashboard.tsx
|           |-- Join.tsx
|           |-- Phone.tsx
|           `-- PrintCard.tsx
```

### What must exist to run it

- **Required source/config:** `backend/app/`, `backend/seed/`, `backend/requirements.txt`,
  `frontend/src/`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/index.html`,
  `frontend/vite.config.ts`, and the TypeScript config files.
- **Local setup, created once:** `backend/.venv/` (Python packages) and `frontend/node_modules/`
  (npm packages). Recreate them with the setup steps below if missing.
- **Local settings:** `backend/.env` is optional for basic operation and must stay private.
  Add `ANTHROPIC_API_KEY` there to enable Claude; the backend has a fallback without it.
- **Runtime data:** `backend/kampung.db` and `backend/.keys/` are created/used by the backend.
  The seed command supplies the fictional demo data. `backend/ai_cache.json` holds saved answers
  for offline/rehearsal use.
- **AI entry point:** there is no separate model-weight file in this project. Claude is called
  by `backend/app/ai.py` when configured; the surrounding crisis and simulation logic is local code.

## Quick start

You need **Python 3.11+** and **Node.js 20+** installed. Then:

- **Windows:** if `start.bat` is present, run `.\start.bat` from PowerShell in the project folder.
  If it is missing, use the two-terminal instructions under [Running it by hand](#running-it-by-hand-every-time).
- **Mac / Linux:** run `./start.sh` from the project folder.

The first run sets everything up (a few minutes); after that it starts in seconds and opens your browser
at http://localhost:5173. To use Claude, put your API key in `backend/.env` before starting the backend.

To stop a manual run, press **Ctrl+C** in each terminal.

The manual steps below do the same thing, if you prefer to see each one.

## First-time setup by hand (each teammate, once)

You need **Python 3.11+**, **Node.js 20+** and **Git**.

### Windows (PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Optional: edit .env and set ANTHROPIC_API_KEY to enable Claude
python -m seed.seed                # loads Block 123 and Block 125
```

Then install frontend packages once:

```powershell
cd ..\frontend
npm install
```

### macOS / Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
# Optional: edit .env and set ANTHROPIC_API_KEY to enable Claude
python -m seed.seed

cd ../frontend
npm install
```

## Running it by hand (every time)

Run these from the project folder in **two separate terminals**. On Windows, use PowerShell:

**Terminal 1 — backend (PowerShell):**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend (PowerShell):**

```powershell
cd frontend
npm run dev -- --open
```

For **macOS / Linux**, activate the backend environment with `source .venv/bin/activate` instead:

```bash
# Terminal 1
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
cd frontend
npm run dev -- --open
```

The frontend opens the app in your browser. If it does not, open http://localhost:5173 manually.
To stop the app, press **Ctrl+C** in both terminals. Available pages:

| Screen | Address |
| --- | --- |
| Home (links to everything) | http://localhost:5173 |
| Authority dashboard | http://localhost:5173/dashboard |
| Demo control panel | http://localhost:5173/control |
| Phone app | http://localhost:5173/phone |
| API test page | http://localhost:8000/docs |

**On a phone:** connect it to the same Wi-Fi (or the laptop's hotspot), then scan the **QR code on the
control panel**. It always shows the laptop's network address, e.g. `http://192.168.1.23:5173/phone`.

## Check it works (Week 1 milestone)

1. Open the dashboard on the laptop and `/phone/meiling` on a phone.
2. On `/control`, press **Start evening**: the dashboard turns green ("Normal evening") straight away.
3. On the phone, tap **Report something**, type `Eh the auntie at 9-12 never open door, got smell leh`, and send.
   The phone says "Sent" instantly; a moment later it shows what the AI understood.
4. The report appears on the dashboard straight away ("AI reading..."), then fills in, matched to
   **#09-12 (Mdm Tan)**, with her unit highlighted.
5. Try a name with no unit: `Mdm Wong never answer phone whole day`. It's matched to **#12-02**.
6. Open `/phone/lim` (Mr Lim, opted in to Silence Alert) and tap **I'm okay today**.
7. Refresh the control panel: the steps you've done stay ticked. Press **Reset demo** to start again.

## Run the Week 2 demo

1. Open the dashboard on the laptop, and **`/phone/aziz`** on a phone (or a narrow browser window).
2. On the control panel press, in order: **Start evening → Cyberattack → Voice note arrives → Assign helper**.
3. The dashboard turns red, ranks **Mdm Tan #1** with her reasons, and draws a line from each helper to the
   person they're checking on. Aziz's phone buzzes (Android) and shows the task card in Malay.
4. On Aziz's phone tap **On my way**, then **Reached**. Mdm Tan's unit turns green and the dashboard shows
   **"Mdm Tan reached. No one in the block gets forgotten."**
5. The other helpers are **simulated neighbours** (labelled on the dashboard): they respond by themselves over the
   next 20 to 45 seconds. Only Aziz waits for a real tap.

**Timing:** Aziz (the real phone) has **5 minutes** to tap **On my way** before his task moves to the next-best
helper; simulated neighbours have 90 seconds. Change these with `KG_FEATURED_ESCALATE_SECONDS` and
`KG_ESCALATE_SECONDS` in `backend/.env`. No phone? Press **Mdm Tan reached** on the control panel instead.

**Every start is a fresh demo.** Restarting the app (`bash start.sh`) resets everything, and the start script
stops any old copy that's still running first. **Reset demo** on the control panel does the same without restarting.

## Run the Week 3 demo (defence)

Do the Week 2 steps (1 → 4), then:

1. On Aziz's phone, his task card shows **Mdm Tan's Sealed Profile**: two keys turn green ("Incident declared",
   "Assigned to you") and only the need-to-know details appear. The dashboard's **unlock log** records it.
2. Press **6 · Fake report + rumour** on the control panel:
   - A fake "14-03 collapsed!" report from an unknown number appears with **Low trust: unknown sender ·
     no second report · unit #14-03 is vacant**. No helper is sent. Press **Reject as fake**.
   - Three neighbours say the tap water is contaminated: a **Rumour spreading** card appears. Press
     **Approve and send via neighbours**. Every phone shows the verified answer "from your neighbour ...".

**How Sealed Profiles work:** each profile is encrypted with its own key, split in two halves. One half is locked by
the authority's incident key (only released during a declared incident), the other by the system key. The keys live
in `backend/.keys/` (created on first run; never commit or share them). `seed/block123.json` stands in for what an RC
volunteer enters: it is sealed the moment it's loaded, so the database never holds it in plain text.
Prove it: `python -m pytest -q tests/test_vault.py` (includes the "stolen database" test).

## Run the Week 4 demo (governance)

1. **Before the crisis**, after **Start evening**: the dashboard shows **Time to Last Knock** for Block 123:
   typical and bad-night minutes at 7pm and 3am, the 24-hour strip (drag the slider), and the **biggest gap**
   (no trained first-aider home on floors 10 to 14 at night).
2. Run beats 2 → 6 as before. On Priya's phone (`/phone/priya`, the nurse) the family card shows her father at
   #11-04 being checked by a neighbour, then "You can report for duty".
3. **7 · Block 125 in trouble**: nobody is home to help there. Press **Reallocate: send SCDF Team B** on its card;
   the team reaches everyone over the next 30 seconds.
4. **8 · SCDF arrives**: the handover brief appears, **NOT REACHED** first. (Mr Rajan's neighbour never answers
   on purpose, so someone is still unreached: set `KG_SIM_NO_RESPONSE=` in `.env` to change that.)
5. Tap **Reached** on Aziz's phone, then **10 · After-action report**: the report, then the Time to Last Knock panel.
   Press **What if?** and pick the top option: 3am counts down to the new time.

**Where the numbers come from:** `backend/sim/assumptions.yaml` holds every guess (stair speed, reaction times,
answer chances). Click **Assumptions** on the panel to show them. After the mini-wargame, replace guesses with
measured numbers. The simulation only uses *where* vulnerable residents live, never their Sealed Profiles.

## Run the Week 5 demo (resilience)

1. Run beats 1 → 4 with Aziz's phone open (`/phone/aziz`).
2. **5 · Network down**: the dashboard says "Low data: SMS" and Aziz's task turns into a text message.
   Tap **Reply 1 · reached** or **Reply 2 · need help**, like replying to a real SMS.
3. On the control panel, **Network mode** buttons switch between all four modes (for the Q&A "what if there's no signal?"):
   - **Relay**: the dashboard draws the message hopping phone to phone up the stairwell. It's labelled *simulated*.
   - **No phones**: every phone says to use the block card; open it from the control panel or `/print/block/123`
     and press **Print**. Unit numbers only: no names, no medical details.
4. **Silence Alert** (any time): press **Mr Lim hasn't checked in for 2 days**. Mr Lim turns amber on the dashboard.
   Press **Approve next step** → Mei Ling's phone (`/phone/meiling`) asks her to knock → **He's okay** closes it.
   Nothing moves up the ladder unless a person approves it. On any other resident's phone, try
   **Haven't seen a neighbour lately?**
5. **Voice notes** (optional): `backend/.venv/bin/pip install faster-whisper`, restart, then on the laptop open a
   phone page, tap **Report something** and hold the 🎤 button. The first note downloads the model once
   (a few hundred MB). Phones over Wi-Fi need an https link for the microphone, so demo this on the laptop.

## Week 6: judges join from their own phones

**QR join (always on).** The control panel's QR code opens `/join`. A judge ticks the consent box, picks a
helper to play (Kavitha, Benjamin, Mei Ling or Ryan), and chooses Telegram or "Stay on this web page".
Whoever joins is a real person, never simulated: their task waits for them to tap. **Reset** lets everyone go.

**Telegram bot (optional, about 3 minutes):**
1. In Telegram, search **@BotFather** (blue tick), send `/newbot`, give it a name (e.g. `Kampung Grid Demo`)
   and a username ending in `bot` (e.g. `kampunggrid_demo_bot`).
2. BotFather replies with a **token**. Treat it like your API key: never paste it in chats, slides or GitHub.
3. Put it in `backend/.env` (NOT `.env.example`): `KG_TELEGRAM_TOKEN=<the token>`
4. Restart (`bash start.sh`). The terminal says `[telegram] on: https://t.me/<your bot>`, and the control
   panel says "Telegram bot: on". The join page now shows a blue **Telegram** button.

**Mobile data (optional): a free public https link.** Without it, judges must be on the same Wi-Fi as the laptop.
1. Install once: `brew install cloudflared`
2. While the app is running, in a second terminal: `cloudflared tunnel --url http://localhost:5173`
3. Copy the `https://....trycloudflare.com` link it prints and paste it into the box under the QR code
   on the control panel. The QR code now works on any phone, and phones get https (microphone works too).
   The link changes every time you run the tunnel.

### Practice with friends: "Send a test job"
Friends join (QR code or the bot), then press **Send a test job** on the control panel. Each person who joined
gets the job nearest to their unit straight away, no beats needed. Mdm Tan is always left for Aziz.

### If the venue internet fails: backup answers
Every good answer from Claude is saved to `backend/ai_cache.json`. If Claude can't be reached later, the
**same question gets the saved answer**, so the demo looks the same. The control panel shows how many are saved.
1. **Rehearse the full demo once with internet** the day before. That fills the file.
2. If the venue internet is bad, add `KG_AI_OFFLINE=true` to `backend/.env` and restart. The app then answers
   instantly from saved answers only, never waiting on the internet. (Remove the line afterwards.)
3. Anything never rehearsed falls back to the built-in rules, labelled "AI offline".

## Testing the AI

```bash
cd backend
python -m tests.test_parse     # scores Claude on the messy-message test set
python -m pytest -q            # quick automated checks
```

Without an API key, the backend uses a simple rule-based fallback (it scores about 5/12). With Claude it
should score far higher; every result is labelled `"source": "claude"` or `"fallback"`, so we never pass off
a rule as AI. **Add more messages to `tests/messages.json`** (goal: 20+, in Singlish, Mandarin, Malay and Tamil).

## Rules

- **Never commit `.env`** (it holds the API key). It's in `.gitignore`.
- **No real personal data.** Everyone in `seed/block123.json` is made up.
- **The dashboard never shows medical details.** `GET /blocks/{id}` only says whether a unit has a vulnerable resident.
- Update `docs/api.md` before changing a route.

## Build plan

The full plan, with every person's step-by-step jobs, is in the team's Build Plan doc.
- Week 1 (done): server, live updates, seed data, first Claude call, three screens connected.
- Week 2 (done): crisis engine (rank with reasons, match helpers, Claude-written instructions, escalation),
  task card, Mdm Tan reached end to end.
- Week 3 (done): trust check (catches the fake report), two-key Sealed Profiles + unlock log, rumour detection.
- Week 4 (done): Time to Last Knock simulation + what-if, Block 125 reallocation, SCDF handover brief, family cover, after-action report.
- Week 5: network-down modes (SMS view, relay animation), printed block card, voice notes, Silence Alert; the mini-wargame.
