// Small "live" indicator so we can see at a glance if a screen lost the backend.
export default function ConnectionDot({ connected }: { connected: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" title={connected ? 'Live updates connected' : 'Reconnecting...'}>
      <span className={`h-2.5 w-2.5 rounded-full ${connected ? 'bg-safe' : 'bg-danger animate-pulse'}`} />
      {connected ? 'Live' : 'Reconnecting'}
    </span>
  )
}
