// /join: where the QR code takes a judge. They agree, pick a helper to play,
// and choose: this web page, or Telegram (a real message on their phone).

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, useLive, type JoinInfo, type JoinRole } from '../lib/api'

const SKILL: Record<string, string> = { cpr: 'CPR', first_aid: 'First aid' }
const LANG: Record<string, string> = { en: 'English', ms: 'Malay', zh: 'Chinese', ta: 'Tamil' }

export default function Join() {
  const [info, setInfo] = useState<JoinInfo | null>(null)
  const [agreed, setAgreed] = useState(false)
  const [picked, setPicked] = useState<JoinRole | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const load = () => api.joinRoles().then(setInfo).catch(() => setError("Can't reach the demo. Ask the team for help."))
  useEffect(() => {
    load()
  }, [])
  useLive((msg) => {
    if (['joined', 'left', 'reset'].includes(msg.type)) load()
  })

  const useWeb = async () => {
    if (!picked) return
    try {
      await api.join(picked.helper_id)
      navigate(`/phone/${picked.helper_id}`)
    } catch {
      setError('Someone just took that role. Pick another.')
      setPicked(null)
      load()
    }
  }

  const bot = info?.telegram.username
  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col gap-4 p-5">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wide text-brand">Kampung Grid · live demo</p>
        <h1 className="text-2xl font-bold">Be a helper in Block 123</h1>
        <p className="text-sm text-muted">
          A blackout is about to hit a (pretend) HDB block. You'll play a neighbour who signed up to help. If someone
          near you needs a knock on the door, your phone gets the task.
        </p>
      </header>

      <label className="flex gap-3 rounded-2xl bg-panel p-4 text-sm ring-1 ring-line">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-1 h-5 w-5 shrink-0" />
        <span>
          I'm happy to join. Everyone in this demo is made up. We don't ask for your name or number. If you use
          Telegram we only see a chat ID, and it's deleted when the demo resets or you send /stop.
        </span>
      </label>

      {error && <p className="rounded-lg bg-danger-soft p-3 text-sm text-danger">{error}</p>}

      <section className={agreed ? '' : 'pointer-events-none opacity-40'}>
        <p className="mb-2 font-semibold">1. Who do you want to play?</p>
        <ul className="flex flex-col gap-2">
          {info?.roles.map((r) => (
            <li key={r.helper_id}>
              <button
                disabled={r.taken}
                onClick={() => setPicked(r)}
                className={`flex w-full items-center justify-between rounded-xl px-4 py-3 text-left ring-1 ${
                  picked?.helper_id === r.helper_id ? 'bg-brand text-white ring-brand' : 'bg-panel ring-line'
                } ${r.taken ? 'opacity-40' : ''}`}
              >
                <span>
                  <span className="font-semibold">{r.name}</span>
                  <span className="block text-xs opacity-80">
                    {r.unit} · {r.languages.map((l) => LANG[l] ?? l).join(', ')}
                    {r.skills.length > 0 && ` · ${r.skills.map((s) => SKILL[s] ?? s).join(', ')}`}
                  </span>
                </span>
                <span className="text-xs">{r.taken ? 'taken' : ''}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {picked && agreed && (
        <section className="flex flex-col gap-2">
          <p className="font-semibold">2. How should we reach you?</p>
          {bot ? (
            <a
              href={`https://t.me/${bot}?start=${picked.helper_id}`}
              className="rounded-2xl bg-[#229ED9] px-4 py-4 text-center text-lg font-bold text-white"
            >
              Telegram: a real message on your phone
            </a>
          ) : null}
          <button onClick={useWeb} className="rounded-2xl bg-panel px-4 py-4 text-lg font-bold ring-1 ring-line">
            Stay on this web page
          </button>
          {bot && <p className="text-center text-xs text-muted">With Telegram, tap Start when it opens.</p>}
        </section>
      )}
    </div>
  )
}
