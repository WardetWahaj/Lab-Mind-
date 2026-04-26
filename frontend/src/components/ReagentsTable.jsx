import { useState } from 'react'

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
  return `$${toNumber(value).toFixed(2)}`
}

const SUPPLIER_TONES = {
  'sigma-aldrich': 'bg-amber-50 text-amber-800 border-amber-100',
  'sigma':         'bg-amber-50 text-amber-800 border-amber-100',
  'merck':         'bg-amber-50 text-amber-800 border-amber-100',
  'thermo fisher': 'bg-rose-50 text-rose-800 border-rose-100',
  'thermofisher':  'bg-rose-50 text-rose-800 border-rose-100',
  'gibco':         'bg-rose-50 text-rose-800 border-rose-100',
  'invitrogen':    'bg-rose-50 text-rose-800 border-rose-100',
  'atcc':          'bg-emerald-50 text-emerald-800 border-emerald-100',
  'addgene':       'bg-accent-50 text-accent-800 border-accent-100',
  'promega':       'bg-blue-50 text-blue-800 border-blue-100',
  'qiagen':        'bg-success-50 text-success-800 border-success-100',
  'idt':           'bg-slate-50 text-slate-800 border-slate-200',
  'idt dna':       'bg-slate-50 text-slate-800 border-slate-200',
}

function supplierPillClass(supplier) {
  const key = (supplier || '').toLowerCase()
  return SUPPLIER_TONES[key] || 'bg-slate-50 text-slate-700 border-slate-200'
}

