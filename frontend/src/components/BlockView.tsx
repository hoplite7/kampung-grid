// A side view of an HDB block: one row per floor (top floor at the top),
// one box per unit, the two stairwells as narrow columns.
// Colours come from each unit's live status. Never shows medical details.

import type { Block, BlockResident, Unit } from '../lib/api'

const UNIT_W = 44
const UNIT_H = 30
const GAP = 4
const LABEL_W = 44
const STAIR_W = 22
const TOP = 30

const STATUS_FILL: Record<string, string> = {
  normal: '#ffffff',
  task_sent: 'var(--color-warn-soft)',
  reached: 'var(--color-safe-soft)',
  escalated: 'var(--color-danger-soft)',
}
const STATUS_STROKE: Record<string, string> = {
  normal: 'var(--color-line)',
  task_sent: 'var(--color-warn)',
  reached: 'var(--color-safe)',
  escalated: 'var(--color-danger)',
}

/** A line from a helper's unit to the resident they're going to check on. */
export interface HelperLink {
  from: string // helper's unit, e.g. "#07-10"
  to: string // resident's unit, e.g. "#09-12"
  status: string // sent, on_the_way
  emphasis?: boolean
}

interface Props {
  block: Block
  /** Outline colour for the whole block: green (calm), amber, red (crisis). */
  alert?: 'none' | 'calm' | 'amber' | 'red'
  highlightUnit?: string | null
  compact?: boolean
  links?: HelperLink[]
  /** Relay mode: the phones a message hopped through, from the void deck up (simulated). */
  relay?: string[] | null
  /** Units to ring in amber (Silence Alert). Unit numbers only. */
  ringUnits?: string[]
}

