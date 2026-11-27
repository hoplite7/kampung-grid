// Everything the screens need to talk to the backend.
// All calls go to /api/... and /ws, which the Vite dev server forwards to the backend.

import { useEffect, useRef, useState } from 'react'

// ---- Types (keep in sync with docs/api.md) --------------------------------

export type UnitStatus = 'normal' | 'task_sent' | 'reached' | 'escalated'

export interface Unit {
  id: string
  block_id: number
  label: string // "#09-12"
  floor: number
  number: number
  stairwell: string
  occupied: boolean
  status: UnitStatus
}

export interface BlockResident {
  id: string
  name: string
  unit: string
  is_vulnerable: boolean
  is_helper: boolean
  helper_skills: string[]
  is_essential_worker: boolean
  silence_opt_in: boolean
}

export interface Block {
  id: number
  name: string
  floors: number
  units_per_floor: number
  stairwells: Record<string, number[]>
  units: Unit[]
  residents: BlockResident[]
}

export interface ParsedReport {
  unit: string | null
  person_hint: string | null
  concern: string
  urgency: number
  language: string
  confidence: number
  source: 'claude' | 'fallback'
}

export interface Report {
  id: number
  text: string
  sender_id: string | null
  /** null while the AI is still reading the report (status "reading") */
  parsed: ParsedReport | null
  resident_id: string | null
  resident_name: string | null
  sender_name: string
  /** high, medium, low; null while the AI is still reading */
  trust_level: 'high' | 'medium' | 'low' | null
  trust_reasons: string[]
  status: string // reading, new, waiting_for_human, approved, rejected
  created_at: string
}

export interface Rumour {
  id: number
  block_id: number
  claim: string
  count: number
  report_ids: number[]
  status: 'flagged' | 'answered' | 'dismissed'
  verified_answer: string | null
  source: string
  created_at: string
}

export interface UnlockEntry {
  id: number
  resident_id: string
  incident_id: number | null
  opened_for: string
  purpose: string
  fields_shown: string[]
  created_at: string
}

export interface ProfileView {
  keys: { incident: boolean; assigned: boolean }
  need_to_know: Record<string, unknown> | null
  message?: string
}

export interface Me {
  id: string
  name: string
  block_id: number
  unit: string
  language: string
  role: 'resident' | 'helper' | 'senior'
  is_essential_worker: boolean
  essential_role: string | null
  dependent_unit: string | null
  silence_opt_in: boolean
  last_checkin: string | null
  helper: { skills: string[]; languages: string[] } | null
}

export interface Instructions {
  headline: string
  steps: string[]
  bring: string[]
  sms: string
  language: string
  source: 'claude' | 'fallback'
}

export type TaskStatus = 'sent' | 'on_the_way' | 'reached' | 'need_help' | 'escalated' | 'reassigned' | 'responder_en_route'

export interface Task {
  id: number
  incident_id: number
  rank: number
  score: number
  reasons: string[]
  resident_id: string
  resident_name: string | null
  resident_unit: string | null
  helper_id: string | null
  helper_name: string | null
  helper_unit: string | null
  /** null while Claude is still writing them */
  instructions: Instructions | null
  channel: string
  status: TaskStatus
  simulated: boolean
  /** How a real person is taking part: telegram, web (joined by QR), presenter */
  via?: 'telegram' | 'web' | 'presenter' | null
  responder: string | null
  family_of: string | null
  created_at: string
}

export interface RankedResident {
  rank: number
  resident_id: string
  name: string
  unit: string
  score: number
  reasons: string[]
  reached: boolean
}

export interface IncidentState {
  incident: { id: number; type: string; cause: string; mode: string; status: string; started_at: string } | null
  ranked: RankedResident[]
  tasks: Task[]
}

export interface TTLK {
  time: string
  median: number
  p90: number
  runs: number
}

