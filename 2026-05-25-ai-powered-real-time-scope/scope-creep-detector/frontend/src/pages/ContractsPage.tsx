import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, Trash2, CheckCircle, Clock, AlertCircle, Plus, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'
import api from '../api'
import type { Contract } from '../types'

function StatusBadge({ status }: { status: string }) {
  const config = {
    active: { label: 'Active', cls: 'bg-green-900/40 text-green-400 border-green-800', icon: CheckCircle },
    processing: { label: 'Processing', cls: 'bg-yellow-900/40 text-yellow-400 border-yellow-800', icon: Clock },
    error: { label: 'Error', cls: 'bg-red-900/40 text-red-400 border-red-800', icon: AlertCircle },
    archived: { label: 'Archived', cls: 'bg-slate-800 text-slate-400 border-slate-700', icon: FileText },
  }[status] ?? { label: status, cls: 'bg-slate-800 text-slate-400 border-slate-700', icon: FileText }

  const Icon = config.icon
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border', config.cls)}>
      <Icon className="w-3 h-3" />
      {config.label}
    </span>
  )
}

function UploadModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [form, setForm] = useState({ title: '', client_name: '', project_value: '' })
  const [dragging, setDragging] = useState(false)

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('No file selected')
      const fd = new FormData()
      fd.append('file', file)
      fd.append('title', form.title)
      fd.append('client_name', form.client_name)
      if (form.project_value) fd.append('project_value', form.project_value)
      return (await api.post('/contracts/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contracts'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      toast.success('Contract uploaded and indexed successfully!')
      onClose()
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail ?? 'Upload failed')
    },
  })

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  const canSubmit = file && form.title.trim() && form.client_name.trim()

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-white">Upload Contract</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Drop zone */}
          <div
            className={clsx(
              'border-2 border-dashed rounded-xl p-6 text-center transition-colors cursor-pointer',
              dragging ? 'border-primary-500 bg-primary-950/30' : 'border-slate-600 hover:border-slate-500'
            )}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Upload className="w-8 h-8 mx-auto text-slate-500 mb-2" />
            {file ? (
              <div>
                <p className="text-white font-medium">{file.name}</p>
                <p className="text-slate-400 text-sm">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
            ) : (
              <div>
                <p className="text-slate-300">Drop your contract here</p>
                <p className="text-slate-500 text-sm">PDF, DOCX, DOC, or TXT</p>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Project Title *</label>
            <input
              type="text"
              placeholder="e.g. E-commerce Website Redesign"
              className="input-field"
              value={form.title}
              onChange={(e) => setForm(f => ({ ...f, title: e.target.value }))}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Client Name *</label>
            <input
              type="text"
              placeholder="e.g. Acme Corp"
              className="input-field"
              value={form.client_name}
              onChange={(e) => setForm(f => ({ ...f, client_name: e.target.value }))}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Project Value (USD) <span className="text-slate-500">optional</span>
            </label>
            <input
              type="number"
              placeholder="5000"
              className="input-field"
              value={form.project_value}
              onChange={(e) => setForm(f => ({ ...f, project_value: e.target.value }))}
            />
          </div>

          <button
            onClick={() => uploadMutation.mutate()}
            disabled={!canSubmit || uploadMutation.isPending}
            className="btn-primary w-full py-3"
          >
            {uploadMutation.isPending ? 'Uploading & Indexing...' : 'Upload Contract'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ContractsPage() {
  const [showUpload, setShowUpload] = useState(false)
  const queryClient = useQueryClient()

  const { data: contracts, isLoading } = useQuery<Contract[]>({
    queryKey: ['contracts'],
    queryFn: async () => (await api.get('/contracts/')).data,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/contracts/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contracts'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      toast.success('Contract deleted')
    },
  })

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Contracts</h1>
          <p className="text-slate-400 mt-1">Upload and manage your signed contracts</p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Upload Contract
        </button>
      </div>

      {isLoading ? (
        <div className="text-slate-400 animate-pulse">Loading contracts...</div>
      ) : !contracts?.length ? (
        <div className="card text-center py-16">
          <FileText className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">No contracts yet</h3>
          <p className="text-slate-400 mb-6">Upload your first signed contract to start detecting scope creep</p>
          <button onClick={() => setShowUpload(true)} className="btn-primary inline-flex items-center gap-2">
            <Upload className="w-4 h-4" />
            Upload Your First Contract
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {contracts.map((contract) => (
            <div
              key={contract.id}
              className="card flex items-center gap-4 hover:border-slate-700 transition-colors"
            >
              <div className="p-3 bg-primary-900/30 rounded-lg">
                <FileText className="w-5 h-5 text-primary-400" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <h3 className="font-medium text-white truncate">{contract.title}</h3>
                  <StatusBadge status={contract.status} />
                </div>
                <div className="flex items-center gap-4 text-sm text-slate-400">
                  <span>Client: {contract.client_name}</span>
                  {contract.clause_count > 0 && (
                    <span>{contract.clause_count} clauses indexed</span>
                  )}
                  {contract.project_value && (
                    <span>${contract.project_value.toLocaleString()} project</span>
                  )}
                  <span>{formatDistanceToNow(new Date(contract.created_at), { addSuffix: true })}</span>
                </div>
              </div>

              <button
                onClick={() => {
                  if (confirm('Delete this contract and all related data?')) {
                    deleteMutation.mutate(contract.id)
                  }
                }}
                className="text-slate-500 hover:text-red-400 transition-colors p-2"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
    </div>
  )
}