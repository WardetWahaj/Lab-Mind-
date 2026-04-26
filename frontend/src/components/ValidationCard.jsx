export default function ValidationCard({ validation }) {
  if (!validation) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
        No validation data available.
      </div>
    )
  }

  const fields = [
    { title: 'Primary metric',     key: 'primary_metric',     value: validation.primary_metric,     icon: MetricIcon,  tone: 'accent'  },
    { title: 'Success threshold',  key: 'success_threshold',  value: validation.success_threshold,  icon: TargetIcon,  tone: 'success' },
    { title: 'Control condition',  key: 'control_condition',  value: validation.control_condition,  icon: ScienceIcon, tone: 'neutral' },
    { title: 'Statistical test',   key: 'statistical_test',   value: validation.statistical_test,   icon: ChartIcon,   tone: 'accent'  },
    { title: 'Sample size',        key: 'sample_size',        value: validation.sample_size,        icon: PeopleIcon,  tone: 'neutral' },
    { title: 'Failure criteria',   key: 'failure_criteria',   value: validation.failure_criteria,   icon: WarnIcon,    tone: 'danger'  },
  ]

  const visibleFields = fields.filter((f) => (f.value || '').toString().trim().length > 0)

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {visibleFields.map((field) => (
          <ValidationField key={field.key} {...field} />
        ))}
      </div>

      {validation.reporting_standard && (
        <div className="rounded-xl2 border border-accent-100 bg-accent-50 px-4 py-3">
          <p className="label text-accent-800">Reporting standard</p>
          <a
            href={getReportingStandardLink(validation.reporting_standard)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold text-accent-800 hover:text-accent-900 mt-0.5 inline-flex items-center gap-1.5"
          >
            {validation.reporting_standard}
            <ExternalIcon />
          </a>
        </div>
      )}
    </div>
  )
}

function ValidationField({ title, value, icon: Icon, tone }) {
  const toneClasses = {
    accent:  'bg-accent-50 text-accent-700',
    success: 'bg-success-50 text-success-700',
    danger:  'bg-danger-50 text-danger-700',
    neutral: 'bg-slate-50 text-slate-600',
  }
  return (
    <div className="rounded-xl2 border border-slate-100 bg-white p-3.5">
      <div className="flex items-start gap-3">
        <span className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${toneClasses[tone] || toneClasses.neutral}`}>
          <Icon />
        </span>
        <div className="flex-1 min-w-0">
          <p className="label">{title}</p>
          <p className="text-sm text-ink-800 leading-snug mt-1">{value}</p>
        </div>
      </div>
    </div>
  )
}

function getReportingStandardLink(standard) {
  const s = (standard || '').toUpperCase()
  if (s.includes('MIQE'))      return 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2737408/'
  if (s.includes('ARRIVE'))    return 'https://arriveguidelines.org/'
  if (s.includes('CONSORT'))   return 'https://www.equator-network.org/reporting-guidelines/consort/'
  if (s.includes('STARD'))     return 'https://www.equator-network.org/reporting-guidelines/stard/'
  if (s.includes('ISO 20391')) return 'https://www.iso.org/standard/68009.html'
  if (s.includes('GLP'))       return 'https://www.oecd.org/chemicalsafety/testing/good-laboratory-practiceglp.htm'
  return 'https://www.equator-network.org/'
}

// ----------------------------------------------------------------------------
// Inline icons
// ----------------------------------------------------------------------------

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }
function MetricIcon() {
  return (<svg width="18" height="18" viewBox="0 0 24 24" {...stroke} aria-hidden="true"><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/></svg>)
}
function TargetIcon() {
  return (<svg width="18" height="18" viewBox="0 0 24 24" {...stroke} aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/></svg>)
}
function ScienceIcon() {
  return (<svg width="18" height="18" viewBox="0 0 24 24" {...stroke} aria-hidden="true"><path d="M9 3h6M10 3v6L5 19a2 2 0 0 0 1.7 3h10.6A2 2 0 0 0 19 19l-5-10V3"/></svg>)
}
function ChartIcon() {
  return (<svg width="18" height="18" viewBox="0 0 24 24" {...stroke} aria-hidden="true"><path d="M3 3v18h18"/><path d="M7 15l4-4 4 4 5-7"/></svg>)
}
function PeopleIcon() {
  return (<svg width="18" height="18" viewBox="0 0 24 24" {...stroke} aria-hidden="true"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="3"/><path d="M22 19a5 5 0 0 0-7-4.6"/></svg>)
}
function WarnIcon() {
  return (<svg width="18" height="18" viewBox="0 0 24 24" {...stroke} aria-hidden="true"><path d="M12 3l10 18H2L12 3z"/><path d="M12 10v5M12 18v.01"/></svg>)
}
function ExternalIcon() {
  return (<svg width="12" height="12" viewBox="0 0 24 24" {...stroke} aria-hidden="true"><path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M20 14v6H4V4h6"/></svg>)
}
