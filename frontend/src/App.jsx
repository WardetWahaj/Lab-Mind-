import { useEffect, useState } from 'react'
import HypothesisInput from './components/HypothesisInput'
import LiteratureQC from './components/LiteratureQC'
import ExperimentPlan from './components/ExperimentPlan'

const STAGES = [
  { id: 'input', label: 'Hypothesis' },
  { id: 'qc', label: 'Literature QC' },
  { id: 'plan', label: 'Experiment Plan' },
]

function getActiveStage(state) {
  if (state === 'idle') return 'input'
  if (state === 'qc_running') return 'qc'
  if (state === 'qc_done') return 'qc'
  if (state === 'generating') return 'plan'
  if (state === 'done') return 'plan'
  return 'input'
}

function getStageStatus(stageId, state) {
  const order = ['input', 'qc', 'plan']
  const stageIdx = order.indexOf(stageId)
  const currentIdx = order.indexOf(getActiveStage(state))

  if (stageId === 'input') {
    if (state === 'idle') return 'active'
    return 'done'
  }
  if (stageId === 'qc') {
    if (state === 'qc_running') return 'active'
    if (state === 'qc_done') return 'active'
    if (state === 'generating' || state === 'done') return 'done'
    return 'upcoming'
  }
  if (stageId === 'plan') {
    if (state === 'generating') return 'active'
    if (state === 'done') return 'active'
    return 'upcoming'
  }
  return stageIdx < currentIdx ? 'done' : 'upcoming'
}