export interface SimOverview {
  block_id: number
  evening: TTLK
  night: TTLK
  curve: TTLK[]
  gap: string | null
  vulnerable: number
  helpers: number
  assumptions: Record<string, unknown>
}

export interface WhatIfOption {
  label: string
  before: number
  after: number
  saved: number
}

export interface WhatIfResult {
  time: string
  before: TTLK
  options: WhatIfOption[]
  summary: { text: string; source: string }
}

export interface Brief {
  text: string
  source: string
  created_at: string
}

export interface AfterAction {
  block_id: number
  vulnerable: number
  reached: number
  measured_minutes: number | null
  reassigned: number
  fake_reports_rejected: number
  rumours_answered: number
  family_cover: FamilyCover
  note: string
}

export interface FamilyCover {
  workers: number
  with_family: number
  covered: number
}

export interface FamilyStatus {
  dependent_unit: string
  dependent_name?: string
  helper_name?: string | null
  status: 'none' | 'on_the_way' | 'reached' | 'escalated'
}

export type Mode = 'full' | 'low_data' | 'relay' | 'no_phone'

export const MODE_LABEL: Record<Mode, string> = {
  full: 'Full',
  low_data: 'Low data: SMS',
  relay: 'Relay: no network',
  no_phone: 'No phones: block card',
}

export interface SilenceCase {
  id: number
  resident_id: string
  name: string
  unit: string | null
  level: 'watch' | 'amber' | 'red'
  signals: string[]
  step: number
  step_label: string | null
  ladder: string[]
  status: 'open' | 'resolved'
  outcome: string | null
  neighbour: { id: string; name: string; unit: string } | null
}

export interface BlockCard {
  block: string
  knock_first: string[]
  helpers: { unit: string; skills: string[] }[]
  updated: string
}

export interface JoinRole {
  helper_id: string
  name: string
  unit: string
  skills: string[]
  languages: string[]
  taken: boolean
}

export interface JoinInfo {
  roles: JoinRole[]
  telegram: { enabled: boolean; username: string | null; error: string | null; joined: number }
}

export interface LiveMessage {
  type: string
  at?: string
  [key: string]: unknown
}

