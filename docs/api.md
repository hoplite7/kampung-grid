# Kampung Grid API

The agreed list of what each screen sends to the backend and gets back.
**Change this file before changing a route**, and tell the team.

Screens call everything through the frontend dev server: `/api/<route>` and `/ws`.
The backend itself serves the routes without the `/api` prefix (try them at `http://localhost:8000/docs`).

Status: ✅ working · 🟡 placeholder (answers, but not built yet)

## Routes

| Route | Who calls it | What it does | Status |
| --- | --- | --- | --- |
| `GET /health` | Anyone | `{"ok": true, "scene": "idle"}` | ✅ |
| `GET /state` | Any screen on load | `{scene, done}`: current scene and which control beats have run | ✅ |
| `GET /network` | Control panel | `{ip}`: the laptop's local network address, for the phone QR code | ✅ |
| `POST /checkins` | Phone (opted-in seniors) | `{resident_id}`: "I'm okay today" for Silence Alert | ✅ |
| `GET /blocks/{id}` | Dashboard | Block, units, residents (**no medical details**, only `is_vulnerable`) | ✅ |
| `GET /residents?block_id=123` | Phone picker | Short list of residents | ✅ |
| `GET /residents/{id}` | Phone | That person's home-screen info and role | ✅ |
| `POST /reports` | Phone | Send a report `{text, sender_id}`. Returns **immediately** with `status: "reading"` and `parsed: null`; the AI result arrives as a `report_updated` live message | ✅ |
| `GET /reports?block_id=123` | Dashboard | All reports, newest first | ✅ |
| `GET /incidents/current?block_id=123` | Dashboard | `{incident, ranked, tasks}`: active incident, everyone ranked with reasons, all tasks | ✅ |
| `GET /tasks?helper_id=aziz` | Phone | That helper's tasks, newest first | ✅ |
| `POST /tasks/{id}/status` | Phone | `{status: "on_the_way" \| "reached" \| "need_help"}` | ✅ |
| `POST /control/reset` | Control panel | Wipe and reload seed data | ✅ |
| `POST /control/start-evening` | Control panel | Scene → evening | ✅ |
| `POST /control/cyberattack` | Control panel | Start the incident: power out, lifts down, scene → crisis | ✅ |
| `POST /control/voice-note` | Control panel | The scripted neighbour message about Mdm Tan arrives | ✅ |
| `POST /control/assign-helper` | Control panel | Rank everyone, match helpers, send tasks | ✅ |
| `POST /control/mdm-tan-reached` | Control panel | Mark Mdm Tan reached (if Aziz's phone isn't used) | ✅ |
| `POST /control/network-down` | Control panel | Beat 5: mode → low_data; open tasks re-sent as SMS | ✅ |
| `POST /control/mode` | Control panel | `{mode, block_id}`: full, low_data, relay, no_phone | ✅ |
| `POST /control/silence-demo` | Control panel | Extra: Mr Lim missed 2 days of check-ins + a neighbour tap | ✅ |
| `GET /sim/overview?block_id=123` | Dashboard | Time to Last Knock: 7pm and 3am (median + bad night), 24-hour curve, biggest gap, assumptions | ✅ |
| `POST /sim/what-if` | Dashboard | `{block_id, time}`: top 3 changes ranked by minutes saved + a plain-English summary | ✅ |
| `POST /responders/reallocate` | Dashboard | `{block_id, team}`: send a responder team to everyone with no neighbour | ✅ |
| `GET /handover-brief` | Dashboard | The SCDF brief (after beat 8) | ✅ |
| `GET /after-action` | Dashboard | The after-action report (after beat 10) | ✅ |
| `GET /family-cover?block_id=123` | Dashboard | Essential workers and families covered | ✅ |
| `GET /family/{worker_id}` | Phone | An essential worker's family status | ✅ |
| `POST /control/block-125`, `/control/scdf-arrives`, `/control/after-action` | Control panel | Beats 7, 8, 10 | ✅ |
| `POST /reports/{id}/decision` | Dashboard | `{decision: "approve" \| "reject"}` for a low-trust report | ✅ |
| `GET /rumours?block_id=123` | Dashboard | Flagged rumours | ✅ |
| `POST /rumours/{id}/approve` | Dashboard | `{answer}`: official's verified answer, sent via neighbours | ✅ |
| `POST /rumours/{id}/dismiss` | Dashboard | Not a rumour | ✅ |
| `GET /tasks/{id}/profile?helper_id=aziz` | Phone | Need-to-know view of the Sealed Profile (assigned helper, active incident only) | ✅ |
| `GET /unlock-log` | Dashboard | Every Sealed Profile opening, newest first | ✅ |
| `POST /control/fake-report` | Control panel | Fake report from an unknown number, then a water rumour | ✅ |
| `POST /reports/voice` | Phone | Form upload: `audio` file + `sender_id`. Whisper → text → read like any report. Returns the report + `transcript`. 501 with how-to if Whisper isn't installed | ✅ |
| `GET /join/roles` | Join page | Helper roles judges can play (`taken` flag) + Telegram bot status | ✅ |
| `POST /join` | Join page | `{helper_id, consent: true}`: play that helper on this web page | ✅ |
| `POST /join/leave` | Phone | `{helper_id}` | ✅ |
| `GET /block-card/{block_id}` | Print page | `knock_first` (unit numbers in order), `helpers` (unit + skills). No names or needs | ✅ |
| `GET /silence/cases` | Dashboard | Silence Alert cases, newest first | ✅ |
| `GET /silence/seniors?block_id=123` | Phone | Opted-in seniors a neighbour can tap "haven't seen" for | ✅ |
| `POST /silence/not-seen` | Phone | `{reporter_id, unit}` | ✅ |
| `POST /silence/{id}/approve` | Dashboard | A person approves the next ladder step | ✅ |
| `POST /silence/{id}/resolve` | Phone | `{outcome: "okay" \| "no_answer"}` from the knocking neighbour | ✅ |

