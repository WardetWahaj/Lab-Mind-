import { useEffect, useRef, useState } from 'react'

const COLORS = {
  'Reagents & Consumables':            '#1d4ed8',
  'Equipment & Rental':                '#0891b2',
  'Cell Lines / Biological Materials': '#059669',
  'Labour (estimated)':                '#d97706',
  'Contingency (10%)':                 '#dc2626',
}

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
  return toNumber(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function colorFor(label, fallbackIdx = 0) {
  if (COLORS[label]) return COLORS[label]
  const palette = ['#1d4ed8', '#0891b2', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0ea5e9', '#16a34a']
  return palette[fallbackIdx % palette.length]
}

export default function BudgetChart({ budget }) {
  const canvasRef = useRef(null)
  const chartRef = useRef(null)
  const retryTimerRef = useRef(null)
  const [chartUnavailable, setChartUnavailable] = useState(false)

  useEffect(() => {
    if (!canvasRef.current || !budget || !Array.isArray(budget.breakdown)) return

    let retries = 0
    const maxRetries = 8
    setChartUnavailable(false)

    const initChart = () => {
      const hasChart = typeof window !== 'undefined' && !!window.Chart
      if (!hasChart) {
        retries += 1
        if (retries >= maxRetries) {
          setChartUnavailable(true)
          return
        }
        retryTimerRef.current = setTimeout(initChart, 400)
        return
      }

      if (chartRef.current) {
        chartRef.current.destroy()
        chartRef.current = null
      }

      const ctx = canvasRef.current.getContext('2d')
      const labels = budget.breakdown.map((b) => b.category)
      const data = budget.breakdown.map((b) => toNumber(b.amount_usd))
      const backgroundColors = labels.map((label, i) => colorFor(label, i))

      chartRef.current = new window.Chart(ctx, {
        type: 'doughnut',
        data: {
          labels,
          datasets: [
            {
              data,
              backgroundColor: backgroundColors,
              borderColor: '#ffffff',
              borderWidth: 3,
              hoverBorderColor: '#ffffff',
              hoverBorderWidth: 3,
              hoverOffset: 6,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          cutout: '70%',
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.label}: $${formatUSD(ctx.parsed)}`,
              },
              backgroundColor: '#0f172a',
              borderColor: '#1e293b',
              borderWidth: 1,
              padding: 10,
              cornerRadius: 8,
              titleFont: { weight: '600' },
              bodyFont: { weight: '500' },
            },
          },
        },
      })
    }

    initChart()

    return () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
      }
      if (chartRef.current) {
        chartRef.current.destroy()
        chartRef.current = null
      }
    }
  }, [budget])

  if (!budget) {
    return <div className="text-slate-500 text-sm">No budget data available.</div>
  }

  const hasChartJs = typeof window !== 'undefined' && !!window.Chart
  const total = toNumber(budget.total_usd)
    || (budget.breakdown || []).reduce((s, b) => s + toNumber(b.amount_usd), 0)
  const breakdownTotal = (budget.breakdown || []).reduce((s, b) => s + toNumber(b.amount_usd), 0) || 1

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-center">
        {/* Doughnut */}
        <div className="lg:col-span-2 flex items-center justify-center">
          <div className="relative w-56 h-56 sm:w-64 sm:h-64">
            <canvas ref={canvasRef}></canvas>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">Total budget</p>
                <p className="text-2xl sm:text-3xl font-bold text-ink-900 mt-0.5">
                  ${formatUSD(total)}
                </p>
                {budget.currency_note && (
                  <p className="text-[10px] text-slate-400 mt-1 max-w-[10rem] mx-auto">{budget.currency_note}</p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Breakdown list w/ progress bars */}
        <div className="lg:col-span-3 space-y-2.5">
          {(budget.breakdown || []).map((item, index) => {
            const amount = toNumber(item.amount_usd)
            const pct = breakdownTotal > 0 ? Math.round((amount / breakdownTotal) * 100) : 0
            const color = colorFor(item.category, index)
            return (
              <div key={index} className="rounded-lg border border-slate-100 bg-white px-3 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-sm font-medium text-ink-800 truncate">{item.category}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-slate-500 tabular-nums">{pct}%</span>
                    <span className="text-sm font-semibold text-ink-900 tabular-nums">${formatUSD(item.amount_usd)}</span>
                  </div>
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {(chartUnavailable || !hasChartJs) && (
        <p className="text-xs text-slate-500 italic">
          Chart visualization unavailable; the breakdown above is fully accessible without it.
        </p>
      )}
    </div>
  )
}
