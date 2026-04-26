export default function ProtocolCard({ protocol }) {
  if (!protocol || protocol.length === 0) {
    return <EmptyState>No protocol steps available.</EmptyState>
  }

  return (
    <ol className="relative">
      {protocol.map((step, index) => (
        <li key={index} className="protocol-step">
          <span className="protocol-dot">{step.step || index + 1}</span>
          <div>
            <h4 className="text-sm font-semibold text-ink-900 leading-snug">
              {step.title || `Step ${index + 1}`}
            </h4>
            {step.description && (
              <p className="mt-1.5 text-sm text-slate-700 leading-relaxed">
                {step.description}
              </p>
            )}
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              {step.duration && (
                <span className="pill-neutral">
                  <ClockIcon /> {step.duration}
                </span>
              )}
              {step.source && (
                <span className="pill-accent">
                  <BookIcon /> {step.source}
                </span>
              )}
            </div>
            {step.safety_note && (
              <div className="mt-3 rounded-lg border-l-4 border-warn-500 bg-warn-50 px-3 py-2">
                <p className="text-[11px] font-bold text-warn-800 uppercase tracking-wide">Safety</p>
                <p className="text-xs text-warn-800 mt-0.5 leading-relaxed">{step.safety_note}</p>
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

function EmptyState({ children }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
      {children}
    </div>
  )
}

function ClockIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  )
}

function BookIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 4h11a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4V4z" />
      <path d="M4 16a4 4 0 0 1 4-4h11" />
    </svg>
  )
}
