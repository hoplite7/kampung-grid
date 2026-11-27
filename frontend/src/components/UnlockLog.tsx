// Every time a Sealed Profile was opened: who, when, why, what was shown.
// Shown on the dashboard for two seconds in the demo; one click away for the Q&A.

import type { UnlockEntry } from '../lib/api'

const FIELD_LABEL: Record<string, string> = {
  powered_equipment: 'equipment',
  equipment_battery_hours: 'battery',
  mobility: 'mobility',
  hearing: 'hearing',
  languages: 'languages',
  how_to_knock: 'how to knock',
  lives_alone: 'lives alone',
}

export default function UnlockLog({ entries, names }: { entries: UnlockEntry[]; names: Record<string, string> }) {
  return (
    <section className="rounded-2xl bg-panel p-5 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <span aria-hidden>🔒</span>
        <h2 className="text-lg font-semibold">Sealed Profiles · unlock log</h2>
      </div>
      <p className="mb-3 text-sm text-muted">
        Profiles are encrypted. Opening one needs two keys: the incident key (released only during a declared incident) and the
        system key. Every opening is recorded.
      </p>
      {entries.length === 0 ? (
        <p className="text-sm text-muted">No profiles opened. Nobody can read them outside an incident.</p>
      ) : (
        <div className="max-h-56 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="py-1 pr-2 font-medium">Time</th>
                <th className="py-1 pr-2 font-medium">Profile</th>
                <th className="py-1 pr-2 font-medium">Opened for</th>
                <th className="py-1 font-medium">Fields shown</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-t border-line">
                  <td className="py-1 pr-2 text-muted">
                    {new Date(e.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </td>
                  <td className="py-1 pr-2">{names[e.resident_id] ?? e.resident_id}</td>
                  <td className="py-1 pr-2">
                    {e.opened_for === 'crisis engine'
                      ? 'Crisis engine (ranking)'
                      : names[e.opened_for]
                        ? `Helper: ${names[e.opened_for]}`
                        : e.opened_for}
                  </td>
                  <td className="py-1 text-muted">{e.fields_shown.map((f) => FIELD_LABEL[f] ?? f).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
