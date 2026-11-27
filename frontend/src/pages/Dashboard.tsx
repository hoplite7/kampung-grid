// The authority dashboard: the big screen in the demo.
// Week 1: block view, scene banner, live report feed.
// Week 2: crisis banner, "who needs a knock first" list with reasons,
//         helper lines on the block, and the moment Mdm Tan is reached.
// Week 3: trust badges on reports, the rumour card, the Sealed Profile unlock log.
// Week 4: Time to Last Knock + what-if, Block 125 reallocation, SCDF handover brief,
//         family cover, the after-action report.

import { useCallback, useEffect, useState } from 'react'
import Block125Card from '../components/Block125Card'
import BlockView, { BlockLegend, type HelperLink } from '../components/BlockView'
import { AfterActionReport, HandoverBrief } from '../components/BriefPanels'
import ConnectionDot from '../components/ConnectionDot'
import TTLKPanel from '../components/TTLKPanel'
import { ReportCard, RumourCard } from '../components/ReportFeed'
import SilencePanel from '../components/SilencePanel'
import UnlockLog from '../components/UnlockLog'
import {
  api,
  MODE_LABEL,
  useLive,
  type Mode,
  type SilenceCase,
  type AfterAction,
  type Block,
  type Brief,
  type FamilyCover,
  type IncidentState,
  type LiveMessage,
  type Report,
  type Rumour,
  type Task,
  type UnlockEntry,
} from '../lib/api'

const FEATURED_RESIDENT = 'tan' // the pitch follows Mdm Tan

