// The demo control panel: one button per demo beat, in order.
// One teammate drives this from a second laptop or phone while the speaker talks.

import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import ConnectionDot from '../components/ConnectionDot'
import { api, MODE_LABEL, useLive, type JoinInfo, type Mode } from '../lib/api'

const BEATS: { id: string; label: string }[] = [
  { id: 'start-evening', label: 'Start evening' },
  { id: 'cyberattack', label: 'Cyberattack' },
  { id: 'voice-note', label: 'Voice note arrives' },
  { id: 'assign-helper', label: 'Assign helper' },
  { id: 'network-down', label: 'Network down' },
  { id: 'fake-report', label: 'Fake report + rumour' },
  { id: 'block-125', label: 'Block 125 in trouble' },
  { id: 'scdf-arrives', label: 'SCDF arrives' },
  { id: 'mdm-tan-reached', label: 'Mdm Tan reached' },
  { id: 'after-action', label: 'After-action report' },
]

export default function Control() {
  const [done, setDone] = useState<string[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [phoneUrl, setPhoneUrl] = useState(`${location.origin}/join`)
  // A public https link (e.g. a Cloudflare tunnel) so judges on mobile data can join.
  const [publicUrl, setPublicUrl] = useState(() => {
    try {
      return localStorage.getItem('kg-public-url') ?? ''
    } catch {
      return ''
    }
  })
  const [joinInfo, setJoinInfo] = useState<JoinInfo | null>(null)
  const [ai, setAi] = useState<{ offline: boolean; saved_answers: number; key_set: boolean } | null>(null)
  const loadJoin = () => {
    api.joinRoles().then(setJoinInfo).catch(() => {})
    api.aiStatus().then(setAi).catch(() => {})
  }

  // The server remembers which beats have run, so refreshing this page doesn't lose our place.
  const connected = useLive((msg) => {
    if (msg.type === 'control_progress') setDone(msg.done as string[])
    if (['joined', 'left', 'reset'].includes(msg.type)) loadJoin()
  })

  useEffect(() => {
    api.state().then((s) => setDone(s.done)).catch(() => {})
    loadJoin()
    // "localhost" only works on this laptop. Ask the backend for the laptop's
    // network address so the QR code works on phones.
    const local = ['localhost', '127.0.0.1', '::1'].includes(location.hostname)
    if (local) {
      api
        .network()
        .then(({ ip }) => {
          if (ip) setPhoneUrl(`${location.protocol}//${ip}${location.port ? `:${location.port}` : ''}/join`)
        })
        .catch(() => {})
    }
  }, [])

  const joinUrl = publicUrl ? `${publicUrl.replace(/\/+$/, '')}/join` : phoneUrl
  const nextIndex = BEATS.findIndex((b) => !done.includes(b.id))

  const run = async (beat: string) => {
    setBusy(true)
    setMessage(null)
    try {
      const res = await api.control(beat)
      if (!res.ok) setMessage(res.message ?? 'Not ready yet')
      // On success the server sends `control_progress`, which ticks the beat off.
    } catch {
      setMessage('Backend not reachable')
    } finally {
      setBusy(false)
    }
  }

  const setModeTo = async (mode: Mode) => {
    setBusy(true)
    setMessage(null)
    try {
      const res = await api.setMode(mode)
      setMessage(res.ok ? `Network mode: ${MODE_LABEL[mode]}` : (res.message ?? 'Not ready yet'))
    } catch {
      setMessage('Backend not reachable')
    } finally {
      setBusy(false)
    }
  }

  const reset = async () => {
    if (!confirm('Reset everything to the start of the demo?')) return
    setBusy(true)
    try {
      await api.control('reset')
      setMessage('Reset done')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col gap-4 p-5">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Demo control</h1>
        <ConnectionDot connected={connected} />
      </header>

      <ol className="flex flex-col gap-2">
        {BEATS.map((b, i) => {
          const isDone = done.includes(b.id)
          const isNext = i === nextIndex
          return (
            <li key={b.id}>
              <button
                disabled={busy}
                onClick={() => run(b.id)}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-base font-semibold transition
                  ${isDone ? 'bg-canvas text-muted line-through' : isNext ? 'bg-brand text-white shadow-md' : 'bg-panel text-ink ring-1 ring-line'}`}
              >
                <span className={`flex h-7 w-7 items-center justify-center rounded-full text-sm ${isNext ? 'bg-white text-brand' : 'bg-canvas text-muted'}`}>
                  {i + 1}
                </span>
                {b.label}
              </button>
            </li>
          )
        })}
      </ol>

      {message && <p className="rounded-lg bg-warn-soft p-3 text-sm text-warn">{message}</p>}

      <button onClick={reset} disabled={busy} className="rounded-xl bg-danger px-4 py-3 font-semibold text-white">
        Reset demo
      </button>

      <section className="rounded-xl bg-panel p-4 ring-1 ring-line">
        <p className="mb-2 text-sm font-semibold">Network mode (for Q&amp;A: "what if there's no signal at all?")</p>
        <div className="grid grid-cols-2 gap-2">
          {(Object.keys(MODE_LABEL) as Mode[]).map((m) => (
            <button key={m} disabled={busy} onClick={() => setModeTo(m)} className="rounded-lg bg-canvas px-3 py-2 text-sm font-medium ring-1 ring-line">
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>
        <a href="/print/block/123" target="_blank" className="mt-2 block text-sm text-brand underline">
          Open the printed block card
        </a>
      </section>

      <section className="rounded-xl bg-panel p-4 ring-1 ring-line">
        <p className="mb-2 text-sm font-semibold">Practice: send a job to everyone who joined</p>
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              setMessage((await api.testJob()).message)
            } catch {
              setMessage('Backend not reachable')
            } finally {
              setBusy(false)
            }
          }}
          className="w-full rounded-lg bg-brand px-3 py-2 text-sm font-semibold text-white"
        >
          Send a test job
        </button>
        <p className="mt-1 text-xs text-muted">No beats needed. Friends who scanned the QR code or opened the bot get a job right away.</p>
      </section>

      <section className="rounded-xl bg-panel p-4 ring-1 ring-line">
        <p className="mb-2 text-sm font-semibold">Extra: Silence Alert</p>
        <button disabled={busy} onClick={() => run('silence-demo')} className="w-full rounded-lg bg-warn px-3 py-2 text-sm font-semibold text-white">
          Mr Lim hasn't checked in for 2 days
        </button>
        <p className="mt-1 text-xs text-muted">Works any time, even before the evening starts.</p>
      </section>

      <section className="mt-2 rounded-xl bg-panel p-4 ring-1 ring-line">
        <div className="flex items-center gap-4">
          <QRCodeSVG value={joinUrl} size={112} />
          <div className="text-sm">
            <p className="font-semibold">Judges: scan to join Block 123</p>
            <p className="break-all text-muted">{joinUrl}</p>
            <p className="mt-1 text-xs text-muted">
              {publicUrl ? 'Public link: works on mobile data.' : 'Same Wi-Fi only. Paste a tunnel link below for mobile data.'}
            </p>
          </div>
        </div>
        <input
          value={publicUrl}
          onChange={(e) => {
            const v = e.target.value.trim()
            setPublicUrl(v)
            try {
              localStorage.setItem('kg-public-url', v)
            } catch {
              /* private browsing: just don't remember it */
            }
          }}
          placeholder="Optional: https://....trycloudflare.com"
          className="mt-3 w-full rounded-lg bg-canvas px-3 py-2 text-sm ring-1 ring-line"
        />
        {joinInfo && (
          <div className="mt-3 text-xs">
            <p>
              Joined:{' '}
              {joinInfo.roles.filter((r) => r.taken).map((r) => r.name).join(', ') || <span className="text-muted">nobody yet</span>}
            </p>
            {ai && (
              <p className={ai.offline ? 'text-warn' : 'text-muted'}>
                AI: {ai.offline ? 'offline mode (saved answers only)' : ai.key_set ? 'on' : 'no key (backup rules)'} · backup answers saved:{' '}
                {ai.saved_answers}
              </p>
            )}
            <p className={joinInfo.telegram.username ? 'text-safe' : 'text-muted'}>
              Telegram bot:{' '}
              {joinInfo.telegram.username
                ? `on (@${joinInfo.telegram.username})`
                : joinInfo.telegram.error
                  ? `problem: ${joinInfo.telegram.error}`
                  : 'off (add KG_TELEGRAM_TOKEN to backend/.env)'}
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
