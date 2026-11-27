// Block 125: the governance decision in the demo. Nobody can help there at night,
// so an official sends a responder team to the block that needs it most.

import { useState } from 'react'
import BlockView from './BlockView'
import { api, type Block, type IncidentState, type Task } from '../lib/api'

export default function Block125Card({ block, crisis }: { block: Block; crisis: IncidentState }) {
  const [busy, setBusy] = useState(false)
  const latest = new Map<string, Task>()
  for (const t of [...crisis.tasks].sort((a, b) => a.id - b.id)) latest.set(t.resident_id, t)
  const tasks = [...latest.values()]
  const unreached = tasks.filter((t) => t.status === 'escalated').length
  const enRoute = tasks.filter((t) => t.status === 'responder_en_route').length
  const reached = tasks.filter((t) => t.status === 'reached').length
  const team = tasks.find((t) => t.responder)?.responder ?? null
  const inTrouble = !!crisis.incident && unreached > 0

  const send = async () => {
    setBusy(true)
    try {
      await api.reallocate(125)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={`rounded-2xl bg-panel p-5 shadow-sm ${inTrouble ? 'ring-2 ring-danger' : ''}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Block 125</h2>
          {crisis.incident ? (
            <p className="text-sm text-muted">
              {tasks.length} vulnerable · {reached} reached{enRoute ? ` · ${enRoute} responders on the way` : ''}
              {unreached ? ` · ` : ''}
              {unreached ? <span className="font-semibold text-danger">{unreached} no neighbour available</span> : null}
            </p>
          ) : (
            <p className="text-sm text-muted">No incident.</p>
          )}
        </div>
      </div>

      {inTrouble && (
        <div className="mb-3 rounded-xl bg-danger-soft p-3">
          <p className="mb-2 text-sm font-semibold text-danger">
            {unreached} vulnerable residents unreached. No helpers are home to respond. Send SCDF Team B?
          </p>
          <button onClick={send} disabled={busy} className="w-full rounded-lg bg-ink px-3 py-2.5 font-semibold text-white">
            Reallocate: send SCDF Team B to Block 125
          </button>
        </div>
      )}
      {team && !inTrouble && (
        <p className="mb-3 rounded-lg bg-safe-soft px-3 py-2 text-sm font-medium text-safe">
          {team} reallocated to Block 125{reached === tasks.length ? ': everyone reached.' : '.'}
        </p>
      )}

      <BlockView block={block} compact alert={inTrouble ? 'red' : crisis.incident ? 'amber' : 'none'} />
    </section>
  )
}