export default function App() {
  const [state, setState] = useState('idle') // idle | qc_running | qc_done | generating | done
  const [hypothesis, setHypothesis] = useState('')
  const [qcResult, setQcResult] = useState(null)
  const [planData, setPlanData] = useState(null)
  const [error, setError] = useState(null)
  const [lastFeedbackApplied, setLastFeedbackApplied] = useState(null)

  const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  // Auto-dismiss the error toast after a few seconds.
  useEffect(() => {
    if (!error) return
    const t = setTimeout(() => setError(null), 6000)
    return () => clearTimeout(t)
  }, [error])

  const handleCheckLiterature = async (hyp) => {
    setHypothesis(hyp)
    setError(null)
    setQcResult(null)
    setPlanData(null)
    setState('qc_running')

    try {
      const response = await fetch(`${API_BASE}/api/literature-qc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hypothesis: hyp })
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail.detail || `Literature QC failed (${response.status})`)
      }

      const data = await response.json()
      setQcResult(data)
      setState('qc_done')
    } catch (err) {
      setError(err.message || 'Literature check failed.')
      setState('idle')
    }
  }

  const handleGeneratePlan = async () => {
    setError(null)
    setState('generating')

    try {
      const response = await fetch(`${API_BASE}/api/generate-plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hypothesis, feedback_context: [] })
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail.detail || `Plan generation failed (${response.status})`)
      }

      const data = await response.json()
      setPlanData(data)
      setState('done')
    } catch (err) {
      setError(err.message || 'Plan generation failed.')
      setState('qc_done')
    }
  }

  const handleFeedbackSaved = (experimentType, corrections) => {
    const correctionTexts = corrections && typeof corrections === 'object'
      ? Object.values(corrections)
          .map((entry) => {
            if (!entry) return ''
            if (typeof entry === 'string') return entry.trim()
            if (typeof entry === 'object' && typeof entry.correction === 'string') {
              return entry.correction.trim()
            }
            return ''
          })
          .filter(Boolean)
      : []
    const summary = correctionTexts.length
      ? `Saved correction applied: ${correctionTexts[0]}`
      : `Plan improved using feedback for ${experimentType || 'this experiment type'}`
    setLastFeedbackApplied(summary)
  }

  const handleStartOver = () => {
    setState('idle')
    setHypothesis('')
    setQcResult(null)
    setPlanData(null)
    setError(null)
    setLastFeedbackApplied(null)
  }

  return (
    <div className="min-h-screen bg-paper text-ink-800">
      <Header onStartOver={handleStartOver} canReset={state !== 'idle'} />

      {/* Stage stepper */}
      <div className="border-b border-slate-200 bg-white">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
          <Stepper state={state} />
          <LearningLoopBanner />
        </div>
      </div>

      {/* Error toast */}
      {error && (
        <div className="toast toast-error" role="alert">
          <div className="text-danger-700 mt-0.5">!</div>
          <div className="flex-1">
            <p className="text-sm font-semibold text-danger-800">Something went wrong</p>
            <p className="text-xs text-danger-700 mt-0.5">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="text-danger-500 hover:text-danger-700 text-sm" aria-label="Dismiss">×</button>
        </div>
      )}

      {/* Main grid */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {state === 'idle' && (
          <Hero />
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
          {/* Left column: input + literature QC */}
          <section className="lg:col-span-5 space-y-5">
            <HypothesisInput
              onCheckLiterature={handleCheckLiterature}
              isLoading={state === 'qc_running' || state === 'generating'}
              value={hypothesis}
              disabled={state === 'generating'}
            />

            {state === 'qc_running' && <QCSkeleton />}

            {(state === 'qc_done' || state === 'generating' || state === 'done') && qcResult && (
              <LiteratureQC
                result={qcResult}
                onGeneratePlan={handleGeneratePlan}
                isLoading={state === 'generating'}
                disabled={state === 'generating' || state === 'done'}
              />
            )}
          </section>

          {/* Right column: experiment plan */}
          <section className="lg:col-span-7">
            {state === 'idle' && <EmptyPlanState />}
            {state === 'qc_running' && <EmptyPlanState muted />}
            {state === 'qc_done' && <ReadyPlanState onGenerate={handleGeneratePlan} />}
            {state === 'generating' && <PlanGeneratingState />}
            {state === 'done' && planData && (
              <ExperimentPlan
                data={planData}
                hypothesis={hypothesis}
                lastFeedbackApplied={lastFeedbackApplied}
                onFeedbackSaved={handleFeedbackSaved}
              />
            )}
          </section>
        </div>
      </main>

      <Footer />
    </div>
  )
}

// ----------------------------------------------------------------------------
// Sub-components
// ----------------------------------------------------------------------------

function Header({ onStartOver, canReset }) {
  return (
    <header className="bg-ink-900 text-white">
      <div className="max-w-6xl mx-auto px-4 py-5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Logo />
          <div className="leading-tight">
            <div className="text-base sm:text-lg font-bold tracking-tight">Lab Mind</div>
            <div className="text-[11px] sm:text-xs text-ink-300 font-medium">From hypothesis to runnable experiment plan</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden sm:inline text-[11px] text-ink-300 uppercase tracking-wider">Powered by</span>
          <span className="text-xs text-white font-semibold">Fulcrum Science</span>
          {canReset && (
            <button onClick={onStartOver} className="ml-3 text-xs text-ink-200 hover:text-white border border-ink-700 hover:border-ink-300 rounded-md px-3 py-1.5 transition-colors">
              ↻ Start over
            </button>
          )}
        </div>
      </div>
    </header>
  )
}

function Logo() {
  return (
    <div className="w-9 h-9 rounded-lg bg-accent-600 flex items-center justify-center text-white font-bold tracking-tighter shadow-sm">
      AI
    </div>
  )
}

function Stepper({ state }) {
  return (
    <ol className="stepper" aria-label="Workflow progress">
      {STAGES.map((stage, idx) => {
        const status = getStageStatus(stage.id, state)
        const circleClass =
          status === 'active' ? 'stepper-state-active' :
          status === 'done'   ? 'stepper-state-done'   : 'stepper-state-upcoming'
        const labelClass =
          status === 'active' ? 'stepper-label-active' :
          status === 'done'   ? 'stepper-label-done'   : 'stepper-label-upcoming'
        return (
          <li key={stage.id} className="stepper-item">
            <span className={`stepper-circle ${circleClass}`}>{status === 'done' ? '✓' : idx + 1}</span>
            <span className={labelClass}>{stage.label}</span>
            {idx < STAGES.length - 1 && (
              <span className={`stepper-rail ${status === 'done' ? 'stepper-rail-done' : ''}`} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function LearningLoopBanner() {
  return (
    <div className="hidden md:flex items-center gap-2 text-[11px] text-success-700">
      <span className="pill-dot bg-success-500 animate-pulse-dot" />
      <span className="font-medium">Live learning loop:</span>
      <span className="text-success-700/90">Expert feedback is reused to improve the next plan.</span>
    </div>
  )
}

function Hero() {
  return (
    <div className="mb-8 max-w-3xl">
      <div className="pill-accent mb-4">
        <span className="pill-dot bg-accent-500" />
        Hackathon · Challenge 04
      </div>
      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-ink-900">
        Turn a scientific question into a plan a lab can run on Monday.
      </h1>
      <p className="mt-3 text-slate-600 leading-relaxed">
        Enter a hypothesis. We scan the literature for prior work, then generate a complete,
        operationally grounded experiment plan — protocol, materials with catalog numbers,
        realistic budget, timeline, and validation criteria.
      </p>
    </div>
  )
}

function QCSkeleton() {
  return (
    <div className="card animate-fade-in">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-4 uppercase tracking-wider">
        <span className="pill-dot bg-accent-500 animate-pulse-dot" />
        Scanning OpenAlex, Tavily &amp; Semantic Scholar
      </div>
      <div className="space-y-3">
        <div className="skeleton h-5 w-2/3"></div>
        <div className="skeleton h-3 w-full"></div>
        <div className="skeleton h-3 w-5/6"></div>
        <div className="skeleton h-3 w-4/6"></div>
      </div>
    </div>
  )
}

function EmptyPlanState({ muted = false }) {
  return (
    <div className={`card flex items-center justify-center text-center min-h-[420px] ${muted ? 'opacity-70' : ''}`}>
      <div className="max-w-sm">
        <div className="w-12 h-12 mx-auto rounded-full bg-accent-50 text-accent-700 flex items-center justify-center text-xl mb-3">📋</div>
        <h3 className="text-base font-semibold text-ink-800">Your experiment plan will appear here</h3>
        <p className="text-sm text-slate-500 mt-1.5 leading-relaxed">
          Enter a hypothesis on the left and run the literature check.
          You'll then be able to generate a full plan in seconds.
        </p>
      </div>
    </div>
  )
}

function ReadyPlanState({ onGenerate }) {
  return (
    <div className="card flex items-center justify-center text-center min-h-[420px]">
      <div className="max-w-sm">
        <div className="w-12 h-12 mx-auto rounded-full bg-success-50 text-success-700 flex items-center justify-center text-xl mb-3">✓</div>
        <h3 className="text-base font-semibold text-ink-800">Literature check complete</h3>
        <p className="text-sm text-slate-500 mt-1.5 leading-relaxed">
          Review the novelty signal and references on the left.
          Ready to generate the full operational plan?
        </p>
        <button onClick={onGenerate} className="btn-primary-lg mt-5">
          Generate experiment plan →
        </button>
      </div>
    </div>
  )
}

function PlanGeneratingState() {
  const steps = [
    'Designing protocol grounded in published methods…',
    'Sourcing reagents with real catalog numbers…',
    'Estimating budget line items and contingency…',
    'Building phased timeline with dependencies…',
    'Defining validation metrics and success thresholds…',
  ]
  return (
    <div className="card min-h-[420px] flex flex-col">
      <div className="flex items-center gap-2 mb-5">
        <span className="pill-dot bg-accent-500 animate-pulse-dot" />
        <span className="text-xs font-semibold uppercase tracking-wider text-accent-700">
          Generating plan
        </span>
      </div>
      <h3 className="text-lg font-semibold text-ink-800 mb-1">Designing your experiment</h3>
      <p className="text-sm text-slate-500 mb-6">This usually takes 8–15 seconds.</p>
      <ul className="space-y-3 text-sm">
        {steps.map((step, i) => (
          <li key={i} className="flex items-start gap-3 animate-fade-in" style={{ animationDelay: `${i * 60}ms` }}>
            <span className="mt-1.5 pill-dot bg-accent-400 animate-pulse-dot" />
            <span className="text-slate-600">{step}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white mt-16">
      <div className="max-w-6xl mx-auto px-4 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500">
        <p>
          Built by <span className="font-semibold text-ink-700">GIKI University</span> · MIT Global AI Hackathon 2026 · Challenge 04: The AI Scientist
        </p>
        <p>
          Powered by Groq · Tavily · OpenAlex · Semantic Scholar
        </p>
      </div>
    </footer>
  )
}