export default function ReagentsTable({ reagents }) {
  const [sortBy, setSortBy] = useState(null)
  const [sortAsc, setSortAsc] = useState(true)

  if (!reagents || reagents.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
        No reagents specified.
      </div>
    )
  }

  const sortedReagents = [...reagents].sort((a, b) => {
    if (!sortBy) return 0
    let aVal = a[sortBy]
    let bVal = b[sortBy]
    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase()
      bVal = (bVal || '').toString().toLowerCase()
    }
    if (aVal < bVal) return sortAsc ? -1 : 1
    if (aVal > bVal) return sortAsc ? 1 : -1
    return 0
  })

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortAsc(!sortAsc)
    } else {
      setSortBy(column)
      setSortAsc(true)
    }
  }

  const total = reagents.reduce((sum, r) => sum + toNumber(r.total_cost_usd), 0)

  const downloadCSV = () => {
    const headers = ['Reagent', 'Qty', 'Unit', 'Concentration', 'Supplier', 'Catalog #', 'Unit Price (USD)', 'Total (USD)', 'Notes']
    const rows = reagents.map((r) => [
      r.name || '',
      toNumber(r.quantity),
      r.unit || '',
      r.concentration || '',
      r.supplier || '',
      r.catalog_number || '',
      toNumber(r.unit_price_usd).toFixed(2),
      toNumber(r.total_cost_usd).toFixed(2),
      (r.notes || '').replace(/"/g, '""'),
    ])
    const csv = [headers, ...rows]
      .map((row) => row.map((cell) => `"${cell}"`).join(','))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'reagents.csv'
    a.click()
    window.URL.revokeObjectURL(url)
  }

  const sortIndicator = (col) => sortBy === col ? (sortAsc ? '↑' : '↓') : ''

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs text-slate-500">
          {reagents.length} reagent{reagents.length === 1 ? '' : 's'} · click column headers to sort
        </div>
        <button onClick={downloadCSV} className="btn-secondary btn-sm">
          <DownloadIcon /> Download CSV
        </button>
      </div>

      <div className="rounded-xl2 border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto thin-scroll">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
                <Th onClick={() => handleSort('name')}            label={`Reagent ${sortIndicator('name')}`} />
                <Th onClick={() => handleSort('quantity')}        label={`Qty ${sortIndicator('quantity')}`} />
                <Th label="Unit" />
                <Th label="Conc." />
                <Th label="Supplier" />
                <Th onClick={() => handleSort('catalog_number')}  label={`Catalog # ${sortIndicator('catalog_number')}`} />
                <Th onClick={() => handleSort('unit_price_usd')}  label={`Unit price ${sortIndicator('unit_price_usd')}`} align="right" />
                <Th onClick={() => handleSort('total_cost_usd')}  label={`Total ${sortIndicator('total_cost_usd')}`}      align="right" />
                <Th label="Notes" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sortedReagents.map((reagent, index) => (
                <tr key={index} className="hover:bg-slate-50/60 transition-colors">
                  <td className="px-3 py-3 align-top">
                    <p className="text-ink-900 font-medium leading-snug">{reagent.name}</p>
                  </td>
                  <td className="px-3 py-3 align-top text-slate-700">{toNumber(reagent.quantity)}</td>
                  <td className="px-3 py-3 align-top text-slate-700">{reagent.unit}</td>
                  <td className="px-3 py-3 align-top text-slate-700">{reagent.concentration || 'N/A'}</td>
                  <td className="px-3 py-3 align-top">
                    {reagent.supplier ? (
                      <span className={`pill ${supplierPillClass(reagent.supplier)}`}>
                        {reagent.supplier}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3 align-top">
                    {reagent.catalog_number ? (
                      <a
                        href={getCatalogLink(reagent.supplier, reagent.catalog_number)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mono hover:bg-slate-200"
                      >
                        {reagent.catalog_number}
                      </a>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3 align-top text-right text-slate-800 font-medium">
                    {formatUSD(reagent.unit_price_usd)}
                  </td>
                  <td className="px-3 py-3 align-top text-right text-ink-900 font-semibold">
                    {formatUSD(reagent.total_cost_usd)}
                  </td>
                  <td className="px-3 py-3 align-top text-xs text-slate-500 max-w-[14rem]">
                    {reagent.notes}
                  </td>
                </tr>
              ))}
              <tr className="bg-accent-50/70 border-t-2 border-accent-200">
                <td colSpan="7" className="px-3 py-3 text-right text-xs uppercase tracking-wider font-semibold text-accent-800">
                  Total reagents
                </td>
                <td className="px-3 py-3 text-right text-accent-900 font-bold text-base">
                  {`$${total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                </td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function Th({ label, onClick, align = 'left' }) {
  return (
    <th
      onClick={onClick}
      className={`px-3 py-2.5 font-semibold ${align === 'right' ? 'text-right' : 'text-left'} ${onClick ? 'cursor-pointer hover:text-ink-700' : ''}`}
    >
      {label}
    </th>
  )
}

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 4v12M6 11l6 6 6-6M5 20h14" />
    </svg>
  )
}

function getCatalogLink(supplier, catalogNumber) {
  if (!catalogNumber) return '#'
  const encoded = encodeURIComponent(catalogNumber)
  switch ((supplier || '').toLowerCase()) {
    case 'sigma-aldrich':
    case 'sigma':
    case 'merck':
      return `https://www.sigmaaldrich.com/US/en/search/${encoded}`
    case 'thermo fisher':
    case 'thermofisher':
    case 'gibco':
    case 'invitrogen':
      return `https://www.thermofisher.com/search/results?query=${encoded}`
    case 'atcc':
      return `https://www.atcc.org/search#q=${encoded}`
    case 'addgene':
      return `https://www.addgene.org/search/catalog/plasmids/?q=${encoded}`
    case 'promega':
      return `https://www.promega.com/search-results?searchterm=${encoded}`
    case 'qiagen':
      return `https://www.qiagen.com/us/search/?q=${encoded}`
    case 'idt':
    case 'idt dna':
      return `https://www.idtdna.com/site/search?q=${encoded}`
    default:
      return `https://www.google.com/search?q=${encoded}+${encodeURIComponent(supplier || '')}`
  }
}