export default function Dashboard() {
  const [block, setBlock] = useState<Block | null>(null)
  const [block125, setBlock125] = useState<Block | null>(null)
  const [scene, setScene] = useState('idle')
  const [reports, setReports] = useState<Report[]>([])
  const [crisis, setCrisis] = useState<IncidentState>({ incident: null, ranked: [], tasks: [] })
  const [tanReached, setTanReached] = useState(false)
  const [rumours, setRumours] = useState<Rumour[]>([])
  const [unlocks, setUnlocks] = useState<UnlockEntry[]>([])
  const [crisis125, setCrisis125] = useState<IncidentState>({ incident: null, ranked: [], tasks: [] })
  const [brief, setBrief] = useState<Brief | null>(null)
  const [afterAction, setAfterAction] = useState<AfterAction | null>(null)
  const [family, setFamily] = useState<FamilyCover | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [relay, setRelay] = useState<Record<number, string[]>>({}) // task id -> hops
  const [silence, setSilence] = useState<SilenceCase[]>([])

  const loadCrisis125 = useCallback(() => {
    api.currentIncident(125).then(setCrisis125).catch(() => {})
  }, [])
  const loadFamily = useCallback(() => {
    api.familyCover(123).then(setFamily).catch(() => {})
  }, [])

  const loadUnlocks = useCallback(() => {
    api.unlockLog().then(setUnlocks).catch(() => {})
  }, [])

  const loadCrisis = useCallback(async () => {
    try {
      const c = await api.currentIncident(123)
      setCrisis(c)
      setTanReached(c.tasks.some((t) => t.resident_id === FEATURED_RESIDENT && t.status === 'reached'))
    } catch {
      /* the next live message will retry */
    }
  }, [])

  const load = useCallback(async () => {
    try {
      const [b, b2, rs, rm] = await Promise.all([api.getBlock(123), api.getBlock(125), api.listReports(123), api.listRumours(123)])
      setBlock(b)
      setBlock125(b2)
      setReports(rs)
      setRumours(rm)
      setError(null)
      await loadCrisis()
      loadUnlocks()
      loadCrisis125()
      loadFamily()
      api.silenceCases().then(setSilence).catch(() => {})
      api.brief().then(setBrief).catch(() => {})
      api.afterAction().then(setAfterAction).catch(() => {})
    } catch {
      setError('Cannot reach the backend. Is it running on port 8000?')
    }
  }, [loadCrisis, loadUnlocks, loadCrisis125, loadFamily])

  useEffect(() => {
    load()
  }, [load])

  // Replace or add one task in our list, keeping the rest.
  const upsertTask = (task: Task) =>
    setCrisis((c) => ({
      ...c,
      tasks: c.tasks.some((t) => t.id === task.id) ? c.tasks.map((t) => (t.id === task.id ? task : t)) : [...c.tasks, task],
    }))

  const connected = useLive((msg: LiveMessage) => {
    switch (msg.type) {
      case 'scene':
        setScene(String(msg.name))
        break
      case 'reset':
        setTanReached(false)
        setBrief(null)
        setAfterAction(null)
        setCrisis125({ incident: null, ranked: [], tasks: [] })
        setRelay({})
        load()
        break
      case 'mode_change':
        if (msg.block_id === 123) {
          setCrisis((c) => (c.incident ? { ...c, incident: { ...c.incident, mode: String(msg.mode) } } : c))
          if (msg.mode !== 'relay') setRelay({})
        }
        break
      case 'relay':
        if (msg.block_id === 123) setRelay((r) => ({ ...r, [Number(msg.task_id)]: msg.hops as string[] }))
        break
      case 'silence_case': {
        const c = msg.case as SilenceCase
        setSilence((cs) => [c, ...cs.filter((x) => x.id !== c.id)])
        break
      }
      case 'incident':
      case 'ranking_changed':
        loadCrisis()
        loadUnlocks()
        break
      case 'rumour_flagged':
      case 'rumour_updated': {
        const r = msg.rumour as Rumour
        setRumours((rs) => [r, ...rs.filter((x) => x.id !== r.id)])
        break
      }
      case 'profile_unlocked':
        loadUnlocks()
        break
      case 'report_new':
        setReports((rs) => [msg.report as Report, ...rs.filter((r) => r.id !== (msg.report as Report).id)])
        break
      case 'report_updated': {
        const updated = msg.report as Report
        setReports((rs) => rs.map((r) => (r.id === updated.id ? updated : r)))
        break
      }
      case 'task_new':
      case 'task_updated':
      case 'task_status': {
        const task = msg.task as Task
        if (crisis.incident && task.incident_id !== crisis.incident.id) {
          loadCrisis125() // a Block 125 task
          break
        }
        upsertTask(task)
        if (msg.type === 'task_new') loadUnlocks()
        if (msg.type === 'task_status') {
          if (task.resident_id === FEATURED_RESIDENT && task.status === 'reached') setTanReached(true)
          loadCrisis()
          loadFamily()
        }
        break
      }
      case 'block_alert':
      case 'responders_moved':
        loadCrisis125()
        break
      case 'brief_ready':
        setBrief(msg.brief as Brief)
        loadUnlocks()
        break
      case 'after_action':
        setAfterAction(msg.report as AfterAction)
        break
      case 'family_status':
        loadFamily()
        break
      case 'unit_status': {
        const { block_id, unit, status } = msg as unknown as { block_id: number; unit: string; status: string }
        const patch = (b: Block | null) =>
          b && b.id === block_id
            ? { ...b, units: b.units.map((u) => (u.label === unit ? { ...u, status: status as Block['units'][number]['status'] } : u)) }
            : b
        setBlock(patch)
        setBlock125(patch)
        break
      }
    }
  })

  const inCrisis = !!crisis.incident || (scene !== 'idle' && scene !== 'evening')
  const alert = scene === 'idle' && !inCrisis ? 'none' : inCrisis ? 'red' : 'calm'
  // Highlight the latest report we trust, never a low-trust or rejected one (e.g. the fake report).
  const latestUnit =
    reports.find((r) => r.parsed?.unit && r.trust_level !== 'low' && r.status !== 'rejected')?.parsed?.unit ?? null

  // The latest task per resident (older ones may have been reassigned).
  const latestTask = new Map<string, Task>()
  for (const t of [...crisis.tasks].sort((a, b) => a.id - b.id)) latestTask.set(t.resident_id, t)

  const links: HelperLink[] = [...latestTask.values()]
    .filter((t) => t.helper_unit && t.resident_unit && (t.status === 'sent' || t.status === 'on_the_way'))
    .map((t) => ({ from: t.helper_unit!, to: t.resident_unit!, status: t.status, emphasis: t.resident_id === FEATURED_RESIDENT }))

  const names: Record<string, string> = Object.fromEntries(
    [...(block?.residents ?? []), ...(block125?.residents ?? [])].map((r) => [r.id, r.name]),
  )
  const openRumours = rumours.filter((r) => r.status !== 'dismissed')

  // Relay mode: animate the hops for Mdm Tan's helper if we have them, otherwise any.
  const tanTask = latestTask.get(FEATURED_RESIDENT)
  const relayHops = crisis.incident?.mode === 'relay' ? (tanTask && relay[tanTask.id]) || Object.values(relay)[0] || null : null
  const openSilence = silence.filter((c) => c.status === 'open')
  const mode = (crisis.incident?.mode ?? 'full') as Mode

  const vulnerableCount = crisis.ranked.length
  const reachedCount = [...latestTask.values()].filter((t) => t.status === 'reached').length

  return (
    <div className="min-h-full p-6">
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Kampung Grid <span className="font-normal text-muted">· Authority dashboard</span>
          </h1>
          <p className="text-sm text-muted">Block-level readiness and live status. No individual tracking.</p>
        </div>
        <ConnectionDot connected={connected} />
      </header>

      <SceneBanner scene={scene} crisis={crisis} reached={reachedCount} vulnerable={vulnerableCount} />

      {tanReached && (
        <div className="mb-5 rounded-xl border-2 border-safe bg-safe-soft p-4 text-center">
          <p className="text-xl font-bold text-safe">Mdm Tan reached.</p>
          <p className="text-ink">No one in the block gets forgotten.</p>
        </div>
      )}

      {crisis.incident && mode !== 'full' && <ModeStrip mode={mode} />}

      {error && <div className="mb-4 rounded-lg bg-danger-soft p-3 text-danger">{error}</div>}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[auto_1fr]">
        <div className="flex flex-col gap-6">
        <section className="rounded-2xl bg-panel p-5 shadow-sm">
          {block ? (
            <BlockView
              block={block}
              alert={alert}
              highlightUnit={latestUnit}
              links={links}
              relay={relayHops}
              ringUnits={openSilence.map((c) => c.unit).filter((u): u is string => !!u)}
            />
          ) : (
            <p className="text-muted">Loading block...</p>
          )}
          <div className="mt-4">
            <BlockLegend />
          </div>
          {crisis.incident && (
            <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 rounded-xl bg-canvas px-4 py-2 text-sm">
              <span>
                Residents reached <b>{reachedCount}/{vulnerableCount}</b>
              </span>
              {family && family.workers > 0 && (
                <span>
                  Essential workers <b>{family.workers}</b> · families covered{' '}
                  <b>
                    {family.covered}/{family.with_family}
                  </b>
                </span>
              )}
              <span>
                Low-trust reports waiting <b>{reports.filter((r) => r.status === 'waiting_for_human').length}</b>
              </span>
              <span>
                Mode <b>{MODE_LABEL[mode]}</b>
              </span>
            </div>
          )}
        </section>

          {block125 && <Block125Card block={block125} crisis={crisis125} />}
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          {silence.length > 0 && <SilencePanel cases={silence} />}
          {afterAction && <AfterActionReport report={afterAction} />}
          {afterAction && <TTLKPanel highlight />}
          {brief && !afterAction && <HandoverBrief brief={brief} onClose={() => setBrief(null)} />}
          {crisis.incident && !afterAction ? <RankedList crisis={crisis} latestTask={latestTask} /> : !afterAction && <TTLKPanel />}

          <section className="rounded-2xl bg-panel p-5 shadow-sm">
            <h2 className="mb-1 text-lg font-semibold">Live reports</h2>
            <p className="mb-3 text-sm text-muted">Every report gets a trust check. Low trust waits for a human.</p>
            {openRumours.length > 0 && (
              <div className="mb-3 flex flex-col gap-3">
                {openRumours.map((r) => (
                  <RumourCard key={r.id} rumour={r} />
                ))}
              </div>
            )}
            {reports.length === 0 ? (
              <p className="text-sm text-muted">No reports yet.</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {reports.slice(0, 6).map((r) => (
                  <ReportCard key={r.id} report={r} />
                ))}
              </ul>
            )}
          </section>

          <UnlockLog entries={unlocks} names={names} />


        </div>
      </div>
    </div>
  )
}

