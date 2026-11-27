// Silence Alert on the dashboard: who may need a knock, why, and the next step.
// A person approves every step. Nothing escalates on its own.

import { useState } from 'react'
import { api, type SilenceCase } from '../lib/api'

export default function SilencePanel({ cases }: { cases: SilenceCase[] }) {
  return (
    <section className="rounded-2xl border-2 border-warn bg-panel p-5 shadow-sm">
      <h2 className="text-lg font-semibold">Silence Alert</h2>
      <p className="mb-3 text-sm text-muted">Seniors who opted in. Small signals only: no cameras, no tracking. A person approves every step.</p>
      <ul className="flex flex-col gap-3">
        {cases.slice(0, 3).map((c) => (
          <CaseRow key={c.id} c={c} />
        ))}
      </ul>
    </section>
  )
}

function CaseRow({ c }: { c: SilenceCase }) {
  const [busy, setBusy] = useState(false)
  const resolved = c.status === 'resolved'
  const badge = resolved ? 'bg-safe-soft text-safe' : c.level === 'red' ? 'bg-danger-soft text-danger' : 'bg-warn-soft text-warn'
  const next = c.ladder[c.step + 1]
  const approve = async () => {
    setBusy(true)
    try {
      await api.silenceApprove(c.id)
    } finally {
      setBusy(false)
    }
  }
  return (
    <li className="rounded-xl border border-line p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold">
          {c.name} <span className="font-normal text-muted">{c.unit}</span>
        </p>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold uppercase ${badge}`}>{resolved ? 'okay' : c.level}</span>
      </div>
      <p className="text-sm text-muted">{c.signals.join(' · ')}</p>

      <ol className="my-2 flex flex-col gap-0.5 text-sm">
        {c.ladder.map((step, i) => (
          <li key={step} className={i < c.step ? 'text-muted line-through' : i === c.step ? 'font-semibold' : 'text-muted'}>
            {i + 1}. {step}
            {i === 1 && c.neighbour && ` (${c.neighbour.name}, ${c.neighbour.unit})`}
            {i === c.step && !resolved && ' ← now'}
          </li>
        ))}
      </ol>

      {c.outcome && <p className={`text-sm font-semibold ${resolved ? 'text-safe' : 'text-danger'}`}>{c.outcome}</p>}
      {!resolved && next && (
        <button onClick={approve} disabled={busy} className="mt-2 rounded-lg bg-warn px-3 py-1.5 text-sm font-semibold text-white">
          Approve next step: {next}
        </button>
      )}
    </li>
  )
}
