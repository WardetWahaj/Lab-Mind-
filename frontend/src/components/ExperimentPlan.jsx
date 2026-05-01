import { useEffect, useMemo, useState } from 'react'
import ProtocolCard from './ProtocolCard'
import ReagentsTable from './ReagentsTable'
import BudgetChart from './BudgetChart'
import TimelineChart from './TimelineChart'
import ValidationCard from './ValidationCard'
import ScientistReview from './ScientistReview'

const TABS = [
  { id: 'protocol',   label: 'Protocol',   icon: ProtocolIcon,   description: 'Step-by-step methodology' },
  { id: 'reagents',   label: 'Reagents',   icon: ReagentsIcon,   description: 'Materials & catalog numbers' },
  { id: 'budget',     label: 'Budget',     icon: BudgetIcon,     description: 'Line-item costs' },
  { id: 'timeline',   label: 'Timeline',   icon: TimelineIcon,   description: 'Phased delivery plan' },
  { id: 'validation', label: 'Validation', icon: ValidationIcon, description: 'Success metrics' },
]

function toNumber(value) {
  if (value === null || value === undefined) return 0
  if (typeof value === 'number' && !Number.isNaN(value)) return value
  if (typeof value === 'string') {
    const cleaned = value.replace(/[^\d.\-]/g, '')
    const parsed = parseFloat(cleaned)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

function formatUSD(value) {
  return `$${toNumber(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatUSDCompact(value) {
  const num = toNumber(value)
  if (num >= 10_000) {
    return `$${(num / 1000).toFixed(num >= 100_000 ? 0 : 1)}k`
  }
  return `$${num.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function ExperimentPlan({ data, hypothesis, lastFeedbackApplied, onFeedbackSaved }) {
  const [activeTab, setActiveTab] = useState('protocol')
  const [showReview, setShowReview] = useState(false)
  const [feedbackToast, setFeedbackToast] = useState(null)

  // Surface a toast when the parent reports that feedback was saved.
  useEffect(() => {
    if (!lastFeedbackApplied) return
    setFeedbackToast(lastFeedbackApplied)
    const t = setTimeout(() => setFeedbackToast(null), 5000)
    return () => clearTimeout(t)
  }, [lastFeedbackApplied])

  const summary = useMemo(() => {
    const stepCount = (data?.protocol || []).length
    const reagentCount = (data?.reagents || []).length
    const totalBudget = toNumber(data?.budget?.total_usd)
      || (data?.reagents || []).reduce((s, r) => s + toNumber(r.total_cost_usd), 0)
    const weeks = (data?.timeline || []).reduce((max, t) => {
      const w = toNumber(t.week)
      return w > max ? w : max
    }, (data?.timeline || []).length)
    return { stepCount, reagentCount, totalBudget, weeks }
  }, [data])

  const handlePrint = () => {
    // Reveal all panels at print time (CSS handles the rest).
    document.body.setAttribute('data-print-all', 'true')
    setTimeout(() => {
      window.print()
      setTimeout(() => document.body.removeAttribute('data-print-all'), 500)
    }, 50)
  }

  const isDemoPlan = (data?.budget?.currency_note || '').toUpperCase().startsWith('DEMO MODE')

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Feedback toast */}
      {feedbackToast && (
        <div className="rounded-lg bg-success-50 border border-success-100 px-3 py-2 flex items-start gap-2 text-success-800 text-sm animate-fade-in">
          <span className="mt-0.5">✓</span>
          <span className="leading-snug">{feedbackToast}</span>
        </div>
      )}

      {/* Demo-mode warning */}
      {isDemoPlan && (
        <div className="rounded-lg bg-warn-50 border border-warn-200 px-4 py-3 flex items-start gap-3 animate-fade-in">
          <div className="w-7 h-7 rounded-full bg-warn-100 text-warn-700 flex items-center justify-center text-sm font-bold flex-shrink-0">!</div>
          <div className="flex-1">
            <p className="text-sm font-semibold" style={{ color: 'var(--color-warning)' }}>Showing a cached demo plan</p>
            <p className="text-xs text-warn-700 mt-1 leading-relaxed">
              Live plan generation hit a provider limit (likely Groq daily quota).
              We picked the most topically relevant cached example instead. Click <span className="font-semibold">Start over</span> in a few minutes to retry a fresh generation.
            </p>
          </div>
        </div>
      )}

      {/* Plan summary header */}
      <div className="surface p-5">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <span className="pill-success mb-2">
              <span className="pill-dot bg-success-500" />
              Plan ready
            </span>
            <h2 className="text-lg font-semibold leading-tight" style={{ color: 'var(--color-text)' }}>Experiment plan</h2>
            <p className="text-xs mt-1 max-w-xl line-clamp-2" style={{ color: 'var(--color-text-subtle)' }}>{hypothesis}</p>
          </div>
          <div className="flex items-center gap-2 no-print">
            <button onClick={handlePrint} className="btn-secondary">
              <span aria-hidden="true">⤓</span> Export PDF
            </button>
            <button
              onClick={() => setShowReview(true)}
              className="btn-primary"
            >
              <span aria-hidden="true">★</span> Expert review
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
          <KpiCard label="Total budget" value={formatUSDCompact(summary.totalBudget)} sub="line items below" />
          <KpiCard label="Timeline"     value={`${summary.weeks || '—'} ${summary.weeks === 1 ? 'week' : 'weeks'}`} sub={`${summary.stepCount} protocol steps`} />
          <KpiCard label="Materials"    value={`${summary.reagentCount}`}            sub="reagents & lines" />
          <KpiCard label="Protocol"     value={`${summary.stepCount}`}               sub="published-method steps" />
        </div>
      </div>

      {/* Tab navigation + content */}
      <div className="surface overflow-hidden">
        <div className="flex border-b border-slate-200 overflow-x-auto thin-scroll" role="tablist">
          {TABS.map((tab) => {
            const Icon = tab.icon
            const selected = activeTab === tab.id
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={selected}
                onClick={() => setActiveTab(tab.id)}
                className="tab flex-shrink-0 flex items-center gap-2"
              >
                <Icon active={selected} />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>

        <div className="p-5 sm:p-6">
          {/* In screen mode only the active tab is rendered, but for print we
              expand all panels via CSS (data-print-all on body). */}
          <div data-tab-panel data-tab-id="protocol"   className={activeTab === 'protocol'   ? '' : 'hidden'}>
            <TabHeader title="Protocol"   description="Step-by-step methodology grounded in published protocols." />
            <ProtocolCard protocol={data.protocol} />
          </div>
          <div data-tab-panel data-tab-id="reagents"   className={activeTab === 'reagents'   ? '' : 'hidden'}>
            <TabHeader title="Reagents & materials" description="Specific reagents, suppliers, and catalog numbers." />
            <ReagentsTable reagents={data.reagents} />
          </div>
          <div data-tab-panel data-tab-id="budget"     className={activeTab === 'budget'     ? '' : 'hidden'}>
            <TabHeader title="Budget" description="Realistic estimate with line items and contingency." />
            <BudgetChart budget={data.budget} />
          </div>
          <div data-tab-panel data-tab-id="timeline"   className={activeTab === 'timeline'   ? '' : 'hidden'}>
            <TabHeader title="Timeline" description="Phased breakdown with milestones and dependencies." />
            <TimelineChart timeline={data.timeline} />
          </div>
          <div data-tab-panel data-tab-id="validation" className={activeTab === 'validation' ? '' : 'hidden'}>
            <TabHeader title="Validation" description="How success or failure will be measured." />
            <ValidationCard validation={data.validation} />
          </div>
        </div>
      </div>

      {/* Expert review slide-over */}
      {showReview && (
        <ReviewSlideOver onClose={() => setShowReview(false)}>
          <ScientistReview
            hypothesis={hypothesis}
            onFeedbackSaved={(experimentType, corrections) => {
              if (onFeedbackSaved) onFeedbackSaved(experimentType, corrections)
            }}
            onClose={() => setShowReview(false)}
          />
        </ReviewSlideOver>
      )}
    </div>
  )
}

// ----------------------------------------------------------------------------
// Sub-components
// ----------------------------------------------------------------------------

function KpiCard({ label, value, sub }) {
  return (
    <div className="rounded-lg border px-3 py-2.5" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-bg-elevated)' }}>
      <p className="label">{label}</p>
      <p className="text-lg font-semibold mt-0.5" style={{ color: 'var(--color-text)' }}>{value}</p>
      <p className="text-[11px]" style={{ color: 'var(--color-text-subtle)' }}>{sub}</p>
    </div>
  )
}

function TabHeader({ title, description }) {
  return (
    <div className="mb-5">
      <h3 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>{title}</h3>
      <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-subtle)' }}>{description}</p>
    </div>
  )
}

function ReviewSlideOver({ children, onClose }) {
  return (
    <div className="fixed inset-0 z-40 no-print" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-ink-900/40 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
      />
      <div className="absolute right-0 top-0 bottom-0 w-full max-w-xl bg-paper shadow-lift overflow-y-auto thin-scroll animate-fade-in">
        <div className="sticky top-0 bg-paper/95 backdrop-blur border-b border-slate-200 px-5 py-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>Expert review</h3>
          <button
            onClick={onClose}
            className="px-2 py-1 rounded-md transition-colors" style={{ color: 'var(--color-text-muted)', backgroundColor: 'var(--color-bg-subtle)' }}
            aria-label="Close review"
          >
            ✕
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------------------
// Inline icons (small, consistent stroke)
// ----------------------------------------------------------------------------

function iconStroke(active) {
  return active ? 'currentColor' : 'currentColor'
}

function ProtocolIcon({ active }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={iconStroke(active)} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 7h8M8 11h8M8 15h5" />
    </svg>
  )
}
function ReagentsIcon({ active }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={iconStroke(active)} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 3h6M10 3v6L5 19a2 2 0 0 0 1.7 3h10.6A2 2 0 0 0 19 19l-5-10V3" />
      <path d="M7.5 14h9" />
    </svg>
  )
}
function BudgetIcon({ active }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={iconStroke(active)} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v10M9 9.5h4.5a2 2 0 1 1 0 4H10.5a2 2 0 1 0 0 4H15" />
    </svg>
  )
}
function TimelineIcon({ active }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={iconStroke(active)} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 9h18M8 3v4M16 3v4" />
    </svg>
  )
}
function ValidationIcon({ active }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={iconStroke(active)} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12l4 4L19 6" />
    </svg>
  )
}
