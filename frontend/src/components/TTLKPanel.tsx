// Time to Last Knock: minutes until neighbours reach EVERY vulnerable resident.
// The governance view: where is the block weakest, and which small change fixes most?

import { useEffect, useState } from 'react'
import { api, type SimOverview, type WhatIfOption, type WhatIfResult } from '../lib/api'

function hourLabel(t: string) {
  const h = Number(t.slice(0, 2))
  return h === 0 ? '12am' : h < 12 ? `${h}am` : h === 12 ? '12pm' : `${h - 12}pm`
}

/** Counts from one number to another, so a change is felt, not just read. */
function useCountTo(target: number | null, from: number | null) {
  const [value, setValue] = useState(target)
  useEffect(() => {
    if (target === null) return
    if (from === null || from === target) {
      setValue(target)
      return
    }
    setValue(from)
    const step = from > target ? -1 : 1
    const id = setInterval(() => {
      setValue((v) => {
        if (v === null || v === target) {
          clearInterval(id)
          return target
        }
        return v + step
      })
    }, 120)
    return () => clearInterval(id)
  }, [target, from])
  return value
}

export default function TTLKPanel({ blockName = 'Block 123', highlight = false }: { blockName?: string; highlight?: boolean }) {
  const [o, setO] = useState<SimOverview | null>(null)
  const [hour, setHour] = useState(3)
  const [whatIf, setWhatIf] = useState<WhatIfResult | null>(null)
  const [chosen, setChosen] = useState<WhatIfOption | null>(null)
  const [loading, setLoading] = useState(false)
  const [showAssumptions, setShowAssumptions] = useState(false)

  useEffect(() => {
    api.simOverview(123).then(setO).catch(() => {})
  }, [])

  const night = useCountTo(chosen ? chosen.after : o?.night.median ?? null, chosen ? chosen.before : null)

  if (!o) {
    return (
      <section className="rounded-2xl bg-panel p-5 shadow-sm">
        <h2 className="text-lg font-semibold">Time to Last Knock</h2>
        <p className="text-sm text-muted">Simulating...</p>
      </section>
    )
  }

  const selected = o.curve[hour]
  const max = Math.max(...o.curve.map((c) => c.p90), 1)

  const runWhatIf = async () => {
    setLoading(true)
    try {
      setWhatIf(await api.whatIf('03:00'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className={`rounded-2xl bg-panel p-5 shadow-sm ${highlight ? 'ring-2 ring-brand' : ''}`}>
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Time to Last Knock · {blockName}</h2>
        <button onClick={() => setShowAssumptions((v) => !v)} className="text-xs text-muted underline">
          {showAssumptions ? 'Hide assumptions' : 'Assumptions'}
        </button>
      </div>
      <p className="mb-4 text-sm text-muted">
        Minutes until neighbours reach every vulnerable resident, simulated {o.evening.runs} times with the lifts down.
      </p>

      <div className="mb-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-safe-soft p-4">
          <p className="text-sm font-medium text-safe">7pm</p>
          <p className="text-4xl font-bold text-ink">
            {o.evening.median} <span className="text-lg font-semibold">min</span>
          </p>
          <p className="text-xs text-muted">bad night: {o.evening.p90} min</p>
        </div>
        <div className={`rounded-xl p-4 ${chosen ? 'bg-safe-soft' : 'bg-danger-soft'}`}>
          <p className={`text-sm font-medium ${chosen ? 'text-safe' : 'text-danger'}`}>3am{chosen ? ' (with the change)' : ''}</p>
          <p className="text-4xl font-bold text-ink">
            {night} <span className="text-lg font-semibold">min</span>
          </p>
          <p className="text-xs text-muted">{chosen ? `was ${chosen.before} min` : `bad night: ${o.night.p90} min`}</p>
        </div>
      </div>

      {o.gap && (
        <p className="mb-4 rounded-lg bg-warn-soft px-3 py-2 text-sm font-medium text-warn">
          Biggest gap: {o.gap.replace(' at 03:00', ' at night')}
        </p>
      )}

      {/* 24-hour strip: when is the block weakest? */}
      <div className="mb-1 flex items-end gap-[3px]" style={{ height: 64 }} aria-label="Typical minutes by hour of day">
        {o.curve.map((c, i) => (
          <button
            key={c.time}
            onClick={() => setHour(i)}
            title={`${hourLabel(c.time)}: ${c.median} min`}
            className={`flex-1 rounded-t ${i === hour ? 'bg-ink' : c.median >= o.night.median ? 'bg-danger/60' : 'bg-brand/50'}`}
            style={{ height: `${(c.median / max) * 100}%` }}
          />
        ))}
      </div>
      <div className="mb-2 flex justify-between text-[10px] text-muted">
        <span>12am</span>
        <span>6am</span>
        <span>12pm</span>
        <span>6pm</span>
        <span>11pm</span>
      </div>
      <input type="range" min={0} max={23} value={hour} onChange={(e) => setHour(Number(e.target.value))} className="w-full accent-[var(--color-brand)]" />
      <p className="mb-4 text-sm">
        At <span className="font-semibold">{hourLabel(selected.time)}</span>: typically{' '}
        <span className="font-semibold">{selected.median} min</span>, bad night {selected.p90} min.
      </p>

      {/* What if? */}
      {!whatIf ? (
        <button onClick={runWhatIf} disabled={loading} className="w-full rounded-xl bg-ink px-4 py-3 font-semibold text-white">
          {loading ? 'Testing changes...' : 'What if? Find the change that cuts 3am most'}
        </button>
      ) : (
        <div>
          <p className="mb-2 text-sm font-semibold">What if... (3am, typical night)</p>
          <ul className="mb-3 flex flex-col gap-2">
            {whatIf.options.map((opt) => (
              <li key={opt.label}>
                <button
                  onClick={() => setChosen(chosen?.label === opt.label ? null : opt)}
                  className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm ring-1 ${
                    chosen?.label === opt.label ? 'bg-safe-soft ring-safe' : 'bg-panel ring-line hover:ring-brand'
                  }`}
                >
                  <span className="font-medium">{opt.label}</span>
                  <span className="whitespace-nowrap font-semibold text-safe">
                    {opt.before} → {opt.after} min
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="text-sm text-ink">{whatIf.summary.text}</p>
          {whatIf.summary.source === 'fallback' && <p className="mt-1 text-xs text-muted">(Summary by backup template: AI offline.)</p>}
        </div>
      )}

      {showAssumptions && (
        <pre className="mt-4 max-h-56 overflow-auto rounded-lg bg-canvas p-3 text-xs text-muted">
          {JSON.stringify(o.assumptions, null, 2)}
        </pre>
      )}
    </section>
  )
}
