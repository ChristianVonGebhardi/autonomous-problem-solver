import { FileCode, Hash, ChevronRight } from 'lucide-react'
import { clsx } from 'clsx'
import type { QuerySource } from '@/lib/api'

interface SourceCardProps {
  source: QuerySource
  index: number
}

const chunkTypeColors: Record<string, string> = {
  function: 'bg-violet-100 text-violet-700',
  class: 'bg-blue-100 text-blue-700',
  documentation: 'bg-emerald-100 text-emerald-700',
  pull_request: 'bg-orange-100 text-orange-700',
  code: 'bg-slate-100 text-slate-600',
}

export function SourceCard({ source, index }: SourceCardProps) {
  const colorClass = chunkTypeColors[source.chunk_type] ?? chunkTypeColors.code
  const fileName = source.file_path.split('/').pop() ?? source.file_path
  const dirPath =
    source.file_path.includes('/') ? source.file_path.split('/').slice(0, -1).join('/') : ''

  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-300 transition-colors">
      <div className="flex-shrink-0 w-6 h-6 rounded-full bg-brand-100 text-brand-700 text-xs font-bold flex items-center justify-center">
        {index}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <FileCode size={13} className="text-slate-400 shrink-0" />
          {dirPath && (
            <span className="text-xs text-slate-400 truncate max-w-[120px]">{dirPath}/</span>
          )}
          <span className="text-xs font-semibold text-slate-700">{fileName}</span>
          <span
            className={clsx('px-1.5 py-0.5 rounded text-[10px] font-medium', colorClass)}
          >
            {source.chunk_type}
          </span>
          {source.name && (
            <span className="text-xs text-slate-500 truncate max-w-[100px]">{source.name}</span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1">
          {source.start_line > 0 && (
            <span className="text-[10px] text-slate-400">
              Lines {source.start_line}–{source.end_line}
            </span>
          )}
          <span className="text-[10px] text-slate-400">
            Relevance: {(source.score * 100).toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  )
}