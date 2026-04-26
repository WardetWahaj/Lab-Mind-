const PHASE_COLORS = {
  Setup:     '#1d4ed8',
  Execution: '#059669',
  Analysis:  '#7c3aed',
  Reporting: '#d97706',
}

function getPhaseColor(phase, week) {
  if (phase && PHASE_COLORS[phase]) return PHASE_COLORS[phase]
  if (week <= 2) return PHASE_COLORS.Setup
  if (week <= 5) return PHASE_COLORS.Execution
  if (week <= 8) return PHASE_COLORS.Analysis
  return PHASE_COLORS.Reporting
}

function normalizePhase(entry, index) {
  const safeEntry = entry && typeof entry === 'object' ? entry : {}
  const numericWeek = Number(safeEntry.week)
  const week = Number.isFinite(numericWeek) && numericWeek > 0 ? numericWeek : index + 1

  let tasks = []
  if (Array.isArray(safeEntry.tasks)) {
    tasks = safeEntry.tasks.filter((task) => typeof task === 'string' && task.trim())
  } else if (typeof safeEntry.description === 'string' && safeEntry.description.trim()) {
    tasks = [safeEntry.description.trim()]
  }

  const dependsOnRaw = safeEntry.depends_on
  const dependsOn = Array.isArray(dependsOnRaw)
    ? dependsOnRaw.filter((dep) => dep !== null && dep !== undefined).map(String)
    : (dependsOnRaw !== null && dependsOnRaw !== undefined && dependsOnRaw !== '')
      ? [String(dependsOnRaw)]
      : []

  return {
    week,
    phase: safeEntry.phase || 'Phase',
    tasks,
    milestone: safeEntry.milestone || '',
    dependsOn,
  }
}

export default function TimelineChart({ timeline }) {
  const data = timeline
  const tasks = data?.tasks ?? data?.phases ?? data?.weeks ?? data ?? []
  const safeTaskList = Array.isArray(tasks)
    ? tasks.map((entry, index) => normalizePhase(entry, index))
    : []

  if (!data || safeTaskList.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
        Timeline data unavailable for this plan.
      </div>
    )
  }

  const maxWeek = Math.max(1, ...safeTaskList.map((t) => Number(t.week) || 1))

  return (
    <div className="space-y-5">
      {/* Phase legend */}
      <div className="flex flex-wrap gap-2">
        {Object.entries(PHASE_COLORS).map(([phase, color]) => (
          <span key={phase} className="pill-neutral">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            {phase}
          </span>
        ))}
      </div>

      {/* Gantt-style rows */}
      <div className="space-y-3">
        {safeTaskList.map((phase, index) => {
          const color = getPhaseColor(phase.phase, phase.week)
          const widthPct = (phase.week / maxWeek) * 100
          return (
            <div key={index} className="rounded-xl2 border border-slate-100 bg-white p-3 sm:p-4">
              <div className="flex items-start gap-4">
                <div className="w-20 sm:w-24 flex-shrink-0">
                  <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Week</p>
                  <p className="text-2xl font-bold text-ink-900 leading-none mt-0.5">{phase.week}</p>
                  <span
                    className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold px-1.5 py-0.5 rounded"
                    style={{ color, backgroundColor: `${color}1A` }}
                  >
                    {phase.phase}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="relative h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${widthPct}%`, backgroundColor: color }}
                    />
                  </div>
                  {phase.tasks.length > 0 && (
                    <ul className="mt-3 space-y-1.5">
                      {phase.tasks.map((task, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-slate-700 leading-snug">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-slate-400 flex-shrink-0" />
                          <span>{task}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {phase.milestone && (
                    <p className="mt-3 text-xs font-semibold text-success-700 flex items-center gap-1.5">
                      <CheckIcon /> {phase.milestone}
                    </p>
                  )}
                  {phase.dependsOn.length > 0 && (
                    <p className="text-[11px] text-slate-500 mt-1.5">
                      Depends on: Week {phase.dependsOn.join(', Week ')}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12l4 4L19 6" />
    </svg>
  )
}
