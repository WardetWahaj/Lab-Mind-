import { useEffect, useState } from 'react'

const SAMPLE_HYPOTHESES = [
  {
    title: 'Diagnostics',
    icon: '🩸',
    accent: 'rose',
    text: 'A paper-based electrochemical biosensor functionalized with anti-CRP antibodies will detect C-reactive protein in whole blood at concentrations below 0.5 mg/L within 10 minutes, matching laboratory ELISA sensitivity without requiring sample preprocessing.',
  },
  {
    title: 'Gut Health',
    icon: '🧬',
    accent: 'emerald',
    text: 'Supplementing C57BL/6 mice with Lactobacillus rhamnosus GG for 4 weeks will reduce intestinal permeability by at least 30% compared to controls, measured by FITC-dextran assay, due to upregulation of tight junction proteins claudin-1 and occludin.',
  },
  {
    title: 'Cell Biology',
    icon: '🧫',
    accent: 'accent',
    text: "Replacing sucrose with trehalose as a cryoprotectant in the freezing medium will increase post-thaw viability of HeLa cells by at least 15 percentage points compared to the standard DMSO protocol, due to trehalose's superior membrane stabilization at low temperatures.",
  },
  {
    title: 'Climate',
    icon: '🌱',
    accent: 'success',
    text: 'Introducing Sporomusa ovata into a bioelectrochemical system at a cathode potential of -400mV vs SHE will fix CO2 into acetate at a rate of at least 150 mmol/L/day, outperforming current biocatalytic carbon capture benchmarks by at least 20%.',
  },
]

const ACCENT_CLASSES = {
  rose:    'bg-rose-50 text-rose-700 border-rose-100 hover:bg-rose-100 hover:border-rose-200',
  emerald: 'bg-emerald-50 text-emerald-700 border-emerald-100 hover:bg-emerald-100 hover:border-emerald-200',
  accent:  'bg-accent-50 text-accent-700 border-accent-100 hover:bg-accent-100 hover:border-accent-200',
  success: 'bg-success-50 text-success-700 border-success-100 hover:bg-success-100 hover:border-success-200',
}

export default function HypothesisInput({ onCheckLiterature, isLoading, value, disabled }) {
  const [text, setText] = useState(value || '')

  // Stay in sync if the parent resets the hypothesis (e.g. "Start over").
  useEffect(() => {
    setText(value || '')
  }, [value])

  const handleCheckClick = () => {
    if (text.trim().length >= 20 && !isLoading) {
      onCheckLiterature(text.trim())
    }
  }

  const handleSampleClick = (sample) => {
    if (disabled) return
    setText(sample.text)
  }

  const length = text.length
  const remaining = Math.max(0, 20 - length)
  const isReady = length >= 20

  return (
    <div className="card animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>Scientific hypothesis</h2>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-subtle)' }}>
            Name a specific intervention, a measurable outcome, and a mechanism.
          </p>
        </div>
        <span className="pill-neutral">Step 1</span>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        placeholder="e.g. Replacing sucrose with trehalose as a cryoprotectant will increase post-thaw viability of HeLa cells by ≥15 percentage points compared to the standard DMSO protocol."
        className="textarea h-36 disabled:opacity-50" style={{ color: 'var(--color-text)' }}
        aria-label="Scientific hypothesis"
      />

      <div className="mt-2 flex items-center justify-between text-xs">
        <span style={{ color: 'var(--color-text-subtle)' }}>
          {length} character{length === 1 ? '' : 's'}
        </span>
        {!isReady && (
          <span className="text-amber-700 font-medium">
            {remaining} more characters needed
          </span>
        )}
        {isReady && (
          <span className="text-success-700 font-medium">Ready to check ✓</span>
        )}
      </div>

      <button
        onClick={handleCheckClick}
        disabled={isLoading || !isReady || disabled}
        className="btn-primary-lg w-full mt-4"
      >
        {isLoading ? (
          <>
            <span className="pill-dot bg-white/80 animate-pulse-dot" />
            Checking literature…
          </>
        ) : (
          <>Run literature QC →</>
        )}
      </button>

      <div className="mt-5">
        <p className="label mb-2">Try a sample hypothesis</p>
        <div className="grid grid-cols-2 gap-2">
          {SAMPLE_HYPOTHESES.map((sample) => (
            <button
              key={sample.title}
              type="button"
              disabled={disabled}
              onClick={() => handleSampleClick(sample)}
              className={`text-left rounded-lg border px-3 py-2 transition-all duration-150 disabled:opacity-50 ${ACCENT_CLASSES[sample.accent]}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold">{sample.title}</span>
                <span aria-hidden="true">{sample.icon}</span>
              </div>
              <span className="block text-[11px] mt-1 text-current line-clamp-2">
                {sample.text.split('.')[0]}.
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
