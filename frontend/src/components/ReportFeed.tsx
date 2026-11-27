// The live report feed on the dashboard, with trust badges (Week 3) and
// the rumour card (the attacker's second wave).

import { useState } from 'react'
import { api, type Report, type Rumour } from '../lib/api'

const TRUST_STYLE: Record<string, { label: string; className: string }> = {
  high: { label: 'High trust', className: 'bg-safe-soft text-safe ring-safe' },
  medium: { label: 'Medium trust', className: 'bg-warn-soft text-warn ring-warn' },
  low: { label: 'Low trust', className: 'bg-danger-soft text-danger ring-danger' },
}

export function TrustBadge({ level }: { level: Report['trust_level'] }) {
  if (!level) return <span className="rounded-full bg-canvas px-2.5 py-0.5 text-xs text-muted">Checking trust...</span>
  const t = TRUST_STYLE[level]
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${t.className}`}>{t.label}</span>
}

export function ReportCard({ report }: { report: Report }) {
  const [busy, setBusy] = useState(false)
  const p = report.parsed
  const urgent = (p?.urgency ?? 0) >= 4
  const low = report.trust_level === 'low'
  const decide = async (d: 'approve' | 'reject') => {
    setBusy(true)
    try {
      await api.decideReport(report.id, d)
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`rounded-xl border p-3 ${low && report.status === 'waiting_for_human' ? 'border-2 border-danger' : 'border-line'}`}>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted">
        <span>
          {new Date(report.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {report.sender_name}
        </span>
        <TrustBadge level={report.trust_level} />
      </div>
      <p className="italic">“{report.text}”</p>
      {!p && (
        <p className="mt-2 flex items-center gap-2 text-sm text-muted">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
          AI reading the message...
        </p>
      )}
      {p && (
        <p className={`mt-2 text-sm font-medium ${urgent && !low ? 'text-danger' : 'text-ink'}`}>
          {p.unit ?? 'No unit given'}
          {report.resident_name ? ` (${report.resident_name})` : ''} · {p.concern} · urgency {p.urgency}
        </p>
      )}
      {report.trust_reasons.length > 0 && (
        <p className={`mt-1 text-xs ${low ? 'font-semibold text-danger' : 'text-muted'}`}>Why: {report.trust_reasons.join(' · ')}</p>
      )}

      {low && report.status === 'waiting_for_human' && (
        <div className="mt-3 rounded-lg bg-danger-soft p-3">
          <p className="mb-2 text-sm font-semibold text-danger">Not acted on. A human must check it first.</p>
          <div className="flex gap-2">
            <button onClick={() => decide('approve')} disabled={busy} className="flex-1 rounded-lg bg-ink px-3 py-2 text-sm font-semibold text-white">
              Approve: send 2 helpers together
            </button>
            <button onClick={() => decide('reject')} disabled={busy} className="flex-1 rounded-lg bg-white px-3 py-2 text-sm font-semibold text-danger ring-1 ring-danger">
              Reject as fake
            </button>
          </div>
        </div>
      )}
      {report.status === 'rejected' && <p className="mt-2 text-xs font-semibold text-muted">Rejected by an official as fake. No helpers sent.</p>}
      {report.status === 'approved' && <p className="mt-2 text-xs font-semibold text-safe">Approved by an official.</p>}
      {p?.source === 'fallback' && <p className="mt-1 text-xs text-warn">Read by the backup rules, not Claude (no API key or offline).</p>}
    </li>
  )
}

const SUGGESTED_ANSWER = 'PUB confirms the tap water is safe to drink. Please don’t forward unverified messages.'

export function RumourCard({ rumour }: { rumour: Rumour }) {
  const [answer, setAnswer] = useState(SUGGESTED_ANSWER)
  const [busy, setBusy] = useState(false)

  if (rumour.status === 'answered') {
    return (
      <div className="rounded-xl border border-safe bg-safe-soft p-3">
        <p className="text-sm font-semibold text-safe">Rumour answered: “{rumour.claim}”</p>
        <p className="text-sm">Sent through residents' own neighbours: “{rumour.verified_answer}”</p>
      </div>
    )
  }
  if (rumour.status === 'dismissed') return null

  return (
    <div className="rounded-xl border-2 border-warn bg-warn-soft p-3">
      <p className="text-xs font-bold uppercase tracking-wide text-warn">Rumour spreading · {rumour.count} messages</p>
      <p className="mb-2 text-base font-semibold">“{rumour.claim}”</p>
      <p className="mb-2 text-xs text-muted">
        The AI only spots the claim. An official checks the facts before anything is sent.
        {rumour.source === 'fallback' && ' (Spotted by backup rules: AI offline.)'}
      </p>
      <textarea
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        rows={2}
        className="mb-2 w-full rounded-lg bg-white p-2 text-sm ring-1 ring-line focus:outline-none focus:ring-2 focus:ring-brand"
      />
      <div className="flex gap-2">
        <button
          disabled={busy || !answer.trim()}
          onClick={async () => {
            setBusy(true)
            try {
              await api.approveRumour(rumour.id, answer)
            } finally {
              setBusy(false)
            }
          }}
          className="flex-1 rounded-lg bg-ink px-3 py-2 text-sm font-semibold text-white"
        >
          Approve and send via neighbours
        </button>
        <button onClick={() => api.dismissRumour(rumour.id)} disabled={busy} className="rounded-lg bg-white px-3 py-2 text-sm ring-1 ring-line">
          Dismiss
        </button>
      </div>
    </div>
  )
}