const MODE_NOTE: Record<Mode, string> = {
  full: '',
  low_data: 'Mobile data is down. Instructions now go out as SMS (160 characters, reply 1 or 2).',
  relay: 'No mobile network. Messages pass phone to phone up the stairwells (simulated in this prototype).',
  no_phone: 'Phones are down. Residents use the printed block card in each lift lobby.',
}

function ModeStrip({ mode }: { mode: Mode }) {
  return (
    <div className={`mb-5 rounded-xl p-3 text-sm font-medium ${mode === 'low_data' ? 'bg-warn-soft text-warn' : 'bg-danger-soft text-danger'}`}>
      <b>Network: {MODE_LABEL[mode]}.</b> {MODE_NOTE[mode]}
      {mode === 'no_phone' && (
        <a href="/print/block/123" target="_blank" className="ml-2 underline">
          Open the block card
        </a>
      )}
    </div>
  )
}

function SceneBanner({
  scene,
  crisis,
  reached,
  vulnerable,
}: {
  scene: string
  crisis: IncidentState
  reached: number
  vulnerable: number
}) {
  if (crisis.incident) {
    return (
      <div className="mb-5 flex items-center justify-between rounded-xl bg-danger p-4 text-white">
        <span className="text-lg font-semibold">
          Crisis mode · Grid cyberattack · Block 123 power out, lifts stopped
        </span>
        {vulnerable > 0 && crisis.tasks.length > 0 && (
          <span className="rounded-full bg-white/20 px-3 py-1 font-semibold">
            {reached}/{vulnerable} vulnerable residents reached
          </span>
        )}
      </div>
    )
  }
  if (scene === 'evening') {
    return <div className="mb-5 rounded-xl bg-safe-soft p-3 font-medium text-safe">9:00pm · Normal evening · All systems normal</div>
  }
  return (
    <div className="mb-5 rounded-xl border border-line bg-panel p-3 text-muted">
      Waiting to start. Press “Start evening” on the control panel.
    </div>
  )
}

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  sent: { text: 'Helper alerted', className: 'bg-warn-soft text-warn' },
  on_the_way: { text: 'On the way', className: 'bg-warn-soft text-warn' },
  reached: { text: 'Reached', className: 'bg-safe-soft text-safe' },
  need_help: { text: 'Helper needs help', className: 'bg-danger-soft text-danger' },
  escalated: { text: 'Escalated to SCDF', className: 'bg-danger-soft text-danger' },
  reassigned: { text: 'Reassigned', className: 'bg-canvas text-muted' },
  responder_en_route: { text: 'Responders on the way', className: 'bg-warn-soft text-warn' },
}

