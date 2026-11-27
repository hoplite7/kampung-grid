// The phone app: what residents and helpers see.
// /phone       -> pick who you are (demo only)
// /phone/:id   -> that person's home screen, which changes by role

import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ConnectionDot from '../components/ConnectionDot'
import { api, MODE_LABEL, useLive, type FamilyStatus, type Me, type Mode, type ProfileView, type Report, type SilenceCase, type Task } from '../lib/api'

export function PhonePicker() {
  const [people, setPeople] = useState<{ id: string; name: string; unit: string; is_helper: boolean }[]>([])
  useEffect(() => {
    api.listResidents(123).then(setPeople).catch(() => setPeople([]))
  }, [])
  return (
    <PhoneFrame>
      <h1 className="mb-1 text-xl font-bold">Block 123</h1>
      <p className="mb-4 text-sm text-muted">Demo only: choose who this phone belongs to.</p>
      <ul className="flex flex-col gap-2">
        {people.map((p) => (
          <li key={p.id}>
            <Link to={`/phone/${p.id}`} className="flex items-center justify-between rounded-xl bg-panel px-4 py-3 ring-1 ring-line">
              <span className="font-medium">{p.name}</span>
              <span className="text-sm text-muted">
                {p.unit}
                {p.is_helper ? ' · helper' : ''}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </PhoneFrame>
  )
}

export default function Phone() {
  const { id } = useParams()
  const [me, setMe] = useState<Me | null>(null)
  const [screen, setScreen] = useState<'home' | 'report'>('home')
  const [scene, setScene] = useState('idle')
  const [tasks, setTasks] = useState<Task[]>([])
  const [verified, setVerified] = useState<{ answer: string; via: string | null } | null>(null)
  const [family, setFamily] = useState<FamilyStatus | null>(null)
  const [mode, setMode] = useState<Mode>('full')
  const [sms, setSms] = useState<Record<number, string>>({}) // task id -> SMS text
  const [relay, setRelay] = useState<Record<number, string[]>>({}) // task id -> phones it hopped through
  const [knock, setKnock] = useState<SilenceCase | null>(null)
  const [battery, setBattery] = useState(false)

  useEffect(() => {
    if (!id) return
    api.getResident(id).then(setMe).catch(() => setMe(null))
    api.myTasks(id).then(setTasks).catch(() => setTasks([]))
    api.family(id).then(setFamily).catch(() => setFamily(null))
    api
      .currentIncident()
      .then((s) => setMode((s.incident?.mode as Mode) ?? 'full'))
      .catch(() => {})
    api
      .silenceCases()
      .then((cs) => setKnock(cs.find((c) => c.status === 'open' && c.step >= 1 && c.neighbour?.id === id && !c.outcome) ?? null))
      .catch(() => {})
  }, [id])

  const connected = useLive((msg) => {
    if (msg.type === 'scene') setScene(String(msg.name))
    if (msg.type === 'reset') {
      setScreen('home')
      setTasks([])
      setVerified(null)
      setMode('full')
      setSms({})
      setRelay({})
      setKnock(null)
    }
    if (msg.type === 'mode_change') setMode(msg.mode as Mode)
    if (msg.type === 'sms' && msg.helper_id === id) {
      navigator.vibrate?.(200)
      setSms((m) => ({ ...m, [Number(msg.task_id)]: String(msg.text) }))
    }
    if (msg.type === 'relay' && msg.helper_id === id) setRelay((m) => ({ ...m, [Number(msg.task_id)]: msg.hops as string[] }))
    if (msg.type === 'knock_request' && msg.helper_id === id) {
      navigator.vibrate?.([300, 150, 300])
      setKnock(msg.case as SilenceCase)
    }
    if (msg.type === 'silence_case') {
      const c = msg.case as SilenceCase
      setKnock((k) => (k && k.id === c.id && (c.status !== 'open' || c.outcome) ? null : k))
    }
    if (msg.type === 'family_status' && msg.worker_id === id) {
      setFamily({
        dependent_unit: String(msg.dependent_unit),
        dependent_name: String(msg.dependent_name),
        helper_name: (msg.helper_name as string) ?? null,
        status: msg.status as FamilyStatus['status'],
      })
    }
    if (msg.type === 'verified_message') {
      const via = (msg.via as Record<string, string | null>)[id ?? ''] ?? null
      setVerified({ answer: String(msg.answer), via })
    }
    if (msg.type === 'task_new' || msg.type === 'task_updated' || msg.type === 'task_status') {
      const task = msg.task as Task
      if (task.helper_id !== id) return
      if (msg.type === 'task_new') {
        navigator.vibrate?.([300, 150, 300]) // works on Android; iPhones ignore it
        setScreen('home')
      }
      setTasks((ts) => [task, ...ts.filter((t) => t.id !== task.id)].sort((a, b) => b.id - a.id))
    }
  })

  // The task to show: the newest one that isn't finished or moved away.
  const current = tasks.find((t) => ['sent', 'on_the_way', 'reached', 'need_help'].includes(t.status)) ?? null
  // If our newest task was handed to someone else (we didn't respond in time), say so.
  const moved = !current && tasks[0]?.status === 'reassigned' ? tasks[0] : null

  if (!me) {
    return (
      <PhoneFrame>
        <p className="text-muted">Loading...</p>
      </PhoneFrame>
    )
  }

  return (
    <PhoneFrame battery={battery}>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-brand">Kampung Grid</p>
          <p className="text-lg font-bold">{me.name}</p>
          <p className="text-sm text-muted">
            {me.unit} · Block {me.block_id}
            {me.role === 'helper' ? ' · Helper' : ''}
          </p>
        </div>
        <ConnectionDot connected={connected} />
      </div>

      {scene !== 'idle' && scene !== 'evening' && (
        <div className="mb-2 rounded-xl bg-danger p-3 font-semibold text-white">Power outage in Block 123</div>
      )}

      {scene !== 'idle' && scene !== 'evening' && (
        <ModeBar mode={mode} battery={battery} onBattery={() => setBattery((b) => !b)} />
      )}

      {mode === 'no_phone' && (
        <div className="mb-4 rounded-xl border-2 border-ink bg-panel p-3 text-sm">
          <p className="font-bold">Phones may stop working soon.</p>
          <p>Use the printed block card in your lift lobby: it lists which units to knock on first, and where the helpers live.</p>
        </div>
      )}

      {knock && <KnockCard c={knock} onDone={() => setKnock(null)} />}

      {verified && (
        <div className="mb-4 rounded-xl border-2 border-safe bg-safe-soft p-3">
          <p className="text-xs font-bold uppercase tracking-wide text-safe">Verified update</p>
          <p className="text-sm">
            {verified.via ? (
              <>
                From your neighbour <span className="font-semibold">{verified.via}</span>:{' '}
              </>
            ) : null}
            {verified.answer}
          </p>
        </div>
      )}

      {screen === 'report' ? (
        <ReportScreen me={me} onDone={() => setScreen('home')} />
      ) : (
        <>
          {current &&
            (mode === 'low_data' && sms[current.id] ? (
              <SmsView task={current} text={sms[current.id]} />
            ) : (
              <>
                {mode === 'relay' && relay[current.id] && <RelayNote hops={relay[current.id]} />}
                <TaskCard task={current} helperId={me.id} language={me.helper?.languages[0] ?? me.language} />
              </>
            ))}
          {moved && (
            <section className="mb-4 rounded-2xl border border-line bg-panel p-4">
              <p className="font-semibold">
                {moved.resident_name}'s task moved to another neighbour
              </p>
              <p className="text-sm text-muted">
                It wasn't accepted in time, so the next-nearest helper was asked. Thank you anyway.
              </p>
            </section>
          )}
          <Home me={me} family={family} hasTask={!!current} onReport={() => setScreen('report')} />
        </>
      )}

      <Link to="/phone" className="mt-auto pt-6 text-center text-xs text-muted underline">
        Switch person (demo only)
      </Link>
    </PhoneFrame>
  )
}

// Button labels in the helper's language, with English underneath.
const BUTTONS: Record<string, { onWay: string; reached: string; help: string; bring: string }> = {
  en: { onWay: 'On my way', reached: 'Reached', help: 'Need help', bring: 'Bring' },
  ms: { onWay: 'Dalam perjalanan', reached: 'Sudah sampai', help: 'Perlu bantuan', bring: 'Bawa' },
  zh: { onWay: '我在路上', reached: '已到达', help: '需要帮助', bring: '请带上' },
  ta: { onWay: 'வழியில் இருக்கிறேன்', reached: 'சென்றடைந்தேன்', help: 'உதவி தேவை', bring: 'கொண்டு வாருங்கள்' },
}

function Label({ text, en }: { text: string; en: string }) {
  return (
    <span className="flex flex-col leading-tight">
      <span>{text}</span>
      {text !== en && <span className="text-xs font-medium opacity-80">{en}</span>}
    </span>
  )
}

/** The full-width card a helper sees when a neighbour needs them. */
/** Two keys must turn before a Sealed Profile opens: the incident key, and "you are the assigned helper". */
function SealedProfileView({ task, helperId }: { task: Task; helperId: string }) {
  const [view, setView] = useState<ProfileView | null>(null)
  const [shown, setShown] = useState(0) // 0, 1 or 2 keys turned (animated one after the other)

  useEffect(() => {
    let alive = true
    api
      .taskProfile(task.id, helperId)
      .then((v) => alive && setView(v))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [task.id, helperId])

  useEffect(() => {
    if (!view) return
    const target = (view.keys.incident ? 1 : 0) + (view.keys.incident && view.keys.assigned ? 1 : 0)
    if (shown >= target) return
    const t = setTimeout(() => setShown((n) => n + 1), 700)
    return () => clearTimeout(t)
  }, [view, shown])

  const open = shown === 2 && !!view?.need_to_know
  const n = (view?.need_to_know ?? {}) as Record<string, unknown>
  const facts = [
    n.powered_equipment ? `Uses ${n.powered_equipment}${n.equipment_battery_hours ? ` (~${n.equipment_battery_hours}h battery)` : ''}` : null,
    n.mobility ? `Uses a ${n.mobility}` : null,
    n.hearing ? String(n.hearing)[0].toUpperCase() + String(n.hearing).slice(1) : null,
    Array.isArray(n.languages) ? `Speaks ${(n.languages as string[]).join(', ')}` : null,
    n.how_to_knock ? String(n.how_to_knock)[0].toUpperCase() + String(n.how_to_knock).slice(1) : null,
  ].filter(Boolean) as string[]

  const key = (on: boolean, label: string) => (
    <div className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors duration-500 ${on ? 'bg-safe-soft text-safe' : 'bg-canvas text-muted'}`}>
      <span aria-hidden>{on ? '🔑' : '○'}</span>
      {label}
    </div>
  )

  return (
    <div className="mb-3 rounded-xl border border-line p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-semibold">
          <span aria-hidden>{open ? '🔓' : '🔒'}</span> Sealed Profile: {task.resident_name}
        </p>
      </div>
      <div className="mb-2 grid grid-cols-2 gap-2">
        {key(shown >= 1, 'Incident declared')}
        {key(shown >= 2, 'Assigned to you')}
      </div>
      {open ? (
        <>
          <ul className="list-disc pl-5 text-sm">
            {facts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">Unlocked for you only, for this incident. Every unlock is recorded.</p>
        </>
      ) : (
        <p className="text-xs text-muted">{view?.message ? 'Locked.' : 'Unlocking...'}</p>
      )}
    </div>
  )
}

function TaskCard({ task, helperId, language }: { task: Task; helperId: string; language: string }) {
  const [busy, setBusy] = useState(false)
  const b = BUTTONS[language] ?? BUTTONS.en
  const en = BUTTONS.en
  const ins = task.instructions

  const set = async (status: 'on_the_way' | 'reached' | 'need_help') => {
    setBusy(true)
    try {
      await api.setTaskStatus(task.id, status)
    } finally {
      setBusy(false)
    }
  }

  if (task.status === 'reached') {
    return (
      <section className="mb-4 rounded-2xl bg-safe-soft p-5 text-center">
        <p className="text-2xl">✓</p>
        <p className="text-lg font-bold text-safe">Thank you. {task.resident_name} has been reached.</p>
        <p className="text-sm text-ink">Stay with them until help arrives, if you can.</p>
      </section>
    )
  }
  if (task.status === 'need_help') {
    return (
      <section className="mb-4 rounded-2xl bg-danger-soft p-5 text-center">
        <p className="text-lg font-bold text-danger">Help is being sent.</p>
        <p className="text-sm text-ink">If it's an emergency, call 995 now.</p>
      </section>
    )
  }

  return (
    <section className="mb-4 rounded-2xl border-2 border-danger bg-panel p-5 shadow-md">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-danger">A neighbour needs you</p>
      {ins ? (
        <>
          <h2 className="mb-3 text-xl font-bold leading-snug">{ins.headline}</h2>
          <ol className="mb-3 flex list-decimal flex-col gap-1.5 pl-5 text-base">
            {ins.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
          {ins.bring.length > 0 && (
            <p className="mb-3 text-sm text-muted">
              {(BUTTONS[ins.language] ?? BUTTONS.en).bring}: {ins.bring.join(', ')}
            </p>
          )}
        </>
      ) : (
        <>
          <h2 className="mb-2 text-xl font-bold">
            Check on {task.resident_name}, {task.resident_unit}
          </h2>
          <p className="mb-3 flex items-center gap-2 text-sm text-muted">
            <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
            Writing your instructions...
          </p>
        </>
      )}

      <SealedProfileView task={task} helperId={helperId} />

      <div className="flex flex-col gap-2">
        {task.status === 'sent' ? (
          <button onClick={() => set('on_the_way')} disabled={busy} className="rounded-xl bg-brand px-4 py-4 text-lg font-bold text-white">
            <Label text={b.onWay} en={en.onWay} />
          </button>
        ) : (
          <button onClick={() => set('reached')} disabled={busy} className="rounded-xl bg-safe px-4 py-4 text-lg font-bold text-white">
            <Label text={b.reached} en={en.reached} />
          </button>
        )}
        <button onClick={() => set('need_help')} disabled={busy} className="rounded-xl bg-danger px-4 py-3 font-bold text-white">
          <Label text={b.help} en={en.help} />
        </button>
      </div>

      {ins && (
        <p className="mt-3 text-center text-xs text-muted">
          {ins.source === 'claude' ? 'Written for you by AI' : 'Standard instructions (AI offline)'}
          {task.reasons.length > 0 && ` · Why: ${task.reasons.slice(0, 3).join(', ')}`}
        </p>
      )}
    </section>
  )
}

function Home({ me, family, hasTask, onReport }: { me: Me; family: FamilyStatus | null; hasTask: boolean; onReport: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      {me.is_essential_worker && (
        <section className="rounded-2xl bg-panel p-4 ring-1 ring-line">
          <p className="text-sm font-semibold">You're an essential worker{me.essential_role ? ` (${me.essential_role})` : ''}</p>
          <p className="text-sm text-muted">During an incident you won't be given neighbour tasks, so you can report for duty.</p>
        </section>
      )}

      {me.role === 'helper' && !me.is_essential_worker && !hasTask && (
        <section className="rounded-2xl bg-panel p-4 ring-1 ring-line">
          <p className="text-sm font-semibold">Your tasks</p>
          <p className="text-sm text-muted">Nothing right now. If a neighbour needs you, it appears here.</p>
          {me.helper && me.helper.skills.length > 0 && (
            <p className="mt-2 text-xs text-muted">Your skills: {me.helper.skills.join(', ').replace('_', ' ')}</p>
          )}
        </section>
      )}

      {me.is_essential_worker && me.dependent_unit && <FamilyCard me={me} family={family} />}

      {me.silence_opt_in && <CheckinButton me={me} />}

      {!me.silence_opt_in && <NotSeenButton me={me} />}

      <button onClick={onReport} className="rounded-2xl bg-brand px-4 py-5 text-lg font-bold text-white shadow-md">
        Report something
      </button>
    </div>
  )
}

function isToday(iso: string | null) {
  if (!iso) return false
  return new Date(iso).toDateString() === new Date().toDateString()
}

/** Silence Alert: an opted-in senior taps once a day. */
function CheckinButton({ me }: { me: Me }) {
  const [checkedAt, setCheckedAt] = useState<string | null>(me.last_checkin)
  const [busy, setBusy] = useState(false)
  const done = isToday(checkedAt)

  const checkin = async () => {
    setBusy(true)
    try {
      const res = await api.checkin(me.id)
      setCheckedAt(res.checked_in_at)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="rounded-2xl bg-safe-soft p-5 text-center">
        <p className="text-xl font-bold text-safe">✓ Thank you. See you tomorrow!</p>
        <p className="text-sm text-muted">
          Checked in today at {new Date(checkedAt!).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    )
  }
  return (
    <button onClick={checkin} disabled={busy} className="rounded-2xl bg-safe px-4 py-6 text-xl font-bold text-white disabled:opacity-60">
      {busy ? 'Sending...' : "I'm okay today"}
    </button>
  )
}

const QUICK = ['Someone is not answering their door', 'Fire or smoke', 'Someone is stuck in the lift', 'Someone needs medical help']

function ReportScreen({ me, onDone }: { me: Me; onDone: () => void }) {
  const [text, setText] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [sentId, setSentId] = useState<number | null>(null)
  const [understood, setUnderstood] = useState<Report | null>(null)

  // When the AI finishes reading OUR report, show the sender what it understood.
  // The answer can arrive before we even know our report's id (the backup rules
  // are instant), so keep every update we see and look ours up once we know it.
  const seen = useRef(new Map<number, Report>())
  useLive((msg) => {
    if (msg.type !== 'report_updated') return
    const r = msg.report as Report
    seen.current.set(r.id, r)
    if (r.id === sentId) setUnderstood(r)
  })
  useEffect(() => {
    if (sentId !== null && seen.current.has(sentId)) setUnderstood(seen.current.get(sentId)!)
  }, [sentId])

  // Go back to the home screen a few seconds after the AI has answered.
  useEffect(() => {
    if (!understood) return
    const t = setTimeout(onDone, 5000)
    return () => clearTimeout(t)
  }, [understood, onDone])

  const [transcript, setTranscript] = useState<string | null>(null)
  const onVoice = (r: Report & { transcript: string }) => {
    setTranscript(r.transcript)
    setSentId(r.id)
    setState('sent')
  }

  const send = async () => {
    if (!text.trim()) return
    setState('sending')
    try {
      const report = await api.sendReport(text.trim(), me.id)
      setSentId(report.id)
      setState('sent')
    } catch {
      setState('error')
    }
  }

  if (state === 'sent') {
    const p = understood?.parsed
    return (
      <div className="flex flex-col gap-3">
        <div className="rounded-2xl bg-safe-soft p-6 text-center">
          <p className="text-2xl">✓</p>
          <p className="text-lg font-bold text-safe">Sent. Your block has been told.</p>
        </div>
        {transcript && (
          <p className="rounded-2xl bg-panel p-3 text-sm ring-1 ring-line">
            <span className="font-semibold">We heard:</span> "{transcript}"
          </p>
        )}
        <div className="rounded-2xl bg-panel p-4 text-sm ring-1 ring-line">
          {!p ? (
            <p className="flex items-center gap-2 text-muted">
              <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
              Reading your message...
            </p>
          ) : p.unit ? (
            <p>
              <span className="font-semibold">We understood:</span> {p.unit}
              {understood?.resident_name ? ` (${understood.resident_name})` : ''} · {p.concern}
            </p>
          ) : (
            <p>
              <span className="font-semibold">We got your message.</span> We couldn't tell which unit. If you can, send
              the unit number too.
            </p>
          )}
        </div>
        <button onClick={onDone} className="text-sm text-muted underline">
          Done
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button key={q} onClick={() => setText(q)} className="rounded-full bg-panel px-3 py-1.5 text-sm ring-1 ring-line">
            {q}
          </button>
        ))}
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder="What's happening? Any language is fine."
        className="rounded-2xl bg-panel p-4 text-base ring-1 ring-line focus:outline-none focus:ring-2 focus:ring-brand"
      />
      {state === 'error' && <p className="text-sm text-danger">Couldn't send. Try again.</p>}
      <button
        onClick={send}
        disabled={state === 'sending' || !text.trim()}
        className="rounded-2xl bg-brand px-4 py-4 text-lg font-bold text-white disabled:opacity-50"
      >
        {state === 'sending' ? 'Sending...' : 'Send'}
      </button>
      <VoiceButton me={me} onSent={onVoice} />
      <button onClick={onDone} className="text-sm text-muted underline">
        Cancel
      </button>
    </div>
  )
}

function PhoneFrame({ children, battery = false }: { children: React.ReactNode; battery?: boolean }) {
  return <div className={`mx-auto flex min-h-full max-w-md flex-col p-5 ${battery ? 'battery-saver' : ''}`}>{children}</div>
}

/** Which way messages are reaching this phone right now. */
function ModeBar({ mode, battery, onBattery }: { mode: Mode; battery: boolean; onBattery: () => void }) {
  const style = mode === 'full' ? 'bg-safe-soft text-safe' : mode === 'low_data' ? 'bg-warn-soft text-warn' : 'bg-danger-soft text-danger'
  return (
    <div className={`mb-4 flex items-center justify-between rounded-xl px-3 py-2 text-xs font-semibold ${style}`}>
      <span>Network: {MODE_LABEL[mode]}</span>
      <button onClick={onBattery} className="rounded-full bg-panel px-2 py-0.5 text-ink ring-1 ring-line">
        Battery saver {battery ? 'on' : 'off'}
      </button>
    </div>
  )
}

// The automatic SMS answer, in the same language as the SMS the helper got.
const SMS_REPLY: Record<string, { reached: (name: string) => string; help: string }> = {
  en: { reached: (n) => `KG: Thank you. ${n} marked reached.`, help: 'KG: Help is being sent. Emergency? Call 995.' },
  ms: { reached: (n) => `KG: Terima kasih. ${n} ditanda sudah dijumpai.`, help: 'KG: Bantuan sedang dihantar. Kecemasan? Hubungi 995.' },
  zh: { reached: (n) => `KG: 谢谢。${n} 已标记为已到达。`, help: 'KG: 正在派人协助。紧急情况请拨 995。' },
  ta: { reached: (n) => `KG: நன்றி. ${n} சென்றடைந்ததாகக் குறிக்கப்பட்டது.`, help: 'KG: உதவி அனுப்பப்படுகிறது. அவசரமா? 995 ஐ அழைக்கவும்.' },
}

/** Low data: the task arrives as a plain SMS. Reply with one digit. */
function SmsView({ task, text }: { task: Task; text: string }) {
  const [reply, setReply] = useState<string | null>(task.status === 'reached' ? '1' : task.status === 'need_help' ? '2' : null)
  const send = async (digit: '1' | '2') => {
    setReply(digit)
    await api.setTaskStatus(task.id, digit === '1' ? 'reached' : 'need_help')
  }
  return (
    <section className="mb-4 rounded-2xl bg-panel p-4 ring-1 ring-line">
      <p className="mb-2 text-center text-xs text-muted">Messages · KampungGrid</p>
      <p className="mb-1 text-center text-[10px] uppercase tracking-wide text-muted">Mobile data is down, so this came by SMS</p>
      <div className="flex flex-col gap-2">
        <div className="max-w-[85%] self-start rounded-2xl rounded-bl-sm bg-line px-3 py-2 text-sm">{text}</div>
        {reply && <div className="max-w-[85%] self-end rounded-2xl rounded-br-sm bg-brand px-3 py-2 text-sm text-white">{reply}</div>}
        {reply && (
          <div className="max-w-[85%] self-start rounded-2xl rounded-bl-sm bg-line px-3 py-2 text-sm">
            {(() => {
              const r = SMS_REPLY[task.instructions?.language ?? 'en'] ?? SMS_REPLY.en
              return reply === '1' ? r.reached(task.resident_name ?? '') : r.help
            })()}
          </div>
        )}
      </div>
      {!reply && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button onClick={() => send('1')} className="rounded-xl bg-safe px-3 py-3 font-bold text-white">
            Reply 1 · reached
          </button>
          <button onClick={() => send('2')} className="rounded-xl bg-danger px-3 py-3 font-bold text-white">
            Reply 2 · need help
          </button>
        </div>
      )}
    </section>
  )
}

/** Relay: no network at all. The message hopped between neighbours' phones. */
function RelayNote({ hops }: { hops: string[] }) {
  return (
    <div className="mb-2 rounded-xl bg-danger-soft p-3 text-xs">
      <p className="font-semibold text-danger">No mobile network. This reached you phone to phone:</p>
      <p className="mt-1 font-mono">void deck → {hops.join(' → ')}</p>
      <p className="mt-1 text-muted">Simulated in this prototype. Real phone-to-phone relay is on the roadmap.</p>
    </div>
  )
}

/** Silence Alert step 2: a nearby neighbour is asked to knock. */
function KnockCard({ c, onDone }: { c: SilenceCase; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const answer = async (outcome: 'okay' | 'no_answer') => {
    setBusy(true)
    try {
      await api.silenceResolve(c.id, outcome)
      onDone()
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="mb-4 rounded-2xl border-2 border-warn bg-warn-soft p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-warn">Could you knock on a neighbour's door?</p>
      <p className="mt-1 text-lg font-bold">
        {c.name}, {c.unit}
      </p>
      <p className="mb-3 text-sm">We haven't heard from him in a while. Please knock and check he's okay. No need to go in.</p>
      <div className="grid grid-cols-2 gap-2">
        <button onClick={() => answer('okay')} disabled={busy} className="rounded-xl bg-safe px-3 py-3 font-bold text-white">
          He's okay
        </button>
        <button onClick={() => answer('no_answer')} disabled={busy} className="rounded-xl bg-danger px-3 py-3 font-bold text-white">
          No answer
        </button>
      </div>
    </section>
  )
}

/** Any resident can quietly say "I haven't seen my neighbour" for a senior who opted in. */
function NotSeenButton({ me }: { me: Me }) {
  const [open, setOpen] = useState(false)
  const [seniors, setSeniors] = useState<{ resident_id: string; name: string; unit: string }[]>([])
  const [sent, setSent] = useState<string | null>(null)
  useEffect(() => {
    if (open) api.silenceSeniors(me.block_id).then((xs) => setSeniors(xs.filter((x) => x.resident_id !== me.id))).catch(() => {})
  }, [open, me])
  if (sent)
    return (
      <p className="rounded-2xl bg-panel p-3 text-center text-sm ring-1 ring-line">
        Thank you. Someone will check on {sent}. They won't know it was you.
      </p>
    )
  if (!open)
    return (
      <button onClick={() => setOpen(true)} className="rounded-2xl bg-panel px-4 py-3 text-sm font-semibold ring-1 ring-line">
        Haven't seen a neighbour lately?
      </button>
    )
  return (
    <section className="rounded-2xl bg-panel p-4 ring-1 ring-line">
      <p className="mb-2 text-sm font-semibold">Who haven't you seen?</p>
      <p className="mb-2 text-xs text-muted">Only neighbours who signed up for check-ins are listed.</p>
      <div className="flex flex-col gap-2">
        {seniors.map((x) => (
          <button
            key={x.resident_id}
            onClick={async () => {
              await api.notSeen(me.id, x.unit)
              setSent(x.name)
            }}
            className="rounded-xl bg-canvas px-3 py-2 text-left text-sm ring-1 ring-line"
          >
            {x.name} · {x.unit}
          </button>
        ))}
        <button onClick={() => setOpen(false)} className="text-xs text-muted underline">
          Cancel
        </button>
      </div>
    </section>
  )
}

/** Hold to record a voice note. Needs a secure page (localhost or https) for the microphone. */
function VoiceButton({ me, onSent }: { me: Me; onSent: (r: Report & { transcript: string }) => void }) {
  const [state, setState] = useState<'idle' | 'recording' | 'sending' | 'error'>('idle')
  const [error, setError] = useState('')
  const rec = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    return <p className="text-center text-xs text-muted">Voice notes need the laptop (localhost) or an https link on phones.</p>
  }

  const start = async () => {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const r = new MediaRecorder(stream)
      chunks.current = []
      r.ondataavailable = (e) => chunks.current.push(e.data)
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setState('sending')
        try {
          onSent(await api.sendVoice(new Blob(chunks.current, { type: r.mimeType }), me.id))
          setState('idle')
        } catch (e) {
          setError((e as Error).message)
          setState('error')
        }
      }
      rec.current = r
      r.start()
      setState('recording')
    } catch {
      setError("Couldn't use the microphone. Allow it in the browser and try again.")
      setState('error')
    }
  }
  const stop = () => rec.current?.state === 'recording' && rec.current.stop()

  return (
    <div className="flex flex-col gap-1">
      <button
        onPointerDown={start}
        onPointerUp={stop}
        onPointerLeave={stop}
        disabled={state === 'sending'}
        className={`select-none rounded-2xl px-4 py-4 text-lg font-bold ring-1 ring-line ${state === 'recording' ? 'animate-pulse bg-danger text-white' : 'bg-panel'}`}
      >
        {state === 'recording' ? 'Recording... let go to send' : state === 'sending' ? 'Listening to your note...' : '🎤 Hold to record a voice note'}
      </button>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  )
}

/** Family cover: an essential worker sees their family member has been checked, so they can report for duty. */
function FamilyCard({ me, family }: { me: Me; family: FamilyStatus | null }) {
  const who = family?.dependent_name ?? me.dependent_unit
  const status = family?.status ?? 'none'
  const style =
    status === 'reached' ? 'border-safe bg-safe-soft' : status === 'on_the_way' ? 'border-warn bg-warn-soft' : status === 'escalated' ? 'border-danger bg-danger-soft' : 'border-line bg-panel'
  return (
    <section className={`rounded-2xl border-2 p-4 ${style}`}>
      <p className="text-xs font-bold uppercase tracking-wide text-muted">Your family · {me.dependent_unit}</p>
      {status === 'none' && <p className="text-sm">In an emergency, a neighbour will check on {who} so you can report for duty.</p>}
      {status === 'on_the_way' && (
        <p className="text-sm font-semibold text-warn">
          A neighbour{family?.helper_name ? `, ${family.helper_name},` : ''} is on the way to {who}.
        </p>
      )}
      {status === 'reached' && (
        <>
          <p className="font-semibold text-safe">
            {who} has been checked{family?.helper_name ? ` by ${family.helper_name}` : ' by a neighbour'}. ✓
          </p>
          <p className="text-sm">You can report for duty{me.essential_role ? ` as a ${me.essential_role}` : ''}. We'll update you here.</p>
        </>
      )}
      {status === 'escalated' && <p className="text-sm font-semibold text-danger">No neighbour is free yet. Official responders have been told.</p>}
    </section>
  )
}