export default function BlockView({ block, alert = 'none', highlightUnit, compact, links = [], relay = null, ringUnits = [] }: Props) {
  const scale = compact ? 0.62 : 1
  const byLabel = new Map(block.units.map((u) => [u.label, u]))
  const peopleByUnit = new Map<string, BlockResident[]>()
  for (const r of block.residents) {
    peopleByUnit.set(r.unit, [...(peopleByUnit.get(r.unit) ?? []), r])
  }

  // Lay units out stairwell by stairwell, with a stair column before each group.
  const groups = Object.entries(block.stairwells).sort(([a], [b]) => a.localeCompare(b))
  const columns: ({ kind: 'stair'; name: string } | { kind: 'unit'; number: number })[] = []
  for (const [name, numbers] of groups) {
    columns.push({ kind: 'stair', name })
    for (const n of [...numbers].sort((a, b) => a - b)) columns.push({ kind: 'unit', number: n })
  }

  const xOf: number[] = []
  let x = LABEL_W
  for (const c of columns) {
    xOf.push(x)
    x += (c.kind === 'stair' ? STAIR_W : UNIT_W) + GAP
  }
  const width = x + 8
  const height = TOP + block.floors * (UNIT_H + GAP) + 24
  const yOfFloor = (floor: number) => TOP + (block.floors - floor) * (UNIT_H + GAP)

  const outline =
    alert === 'red' ? 'var(--color-danger)' : alert === 'amber' ? 'var(--color-warn)' : alert === 'calm' ? 'var(--color-safe)' : 'var(--color-line)'

  // Centre point of each unit, for drawing helper lines.
  const centre = (label: string): [number, number] | null => {
    const unit = byLabel.get(label)
    if (!unit) return null
    const ci = columns.findIndex((c) => c.kind === 'unit' && c.number === unit.number)
    if (ci < 0) return null
    return [xOf[ci] + UNIT_W / 2, yOfFloor(unit.floor) + UNIT_H / 2]
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width * scale}
      style={{ maxWidth: '100%', height: 'auto' }}
      role="img"
      aria-label={`${block.name}, ${block.floors} floors`}
    >
      {/* Building outline: its colour shows the block's overall state */}
      <rect
        x={LABEL_W - 8}
        y={TOP - 10}
        width={width - LABEL_W + 2}
        height={block.floors * (UNIT_H + GAP) + 16}
        rx={10}
        fill="none"
        stroke={outline}
        strokeWidth={alert === 'none' ? 1.5 : 4}
        style={{ transition: 'stroke 0.8s ease' }}
      />
      <text x={LABEL_W - 8} y={16} fontSize={14} fontWeight={700} fill="var(--color-ink)">
        {block.name}
      </text>

      {Array.from({ length: block.floors }, (_, i) => block.floors - i).map((floor) => {
        const y = yOfFloor(floor)
        return (
          <g key={floor}>
            <text x={LABEL_W - 14} y={y + UNIT_H / 2 + 4} fontSize={11} textAnchor="end" fill="var(--color-muted)">
              {String(floor).padStart(2, '0')}
            </text>
            {columns.map((c, ci) => {
              if (c.kind === 'stair') {
                return (
                  <rect key={`s${ci}`} x={xOf[ci]} y={y} width={STAIR_W} height={UNIT_H} fill="#e2e8f0" rx={3} />
                )
              }
              const label = `#${String(floor).padStart(2, '0')}-${String(c.number).padStart(2, '0')}`
              const unit = byLabel.get(label)
              return unit ? (
                <UnitBox
                  key={label}
                  unit={unit}
                  people={peopleByUnit.get(label) ?? []}
                  x={xOf[ci]}
                  y={y}
                  highlighted={highlightUnit === label}
                />
              ) : null
            })}
          </g>
        )
      })}

      {/* Helper -> resident lines, drawn on top of the units */}
      <defs>
        <marker id={`arrow-${block.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill="var(--color-warn)" />
        </marker>
      </defs>
      {links.map((l) => {
        const a = centre(l.from)
        const b = centre(l.to)
        if (!a || !b) return null
        return (
          <line
            key={`${l.from}-${l.to}`}
            x1={a[0]}
            y1={a[1]}
            x2={b[0]}
            y2={b[1]}
            stroke="var(--color-warn)"
            strokeWidth={l.emphasis ? 3.5 : 2}
            strokeDasharray={l.status === 'sent' ? '6 4' : undefined}
            markerEnd={`url(#arrow-${block.id})`}
            opacity={0.9}
          />
        )
      })}

      {/* Silence Alert: amber ring around the unit */}
      {ringUnits.map((label) => {
        const c = centre(label)
        return c ? (
          <rect
            key={`ring-${label}`}
            x={c[0] - UNIT_W / 2 - 4}
            y={c[1] - UNIT_H / 2 - 4}
            width={UNIT_W + 8}
            height={UNIT_H + 8}
            rx={6}
            fill="none"
            stroke="var(--color-warn)"
            strokeWidth={3}
          >
            <animate attributeName="opacity" values="1;0.35;1" dur="1.6s" repeatCount="indefinite" />
          </rect>
        ) : null
      })}

      {/* Relay mode: hops from the void deck up through neighbours' phones */}
      {relay && relay.length > 0 && (() => {
        const pts = relay.map(centre).filter((p): p is [number, number] => !!p)
        if (pts.length === 0) return null
        const start: [number, number] = [pts[0][0], height - 18]
        const all = [start, ...pts]
        const path = all.map((p) => p.join(',')).join(' ')
        const total = all.slice(1).reduce((d, p, i) => d + Math.hypot(p[0] - all[i][0], p[1] - all[i][1]), 0)
        return (
          <g key={relay.join('>')}>
            <polyline
              points={path}
              fill="none"
              stroke="var(--color-brand)"
              strokeWidth={3}
              strokeDasharray={total}
              strokeDashoffset={total}
              strokeLinecap="round"
            >
              <animate attributeName="stroke-dashoffset" from={total} to={0} dur={`${0.9 * pts.length}s`} fill="freeze" />
            </polyline>
            {pts.map((p, i) => (
              <circle key={i} cx={p[0]} cy={p[1]} r={0} fill="var(--color-brand)">
                <animate attributeName="r" from="0" to="7" begin={`${0.9 * (i + 1)}s`} dur="0.3s" fill="freeze" />
              </circle>
            ))}
            <text x={width - 8} y={16} fontSize={12} fontWeight={700} textAnchor="end" fill="var(--color-brand)">
              Relay: phone to phone (simulated)
            </text>
          </g>
        )
      })()}

      {/* Stairwell names under their columns */}
      {columns.map((c, ci) =>
        c.kind === 'stair' ? (
          <text key={`sl${ci}`} x={xOf[ci] + STAIR_W / 2} y={height - 6} fontSize={11} textAnchor="middle" fill="var(--color-muted)">
            {c.name}
          </text>
        ) : null,
      )}
    </svg>
  )
}