function RankedList({ crisis, latestTask }: { crisis: IncidentState; latestTask: Map<string, Task> }) {
  return (
    <section className="rounded-2xl bg-panel p-5 shadow-sm">
      <h2 className="text-lg font-semibold">Who needs a knock first</h2>
      <p className="mb-3 text-sm text-muted">Ranked by risk. Each line shows why. Helpers are matched by distance and skills.</p>
      <ol className="flex flex-col gap-2">
        {crisis.ranked.map((r) => {
          const task = latestTask.get(r.resident_id)
          const status = task ? STATUS_LABEL[task.status] : null
          const reached = r.reached || task?.status === 'reached'
          return (
            <li
              key={r.resident_id}
              className={`flex items-start gap-3 rounded-xl border p-3 ${
                r.resident_id === FEATURED_RESIDENT && !reached ? 'border-danger' : 'border-line'
              } ${reached ? 'bg-safe-soft/40 opacity-80' : ''}`}
            >
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                  reached ? 'bg-safe text-white' : r.rank === 1 ? 'bg-danger text-white' : 'bg-canvas text-ink'
                }`}
              >
                {reached ? '✓' : r.rank}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">
                    {r.name} <span className="font-normal text-muted">{r.unit}</span>
                  </p>
                  {status && <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${status.className}`}>{status.text}</span>}
                </div>
                <p className="text-sm text-muted">{r.reasons.join(' · ')}</p>
                {task?.helper_name && task.status !== 'reassigned' && (
                  <p className="mt-1 text-sm">
                    Helper: <span className="font-medium">{task.helper_name}</span> ({task.helper_unit})
                    {task.via === 'telegram' || task.via === 'web' ? (
                      <span className="ml-1.5 rounded-full bg-brand px-2 py-0.5 text-xs font-semibold text-white">
                        real person · {task.via === 'telegram' ? 'Telegram' : 'phone'}
                      </span>
                    ) : task.simulated ? (
                      <span className="ml-1 text-xs text-muted">· simulated neighbour</span>
                    ) : null}
                  </p>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
