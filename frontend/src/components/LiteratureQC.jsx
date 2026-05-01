const SIGNAL_CONFIG = {
  not_found: {
    label: 'Novel territory',
    summary: "No matching prior work — you may be breaking new ground.",
    tone: 'success',
    icon: '🌱',
  },
  similar_exists: {
    label: 'Similar work exists',
    summary: 'Related protocols found — the plan should build on prior art.',
    tone: 'warn',
    icon: '🔗',
  },
  exact_match: {
    label: 'Exact match found',
    summary: 'A very similar experiment appears to be published.',
    tone: 'danger',
    icon: '⚠',
  },
}

const TONE_CLASSES = {
  success: 'border-success-200 dark:border-success-900 bg-success-50 dark:bg-success-900/30',
  warn:    'border-warn-200 dark:border-warn-900 bg-warn-50 dark:bg-warn-900/30',
  danger:  'border-danger-200 dark:border-danger-900 bg-danger-50 dark:bg-danger-900/30',
}
const TONE_TEXT = {
  success: 'text-success-800',
  warn:    'text-warn-800',
  danger:  'text-danger-800',
}
const TONE_ICON_BG = {
  success: 'bg-success-100 text-success-700',
  warn:    'bg-warn-100 text-warn-700',
  danger:  'bg-danger-100 text-danger-700',
}

const SOURCE_LABELS = {
  openalex: 'OpenAlex',
  tavily: 'Tavily',
  semantic_scholar: 'Semantic Scholar',
  demo: 'Curated example',
}

export default function LiteratureQC({ result, onGeneratePlan, isLoading, disabled }) {
  const config = SIGNAL_CONFIG[result.signal] || SIGNAL_CONFIG.not_found
  const explanation = (result.explanation || '').trim()
  const refs = result.references || []

  return (
    <div className="card animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>Literature quality control</h2>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-subtle)' }}>
            Plagiarism check, but for science. Fast novelty signal + 1–3 references.
          </p>
        </div>
        <span className="pill-neutral">Step 2</span>
      </div>

      {/* Signal panel */}
      <div className={`rounded-xl2 border p-4 ${TONE_CLASSES[config.tone]}`}>
        <div className="flex items-start gap-3">
          <div className={`w-9 h-9 rounded-full flex items-center justify-center text-lg ${TONE_ICON_BG[config.tone]}`}>
            <span aria-hidden="true">{config.icon}</span>
          </div>
          <div className="flex-1">
            <div className={`text-sm font-semibold ${TONE_TEXT[config.tone]}`}>{config.label}</div>
            <p className={`text-xs mt-0.5 ${TONE_TEXT[config.tone]}`}>
              {config.summary}
            </p>
            {explanation && (
              <p className="text-xs mt-2 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
                <span className="font-semibold" style={{ color: 'var(--color-text-muted)' }}>Why:</span> {explanation}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* References */}
      <div className="mt-5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="label">References ({refs.length})</h3>
        </div>
        {refs.length > 0 ? (
          <ul className="space-y-2">
            {refs.map((ref, i) => {
              const sourceLabel = ref.source ? SOURCE_LABELS[ref.source] || ref.source : null
              const yearText = ref.year && ref.year > 0 ? ref.year : 'n.d.'
              return (
                <li
                  key={i}
                  className="rounded-lg border hover:shadow-card-hover transition-all" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-bg-elevated)' }}
                >
                  <a
                    href={ref.url || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block p-3 focus-ring"
                  >
                    <p className="text-sm font-medium leading-snug line-clamp-2" style={{ color: 'var(--color-text)' }}>
                      {ref.title || 'Untitled'}
                    </p>
                    <p className="text-xs mt-1" style={{ color: 'var(--color-text-subtle)' }}>
                      {ref.authors || 'Unknown authors'} · {yearText}
                    </p>
                    {sourceLabel && (
                      <span className="pill-neutral mt-2 text-[10px]">
                        via {sourceLabel}
                      </span>
                    )}
                  </a>
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="rounded-lg border border-dashed px-3 py-4 text-xs text-center" style={{ color: 'var(--color-text-subtle)', borderColor: 'var(--color-border)' }}>
            No references retrieved. The plan generator will still proceed.
          </div>
        )}
      </div>

      <button
        onClick={onGeneratePlan}
        disabled={isLoading || disabled}
        className="btn-primary-lg w-full mt-5"
      >
        {isLoading ? (
          <>
            <span className="pill-dot bg-white/80 animate-pulse-dot" />
            Generating plan…
          </>
        ) : disabled ? (
          'Plan generated below ↓'
        ) : (
          <>Generate full experiment plan →</>
        )}
      </button>
    </div>
  )
}