function UnitBox({
  unit,
  people,
  x,
  y,
  highlighted,
}: {
  unit: Unit
  people: BlockResident[]
  x: number
  y: number
  highlighted: boolean
}) {
  const vulnerable = people.some((p) => p.is_vulnerable)
  const helper = people.find((p) => p.is_helper)
  const status = unit.status ?? 'normal'
  const tooltip = [
    unit.label,
    unit.occupied ? null : 'vacant',
    vulnerable ? 'vulnerable resident' : null,
    helper ? `helper${helper.helper_skills.length ? ` (${helper.helper_skills.join(', ').replace('_', ' ')})` : ''}` : null,
    status !== 'normal' ? status.replace('_', ' ') : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <g>
      <title>{tooltip}</title>
      <rect
        x={x}
        y={y}
        width={UNIT_W}
        height={UNIT_H}
        rx={4}
        fill={unit.occupied ? STATUS_FILL[status] : '#f8fafc'}
        stroke={highlighted ? 'var(--color-ink)' : vulnerable && status === 'normal' ? 'var(--color-brand)' : STATUS_STROKE[status]}
        strokeWidth={highlighted ? 3 : vulnerable || status !== 'normal' ? 2 : 1}
        strokeDasharray={unit.occupied ? undefined : '3 3'}
        style={{ transition: 'fill 0.5s ease, stroke 0.5s ease' }}
      />
      {vulnerable && (
        // A small heart-ish marker: "someone here may need help". No details.
        <circle cx={x + UNIT_W - 8} cy={y + 8} r={4} fill="var(--color-brand)" />
      )}
      {helper && (
        <circle
          cx={x + 9}
          cy={y + UNIT_H - 9}
          r={4.5}
          fill={helper.helper_skills.includes('cpr') || helper.helper_skills.includes('first_aid') ? 'var(--color-ink)' : '#ffffff'}
          stroke="var(--color-ink)"
          strokeWidth={1.5}
        />
      )}
      {status === 'reached' && (
        <path d={`M${x + 15} ${y + 15} l5 5 l10 -10`} stroke="var(--color-safe)" strokeWidth={3} fill="none" />
      )}
    </g>
  )
}

export function BlockLegend() {
  const item = (swatch: React.ReactNode, text: string) => (
    <div className="flex items-center gap-2">
      <svg width={22} height={16}>{swatch}</svg>
      <span>{text}</span>
    </div>
  )
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted">
      {item(<><rect x={1} y={1} width={20} height={14} rx={3} fill="#fff" stroke="var(--color-brand)" strokeWidth={2} /><circle cx={16} cy={5} r={3} fill="var(--color-brand)" /></>, 'Vulnerable resident')}
      {item(<><rect x={1} y={1} width={20} height={14} rx={3} fill="#fff" stroke="var(--color-line)" /><circle cx={6} cy={10} r={3.5} fill="var(--color-ink)" /></>, 'Trained helper')}
      {item(<><rect x={1} y={1} width={20} height={14} rx={3} fill="#fff" stroke="var(--color-line)" /><circle cx={6} cy={10} r={3.5} fill="#fff" stroke="var(--color-ink)" strokeWidth={1.5} /></>, 'Helper (no training)')}
      {item(<rect x={1} y={1} width={20} height={14} rx={3} fill="#f8fafc" stroke="var(--color-line)" strokeDasharray="3 3" />, 'Vacant')}
      {item(<rect x={1} y={1} width={20} height={14} rx={3} fill="var(--color-warn-soft)" stroke="var(--color-warn)" strokeWidth={2} />, 'Helper on the way')}
      {item(<rect x={1} y={1} width={20} height={14} rx={3} fill="var(--color-safe-soft)" stroke="var(--color-safe)" strokeWidth={2} />, 'Reached')}
      {item(<rect x={1} y={1} width={20} height={14} rx={3} fill="var(--color-danger-soft)" stroke="var(--color-danger)" strokeWidth={2} />, 'Not reached / escalated')}
    </div>
  )
}
