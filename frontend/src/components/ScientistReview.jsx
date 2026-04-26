import { useState } from 'react'

const SECTIONS = [
  { key: 'protocol',   label: 'Protocol steps',          placeholder: 'e.g. Step 3 incubation should be 37 °C, not 25 °C.' },
  { key: 'reagents',   label: 'Reagents & materials',    placeholder: 'e.g. Use catalog #L6416 instead of L2020 for this application.' },
  { key: 'budget',     label: 'Budget estimates',        placeholder: 'e.g. Flow cytometer rental is typically $200/hr, not $80/hr.' },
  { key: 'timeline',   label: 'Timeline & dependencies', placeholder: 'e.g. Cell passaging takes 3 weeks minimum, not 1 week.' },
  { key: 'validation', label: 'Validation criteria',     placeholder: 'e.g. Need n=12 minimum for 80% statistical power.' },
]

export default function ScientistReview({ hypothesis, onFeedbackSaved, onClose }) {
  const [experimentType, setExperimentType] = useState('')
  const [ratings, setRatings] = useState({
    protocol: 3, reagents: 3, budget: 3, timeline: 3, validation: 3,
  })
  const [corrections, setCorrections] = useState({
    protocol: '', reagents: '', budget: '', timeline: '', validation: '',
  })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  const handleRating = (section, value) =>
    setRatings((prev) => ({ ...prev, [section]: value }))

  const handleCorrection = (section, value) =>
    setCorrections((prev) => ({ ...prev, [section]: value }))

  const isValid = experimentType.trim().length > 0

  const handleSubmit = async () => {
    if (!isValid) {
      setSubmitError('Please specify the experiment type so feedback applies to similar plans.')
      return
    }
    setSubmitError(null)
    setIsSubmitting(true)

    try {
      const response = await fetch(`${API_BASE}/api/save-feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hypothesis,
          experiment_type: experimentType.trim(),
          corrections: {
            protocol:   { rating: ratings.protocol,   correction: corrections.protocol },
            reagents:   { rating: ratings.reagents,   correction: corrections.reagents },
            budget:     { rating: ratings.budget,     correction: corrections.budget },
            timeline:   { rating: ratings.timeline,   correction: corrections.timeline },
            validation: { rating: ratings.validation, correction: corrections.validation },
          },
        }),
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail.detail || `Save failed (${response.status})`)
      }

      if (onFeedbackSaved) {
        onFeedbackSaved(experimentType.trim(), corrections)
      }
      setSubmitted(true)
      // Briefly show success, then close the panel.
      setTimeout(() => {
        if (onClose) onClose()
      }, 1500)
    } catch (err) {
      setSubmitError(err.message || 'Could not save feedback.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-lg font-semibold text-ink-900">Scientist review</h2>
        <p className="text-sm text-slate-600 mt-1 leading-relaxed">
          Rate each section and leave concrete corrections. Future plans of the
          same experiment type will reflect your corrections automatically.
        </p>
      </header>

      <div>
        <label htmlFor="experiment-type" className="label">Experiment type</label>
        <input
          id="experiment-type"
          type="text"
          value={experimentType}
          onChange={(e) => setExperimentType(e.target.value)}
          placeholder="e.g. mouse gut microbiome, cell cryopreservation, paper biosensor…"
          className="input mt-1.5"
        />
        <p className="text-[11px] text-slate-500 mt-1">
          Used to retrieve this feedback the next time a similar hypothesis is submitted.
        </p>
      </div>

      <div className="space-y-3">
        {SECTIONS.map((section) => (
          <div key={section.key} className="rounded-xl2 border border-slate-200 bg-white p-3.5">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-semibold text-ink-800">{section.label}</label>
              <StarRating
                value={ratings[section.key]}
                onChange={(v) => handleRating(section.key, v)}
              />
            </div>
            <textarea
              value={corrections[section.key]}
              onChange={(e) => handleCorrection(section.key, e.target.value)}
              placeholder={section.placeholder}
              className="textarea h-20 text-sm"
            />
          </div>
        ))}
      </div>

      {submitError && (
        <div className="rounded-lg bg-danger-50 border border-danger-100 px-3 py-2 text-sm text-danger-800">
          {submitError}
        </div>
      )}

      {submitted ? (
        <div className="rounded-lg bg-success-50 border border-success-100 px-3 py-3 text-sm text-success-800 flex items-start gap-2 animate-fade-in">
          <span className="mt-0.5">✓</span>
          <span>
            Feedback saved. Future plans tagged <span className="font-semibold">"{experimentType.trim()}"</span> will reuse your corrections.
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button onClick={handleSubmit} disabled={isSubmitting || !isValid} className="btn-primary-lg flex-1">
            {isSubmitting ? (
              <>
                <span className="pill-dot bg-white/80 animate-pulse-dot" /> Saving…
              </>
            ) : (
              <>Save expert feedback</>
            )}
          </button>
          {onClose && (
            <button onClick={onClose} className="btn-secondary">Cancel</button>
          )}
        </div>
      )}
    </div>
  )
}

function StarRating({ value, onChange }) {
  return (
    <div className="flex items-center gap-0.5" role="radiogroup">
      {[1, 2, 3, 4, 5].map((star) => {
        const filled = star <= value
        return (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={filled}
            aria-label={`Rate ${star} out of 5`}
            onClick={() => onChange(star)}
            className={`p-1 rounded transition-transform hover:scale-110 focus-ring ${filled ? 'text-amber-500' : 'text-slate-300 hover:text-amber-400'}`}
          >
            <Star filled={filled} />
          </button>
        )
      })}
    </div>
  )
}

function Star({ filled }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
    </svg>
  )
}
