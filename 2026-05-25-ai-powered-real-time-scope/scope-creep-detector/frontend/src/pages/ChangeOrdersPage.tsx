import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardList,
  Check,
  Send,
  Download,
  Edit3,
  DollarSign,
  Clock,
  ChevronDown,
  ChevronUp,
  X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'
import api from '../api'
import type { ChangeOrder } from '../types'

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    draft: { label: 'Draft', cls: 'bg-slate-800 text-slate-400 border-slate-600' },
    approved: { label: 'Approved', cls: 'bg-green-900/40 text-green-400 border-green-800' },
    sent: { label: 'Sent', cls: 'bg-primary-900/40 text-primary-400 border-primary-800' },
    accepted: { label: 'Accepted', cls: 'bg-emerald-900/40 text-emerald-400 border-emerald-800' },
    declined: { label: 'Declined', cls: 'bg-red-900/40 text-red-400 border-red-800' },
  }
  const c = config[status] ?? config.draft
  return (
    <span className={clsx('text-xs px-2 py-0.5 rounded-full border', c.cls)}>
      {c.label}
    </span>
  )
}

interface EditModalProps {
  order: ChangeOrder
  onClose: () => void
}

function EditModal({ order, onClose }: EditModalProps) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    title: order.title,
    description: order.description,
    scope_addition: order.scope_addition,
    estimated_hours: order.estimated_hours,
    hourly_rate: order.hourly_rate,
    terms: order.terms ?? '',
  })

  const updateMutation = useMutation({
    mutationFn: () => api.patch(`/change-orders/${order.id}`, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-orders'] })
      toast.success('Change order updated')
      onClose()
    },
    onError: () => toast.error('Failed to update change order'),
  })

  const total = form.estimated_hours * form.hourly_rate

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4 overflow-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl p-6 my-4">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-white">Edit Change Order</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Title</label>
            <input
              type="text"
              className="input-field"
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Description</label>
            <textarea
              rows={3}
              className="input-field resize-none"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Scope Addition</label>
            <textarea
              rows={4}
              className="input-field resize-none"
              value={form.scope_addition}
              onChange={e => setForm(f => ({ ...f, scope_addition: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Hours</label>
              <input
                type="number"
                step="0.5"
                className="input-field"
                value={form.estimated_hours}
                onChange={e => setForm(f => ({ ...f, estimated_hours: parseFloat(e.target.value) || 0 }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Rate ($/hr)</label>
              <input
                type="number"
                className="input-field"
                value={form.hourly_rate}
                onChange={e => setForm(f => ({ ...f, hourly_rate: parseFloat(e.target.value) || 0 }))}
              />
            </div>
          </div>
          <div className="bg-slate-800 rounded-lg p-3 flex items-center justify-between">
            <span className="text-slate-400">Total</span>
            <span className="text-xl font-bold text-green-400">${total.toLocaleString()}</span>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Payment Terms</label>
            <textarea
              rows={2}
              className="input-field resize-none"
              value={form.terms}
              onChange={e => setForm(f => ({ ...f, terms: e.target.value }))}
            />
          </div>

          <div className="flex gap-3">
            <button onClick={onClose} className="btn-secondary flex-1">Cancel</button>
            <button
              onClick={() => updateMutation.mutate()}
              disabled={updateMutation.isPending}
              className="btn-primary flex-1"
            >
              {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function ChangeOrderCard({ order }: { order: ChangeOrder }) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const queryClient = useQueryClient()

  const approveMutation = useMutation({
    mutationFn: () => api.post(`/change-orders/${order.id}/approve`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-orders'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      toast.success('Change order approved! 🎉')
    },
    onError: () => toast.error('Failed to approve'),
  })

  const sendMutation = useMutation({
    mutationFn: () => api.post(`/change-orders/${order.id}/send`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-orders'] })
      toast.success('Change order marked as sent')
    },
  })

  const downloadPdf = async () => {
    try {
      const response = await api.get(`/change-orders/${order.id}/pdf`, {
        responseType: 'blob',
      })
      const blob = new Blob([response.data], { type: response.headers['content-type'] })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `change-order-${order.id.slice(0, 8)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('PDF not available yet')
    }
  }

  return (
    <>
      <div className="card">
        <div className="flex items-start gap-4">
          <div className="p-2 bg-primary-900/30 rounded-lg flex-shrink-0">
            <ClipboardList className="w-5 h-5 text-primary-400" />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap mb-1">
              <h3 className="font-semibold text-white">{order.title}</h3>
              <StatusBadge status={order.status} />
            </div>

            <div className="flex items-center gap-4 text-sm text-slate-400 mb-3">
              <div className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {order.estimated_hours}h @ ${order.hourly_rate}/hr
              </div>
              <div className="flex items-center gap-1 text-green-400 font-bold">
                <DollarSign className="w-3.5 h-3.5" />
                ${order.total_cost.toLocaleString()}
              </div>
              <span className="text-slate-500">
                {formatDistanceToNow(new Date(order.created_at), { addSuffix: true })}
              </span>
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2 flex-wrap">
              {order.status === 'draft' && (
                <>
                  <button
                    onClick={() => setEditing(true)}
                    className="btn-secondary text-sm py-1.5 px-3 flex items-center gap-1"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                    Edit
                  </button>
                  <button
                    onClick={() => approveMutation.mutate()}
                    disabled={approveMutation.isPending}
                    className="btn-primary text-sm py-1.5 px-3 flex items-center gap-1"
                  >
                    <Check className="w-3.5 h-3.5" />
                    {approveMutation.isPending ? 'Approving...' : 'Approve'}
                  </button>
                </>
              )}
              {order.status === 'approved' && (
                <button
                  onClick={() => sendMutation.mutate()}
                  disabled={sendMutation.isPending}
                  className="btn-primary text-sm py-1.5 px-3 flex items-center gap-1"
                >
                  <Send className="w-3.5 h-3.5" />
                  Mark as Sent
                </button>
              )}
              {order.pdf_path && (
                <button
                  onClick={downloadPdf}
                  className="btn-secondary text-sm py-1.5 px-3 flex items-center gap-1"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download PDF
                </button>
              )}
            </div>
          </div>

          <button
            onClick={() => setExpanded(!expanded)}
            className="text-slate-400 hover:text-white p-1 flex-shrink-0"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>

        {expanded && (
          <div className="mt-4 pt-4 border-t border-slate-800 space-y-3">
            <div>
              <h4 className="text-sm font-semibold text-slate-300 mb-1">Description</h4>
              <p className="text-sm text-slate-400">{order.description}</p>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-300 mb-1">Scope Addition</h4>
              <p className="text-sm text-slate-400 bg-slate-800/50 rounded-lg p-3">
                {order.scope_addition}
              </p>
            </div>
            {order.terms && (
              <div>
                <h4 className="text-sm font-semibold text-slate-300 mb-1">Terms</h4>
                <p className="text-sm text-slate-400">{order.terms}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {editing && <EditModal order={order} onClose={() => setEditing(false)} />}
    </>
  )
}

export default function ChangeOrdersPage() {
  const [statusFilter, setStatusFilter] = useState('all')

  const { data: changeOrders, isLoading } = useQuery<ChangeOrder[]>({
    queryKey: ['change-orders'],
    queryFn: async () => (await api.get('/change-orders/')).data,
  })

  const filtered = changeOrders?.filter(
    co => statusFilter === 'all' || co.status === statusFilter
  )

  const totalValue = filtered?.reduce((sum, co) => sum + co.total_cost, 0) ?? 0
  const approvedValue = changeOrders
    ?.filter(co => ['approved', 'sent', 'accepted'].includes(co.status))
    .reduce((sum, co) => sum + co.total_cost, 0) ?? 0

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Change Orders</h1>
        <p className="text-slate-400 mt-1">Auto-generated from detected scope violations</p>
      </div>

      {/* Revenue summary */}
      {(changeOrders?.length ?? 0) > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div className="card">
            <div className="text-sm text-slate-400 mb-1">Total Potential Revenue</div>
            <div className="text-2xl font-bold text-white">${totalValue.toLocaleString()}</div>
          </div>
          <div className="card">
            <div className="text-sm text-slate-400 mb-1">Approved / Recovered</div>
            <div className="text-2xl font-bold text-green-400">${approvedValue.toLocaleString()}</div>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {['all', 'draft', 'approved', 'sent', 'accepted', 'declined'].map((s) => {
          const count = s === 'all'
            ? changeOrders?.length ?? 0
            : changeOrders?.filter(co => co.status === s).length ?? 0
          return (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-sm font-medium capitalize transition-colors',
                statusFilter === s
                  ? 'bg-primary-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              )}
            >
              {s === 'all' ? 'All' : s}
              {count > 0 && <span className="ml-1.5 text-xs opacity-70">({count})</span>}
            </button>
          )
        })}
      </div>

      {isLoading ? (
        <div className="text-slate-400 animate-pulse">Loading change orders...</div>
      ) : !filtered?.length ? (
        <div className="card text-center py-16">
          <ClipboardList className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">No change orders yet</h3>
          <p className="text-slate-400">
            Change orders are automatically generated when scope creep is detected in client messages
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((co) => (
            <ChangeOrderCard key={co.id} order={co} />
          ))}
        </div>
      )}
    </div>
  )
}