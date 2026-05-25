import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Send, Loader, CheckCircle, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import api from '../api'
import type { Contract, Message } from '../types'

const SAMPLE_MESSAGES = [
  {
    label: "Logo redesign request",
    text: "Hey! Love the website so far. Can you also redesign our company logo while you're at it? We want a fresh look. Shouldn't take too long!"
  },
  {
    label: "Social media add-on",
    text: "Quick question - could you also set up our social media profiles and create content for the first month? Instagram, Twitter, LinkedIn. Let's make a big splash on launch!"
  },
  {
    label: "Mobile app request",
    text: "The website looks great! Now we're thinking we should also have a mobile app. Can you build iOS and Android versions? We need it before the website launches."
  },
  {
    label: "In-scope message",
    text: "Hi, I reviewed the homepage mockup and I have some minor feedback on the hero section colors. Could you try a darker blue instead of the current one?"
  }
]

export default function MessagesPage() {
  const queryClient = useQueryClient()
  const [selectedContract, setSelectedContract] = useState('')
  const [messageText, setMessageText] = useState('')
  const [senderName, setSenderName] = useState('')
  const [senderEmail, setSenderEmail] = useState('')
  const [subject, setSubject] = useState('')

  const { data: contracts } = useQuery<Contract[]>({
    queryKey: ['contracts'],
    queryFn: async () => (await api.get('/contracts/')).data,
  })

  const { data: messages } = useQuery<Message[]>({
    queryKey: ['messages'],
    queryFn: async () => (await api.get('/messages/')).data,
  })

  const activeContracts = contracts?.filter(c => c.status === 'active') ?? []

  const analyzeMutation = useMutation({
    mutationFn: async () => {
      return (await api.post('/messages/analyze', {
        contract_id: selectedContract,
        content: messageText,
        sender_name: senderName || undefined,
        sender_email: senderEmail || undefined,
        subject: subject || undefined,
        source: 'manual',
      })).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages'] })
      toast.success('Message submitted for analysis! Results will appear in Violations.')
      setMessageText('')
      setSenderName('')
      setSenderEmail('')
      setSubject('')
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail ?? 'Analysis failed')
    },
  })

  const canSubmit = selectedContract && messageText.trim().length > 10

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Analyze Message</h1>
        <p className="text-slate-400 mt-1">
          Paste a client message to check if it requests out-of-scope work
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Input form */}
        <div className="card space-y-4">
          <h2 className="text-lg font-semibold text-white">Client Message</h2>

          {/* Contract selector */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Select Contract *
            </label>
            {activeContracts.length === 0 ? (
              <div className="text-sm text-slate-500 bg-slate-800 rounded-lg p-3">
                No active contracts. <a href="/contracts" className="text-primary-400 hover:underline">Upload one first →</a>
              </div>
            ) : (
              <select
                className="input-field"
                value={selectedContract}
                onChange={(e) => setSelectedContract(e.target.value)}
              >
                <option value="">Choose a contract...</option>
                {activeContracts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title} — {c.client_name}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Optional fields */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Sender Name <span className="text-slate-500">(opt)</span>
              </label>
              <input
                type="text"
                placeholder="John Smith"
                className="input-field"
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Subject <span className="text-slate-500">(opt)</span>
              </label>
              <input
                type="text"
                placeholder="Re: Project Update"
                className="input-field"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              />
            </div>
          </div>

          {/* Message content */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Message Content *
            </label>
            <textarea
              rows={8}
              placeholder="Paste the client message here..."
              className="input-field resize-none"
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
            />
            <p className="text-xs text-slate-500 mt-1">{messageText.length} characters</p>
          </div>

          <button
            onClick={() => analyzeMutation.mutate()}
            disabled={!canSubmit || analyzeMutation.isPending}
            className="btn-primary w-full py-3 flex items-center justify-center gap-2"
          >
            {analyzeMutation.isPending ? (
              <>
                <Loader className="w-4 h-4 animate-spin" />
                Analyzing with AI...
              </>
            ) : (
              <>
                <Send className="w-4 h-4" />
                Analyze for Scope Creep
              </>
            )}
          </button>
        </div>

        {/* Sample messages + history */}
        <div className="space-y-4">
          {/* Sample messages */}
          <div className="card">
            <h3 className="text-base font-semibold text-white mb-3">💡 Try a Sample Message</h3>
            <div className="space-y-2">
              {SAMPLE_MESSAGES.map((sample) => (
                <button
                  key={sample.label}
                  onClick={() => setMessageText(sample.text)}
                  className="w-full text-left p-3 bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
                >
                  <div className="text-sm font-medium text-slate-200">{sample.label}</div>
                  <div className="text-xs text-slate-400 mt-0.5 line-clamp-1">{sample.text}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Recent messages */}
          <div className="card">
            <h3 className="text-base font-semibold text-white mb-3">Recent Messages</h3>
            {!messages?.length ? (
              <div className="text-center py-4 text-slate-500 text-sm">
                <MessageSquare className="w-6 h-6 mx-auto mb-1 opacity-40" />
                No messages analyzed yet
              </div>
            ) : (
              <div className="space-y-2">
                {messages.slice(0, 8).map((m) => (
                  <div key={m.id} className="flex items-start gap-2 p-2 rounded-lg bg-slate-800/50">
                    {m.analyzed ? (
                      <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                    ) : (
                      <Clock className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0 animate-spin" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-slate-300 line-clamp-2">{m.content}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}