### Example: `POST /reports`

Request:
```json
{ "text": "Eh the auntie at 9-12 never open door, got smell leh", "sender_id": "meiling" }
```
The response comes back straight away with `"status": "reading"` and `"parsed": null`.
A moment later every screen receives `report_updated` with the finished report:
```json
{
  "id": 1,
  "text": "Eh the auntie at 9-12 never open door, got smell leh",
  "sender_id": "meiling",
  "parsed": {
    "unit": "#09-12", "person_hint": "auntie", "concern": "not answering door, bad smell",
    "urgency": 5, "language": "Singlish", "confidence": 0.9, "source": "claude"
  },
  "resident_id": "tan",
  "resident_name": "Mdm Tan Ah Moi",
  "status": "new",
  "created_at": "2026-11-26T13:00:00Z"
}
```
`parsed.source` is `"claude"` or `"fallback"` (rule-based backup when there's no key or no internet).

Every report also gets `trust_level` (`high`, `medium`, `low`) and `trust_reasons`, e.g.
`["unknown sender", "no second report", "unit #14-03 is vacant"]`. Low-trust reports get
`status: "waiting_for_human"` and are never acted on until an official approves them.

## Live messages (`/ws`)

Every message is JSON with a `type` and an `at` timestamp.

| Type | Fields | Status |
| --- | --- | --- |
| `scene` | `name`: idle, evening, crisis... | ✅ |
| `reset` | — (screens should reload their data) | ✅ |
| `report_new` | `report` with `status: "reading"`, `parsed: null` (show "AI reading...") | ✅ |
| `report_updated` | `report` with `parsed` filled in by the AI | ✅ |
| `control_progress` | `done`: list of beats already run | ✅ |
| `checkin` | `resident_id`, `unit` | ✅ |
| `unit_status` | `block_id`, `unit`, `status`: normal, task_sent, reached, escalated | ✅ |
| `incident` | `incident_id`, `cause`, `power_out`, `lifts_down` | ✅ |
| `task_new` | `task` (see Task shape below); `instructions` is null at first | ✅ |
| `task_updated` | `task` with Claude's `instructions` filled in | ✅ |
| `task_status` | `task` with its new `status` | ✅ |
| `progress` | `reached`, `vulnerable`, `all_reached` | ✅ |
| `ranking_changed` | `block_id` (screens should reload `/incidents/current`) | ✅ |
| `mode_change` | `block_id`, `mode`: full, low_data, relay, no_phone, `label` | ✅ |
| `sms` | `helper_id`, `task_id`, `text` (≤160 characters) | ✅ |
| `relay` | `helper_id`, `task_id`, `block_id`, `hops` (units, void deck → helper), `text`, `simulated: true` | ✅ |
| `silence_case` | `case` | ✅ |
| `joined` / `left` | `helper_id`, `via` (web, telegram) | ✅ |
| `knock_request` | `helper_id`, `case`: ask this neighbour to knock | ✅ |
| `rumour_flagged` / `rumour_updated` | `rumour` | ✅ |
| `verified_message` | `answer`, `via` (resident id → the neighbour who passes it on) | ✅ |
| `profile_unlocked` | `task_id`, `resident_id`, `helper_id`, `keys`, `log` | ✅ |
| `brief_ready` | `brief` {text, source} | ✅ |
| `block_alert` | `block_id`, `unreached`, `suggested_team` | ✅ |
| `responders_moved` | `team`, `block_id`, `residents` | ✅ |
| `family_status` | `worker_id`, `dependent_unit`, `dependent_name`, `helper_name`, `status` | ✅ |
| `after_action` | `report` | ✅ |

## Task shape

```json
{
  "id": 1, "incident_id": 1, "rank": 1, "score": 120,
  "reasons": ["lives alone", "oxygen concentrator (~1h battery)", "uses a walker", "hard of hearing", "lifts down", "neighbour report: not answering door, bad smell", "level 9"],
  "resident_id": "tan", "resident_name": "Mdm Tan Ah Moi", "resident_unit": "#09-12",
  "helper_id": "aziz", "helper_name": "Aziz Rahman", "helper_unit": "#07-10",
  "instructions": {
    "headline": "Periksa Mdm Tan, #09-12, sekarang",
    "steps": ["...", "..."], "bring": ["lampu suluh", "telefon"],
    "sms": "KG: ... Reply 1=reached 2=need help", "language": "ms", "source": "claude"
  },
  "channel": "app", "status": "sent", "simulated": false, "created_at": "..."
}
```

Status flow: `sent` → `on_the_way` → `reached` (or `need_help`). If nobody responds within
`KG_ESCALATE_SECONDS`, the task becomes `reassigned` and a new task goes to the next-best helper;
if no helper is left, the new task is `escalated` (to official services).
