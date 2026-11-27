// The SCDF handover brief (beat 8) and the after-action report (beat 10).

import type { AfterAction, Brief } from '../lib/api'

export function HandoverBrief({ brief, onClose }: { brief: Brief; onClose: () => void }) {
  const lines = brief.text.split('\n').filter((l) => l.trim())
  return (
    <section className="rounded-2xl border-2 border-ink bg-white p-5 shadow-lg">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs font-bold uppercase tracking-wide text-ink">SCDF handover brief</p>
        <div className="flex gap-2">
          <button onClick={() => window.print()} className="rounded-lg px-3 py-1 text-xs ring-1 ring-line">
            Print
          </button>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-xs ring-1 ring-line">
            Close
          </button>
        </div>
      </div>
      <div className="flex flex-col gap-1 font-mono text-sm leading-relaxed">
        {lines.map((line, i) => {
          const heading = /^(NOT REACHED|REACHED|ALSO)\b/i.test(line)
          const notReached = /^NOT REACHED/i.test(line)
          return (
            <p
              key={i}
              className={
                i === 0
                  ? 'text-base font-bold'
                  : notReached
                    ? 'mt-2 font-bold text-danger'
                    : heading
                      ? 'mt-2 font-bold'
                      : ''
              }
            >
              {line}
            </p>
          )
        })}
      </div>
      <p className="mt-3 text-xs text-muted">
        {brief.source === 'claude' ? 'Written by AI from the live crisis log.' : 'Standard template (AI offline).'} Opening the
        profiles for SCDF is recorded in the unlock log.
      </p>
    </section>
  )
}

export function AfterActionReport({ report }: { report: AfterAction }) {
  const allReached = report.reached === report.vulnerable
  return (
    <section className="rounded-2xl bg-panel p-5 shadow-sm ring-2 ring-brand">
      <p className="text-xs font-bold uppercase tracking-wide text-brand">After-action report · Block 123</p>
      <h2 className="mb-3 text-xl font-bold">
        {allReached ? `All ${report.vulnerable} vulnerable residents reached` : `${report.reached} of ${report.vulnerable} vulnerable residents reached`}
      </h2>
      <div className="mb-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <Stat label="Measured last knock" value={report.measured_minutes !== null ? `${report.measured_minutes} min*` : 'not yet'} />
        <Stat label="Tasks reassigned" value={String(report.reassigned)} />
        <Stat label="Fake reports caught" value={String(report.fake_reports_rejected)} />
        <Stat label="Rumours answered" value={String(report.rumours_answered)} />
      </div>
      <p className="text-sm">
        Essential workers: {report.family_cover.workers} · families covered {report.family_cover.covered}/{report.family_cover.with_family}
      </p>
      <p className="mt-2 text-xs text-muted">* {report.note} Next: fix the night-time gap below.</p>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-canvas p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-lg font-bold">{value}</p>
    </div>
  )
}
