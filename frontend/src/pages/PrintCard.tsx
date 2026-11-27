// The printed block card: the fallback when phones are dead.
// Stuck in every lift lobby. Unit numbers only: no names, no medical details.
// Open /print/block/123 and press Print (or Ctrl/Cmd + P).

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, type BlockCard } from '../lib/api'

const SKILL_ICON: Record<string, string> = { cpr: '❤️ CPR', first_aid: '✚ First aid' }

export default function PrintCard() {
  const { id } = useParams()
  const [card, setCard] = useState<BlockCard | null>(null)
  useEffect(() => {
    api.blockCard(Number(id ?? 123)).then(setCard).catch(() => setCard(null))
  }, [id])

  if (!card) return <p className="p-8 text-muted">Loading block card...</p>

  return (
    <div className="print-card mx-auto max-w-[190mm] bg-white p-8 text-ink">
      <div className="no-print mb-6 flex items-center justify-between rounded-xl bg-canvas p-3 text-sm">
        <span>This is the card for the lift lobby. It has unit numbers only.</span>
        <button onClick={() => window.print()} className="rounded-lg bg-brand px-4 py-2 font-semibold text-white">
          Print
        </button>
      </div>

      <header className="mb-6 border-b-4 border-ink pb-3">
        <p className="text-sm font-bold uppercase tracking-widest">Kampung Grid · {card.block}</p>
        <h1 className="text-4xl font-black leading-tight">If the power and phones are down</h1>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-4">
        <div className="rounded-xl border-4 border-danger p-4 text-center">
          <p className="text-lg font-bold">Fire / ambulance</p>
          <p className="text-6xl font-black text-danger">995</p>
        </div>
        <div className="rounded-xl border-4 border-ink p-4 text-center">
          <p className="text-lg font-bold">Police</p>
          <p className="text-6xl font-black">999</p>
        </div>
      </div>

      <section className="mb-6">
        <h2 className="mb-1 text-2xl font-black">1. Knock on these doors first</h2>
        <p className="mb-3 text-base">These neighbours may need help to get out. Go in this order. Use the stairs.</p>
        <ol className="grid grid-cols-3 gap-3">
          {card.knock_first.map((u, i) => (
            <li key={u} className="flex items-center gap-3 rounded-xl border-2 border-ink p-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-ink text-lg font-bold text-white">{i + 1}</span>
              <span className="text-2xl font-black">{u}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="mb-6">
        <h2 className="mb-1 text-2xl font-black">2. Helpers in this block</h2>
        <p className="mb-3 text-base">Neighbours who signed up to help. Ask them to come with you.</p>
        <ul className="grid grid-cols-3 gap-3">
          {card.helpers.map((h) => (
            <li key={h.unit} className="rounded-xl border-2 border-line p-3">
              <p className="text-2xl font-black">{h.unit}</p>
              <p className="text-sm">{h.skills.length ? h.skills.map((s) => SKILL_ICON[s] ?? s).join(' · ') : 'Helper'}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="mb-6 rounded-xl bg-canvas p-4 text-base">
        <h2 className="mb-1 text-xl font-black">3. Meet at the void deck</h2>
        <p>Tell the first SCDF officer which doors were knocked and who still needs help.</p>
      </section>

      <footer className="border-t-2 border-line pt-2 text-xs text-muted">
        Sample card · {card.updated}. No names or medical details are printed on this card.
      </footer>
    </div>
  )
}