// ---- HTTP helpers -----------------------------------------------------------

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${method} ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  getBlock: (id: number) => request<Block>('GET', `/blocks/${id}`),
  getResident: (id: string) => request<Me>('GET', `/residents/${id}`),
  listResidents: (blockId = 123) =>
    request<{ id: string; name: string; unit: string; is_helper: boolean }[]>('GET', `/residents?block_id=${blockId}`),
  listReports: (blockId = 123) => request<Report[]>('GET', `/reports?block_id=${blockId}`),
  sendReport: (text: string, senderId?: string) =>
    request<Report>('POST', '/reports', { text, sender_id: senderId ?? null }),
  control: (beat: string) => request<{ ok: boolean; message?: string; scene?: string }>('POST', `/control/${beat}`),
  state: () => request<{ scene: string; done: string[] }>('GET', '/state'),
  network: () => request<{ ip: string | null }>('GET', '/network'),
  checkin: (residentId: string) =>
    request<{ ok: boolean; checked_in_at: string }>('POST', '/checkins', { resident_id: residentId }),
  setTaskStatus: (taskId: number, status: 'on_the_way' | 'reached' | 'need_help') =>
    request<Task>('POST', `/tasks/${taskId}/status`, { status }),
  currentIncident: (blockId = 123) => request<IncidentState>('GET', `/incidents/current?block_id=${blockId}`),
  myTasks: (helperId: string) => request<Task[]>('GET', `/tasks?helper_id=${helperId}`),
  taskProfile: (taskId: number, helperId: string) =>
    request<ProfileView>('GET', `/tasks/${taskId}/profile?helper_id=${helperId}`),
  decideReport: (reportId: number, decision: 'approve' | 'reject') =>
    request<Report>('POST', `/reports/${reportId}/decision`, { decision }),
  listRumours: (blockId = 123) => request<Rumour[]>('GET', `/rumours?block_id=${blockId}`),
  approveRumour: (id: number, answer: string) => request<Rumour>('POST', `/rumours/${id}/approve`, { answer }),
  dismissRumour: (id: number) => request<Rumour>('POST', `/rumours/${id}/dismiss`),
  unlockLog: () => request<UnlockEntry[]>('GET', '/unlock-log'),
  simOverview: (blockId = 123) => request<SimOverview>('GET', `/sim/overview?block_id=${blockId}`),
  whatIf: (time = '03:00', blockId = 123) => request<WhatIfResult>('POST', '/sim/what-if', { block_id: blockId, time }),
  reallocate: (blockId: number, team = 'SCDF Team B') => request('POST', '/responders/reallocate', { block_id: blockId, team }),
  brief: () => request<Brief | null>('GET', '/handover-brief'),
  afterAction: () => request<AfterAction | null>('GET', '/after-action'),
  familyCover: (blockId = 123) => request<FamilyCover>('GET', `/family-cover?block_id=${blockId}`),
  family: (workerId: string) => request<FamilyStatus | null>('GET', `/family/${workerId}`),
  setMode: (mode: Mode, blockId = 123) =>
    request<{ ok: boolean; message?: string }>('POST', '/control/mode', { mode, block_id: blockId }),
  testJob: () => request<{ ok: boolean; message: string }>('POST', '/control/test-job', {}),
  aiStatus: () => request<{ offline: boolean; saved_answers: number; used_this_run: number; key_set: boolean }>('GET', '/ai/status'),
  joinRoles: () => request<JoinInfo>('GET', '/join/roles'),
  join: (helperId: string) => request<JoinRole>('POST', '/join', { helper_id: helperId, consent: true }),
  leave: (helperId: string) => request<{ ok: boolean }>('POST', '/join/leave', { helper_id: helperId }),
  blockCard: (blockId = 123) => request<BlockCard>('GET', `/block-card/${blockId}`),
  silenceCases: () => request<SilenceCase[]>('GET', '/silence/cases'),
  silenceSeniors: (blockId = 123) =>
    request<{ resident_id: string; name: string; unit: string }[]>('GET', `/silence/seniors?block_id=${blockId}`),
  notSeen: (reporterId: string, unit: string) =>
    request<{ ok: boolean }>('POST', '/silence/not-seen', { reporter_id: reporterId, unit }),
  silenceApprove: (id: number) => request<SilenceCase>('POST', `/silence/${id}/approve`),
  silenceResolve: (id: number, outcome: 'okay' | 'no_answer') =>
    request<SilenceCase>('POST', `/silence/${id}/resolve`, { outcome }),
  /** Upload a voice note. Throws an Error whose message is the server's explanation. */
  sendVoice: async (audio: Blob, senderId: string) => {
    const form = new FormData()
    form.append('audio', audio, audio.type.includes('mp4') ? 'note.mp4' : 'note.webm')
    form.append('sender_id', senderId)
    const res = await fetch('/api/reports/voice', { method: 'POST', body: form })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(body.detail ?? `Voice note failed (${res.status})`)
    return body as Report & { transcript: string }
  },
}

// ---- Live updates -----------------------------------------------------------

/**
 * Connects to the live update hub and calls `onMessage` for every message.
 * Reconnects automatically if the connection drops (e.g. backend restarted).
 * Returns whether we're currently connected, for a small status dot.
 */
export function useLive(onMessage: (msg: LiveMessage) => void): boolean {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onMessage)
  handler.current = onMessage

  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let stopped = false

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => {
        try {
          handler.current(JSON.parse(e.data))
        } catch {
          /* ignore malformed messages */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (!stopped) retry = setTimeout(connect, 1500)
      }
    }
    connect()
    return () => {
      stopped = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [])

  return connected
}
