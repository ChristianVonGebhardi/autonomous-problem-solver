'use client'

import { useState, useRef, useEffect, Suspense } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useSearchParams } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import {
  Search,
  Send,
  Loader2,
  BookOpen,
  Zap,
  Clock,
  ChevronDown,
  AlertCircle,
} from 'lucide-react'
import { Sidebar } from '@/components/Sidebar'
import { SourceCard } from '@/components/SourceCard'
import { queryCodebase, listRepositories, getQueryHistory } from '@/lib/api'
import type { QueryResponse } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  response?: QueryResponse
  timestamp: Date
}

function QueryPageInner() {
  const searchParams = useSearchParams()
  const initialRepo = searchParams.get('repo') ?? ''
  
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [selectedRepo, setSelectedRepo] = useState<string>(initialRepo)
  const [showHistory, setShowHistory] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { data: repos } = useQuery({
    queryKey: ['repositories'],
    queryFn: listRepositories,
  })

  const { data: history } = useQuery({
    queryKey: ['query-history', selectedRepo],
    queryFn: () => getQueryHistory(selectedRepo || undefined),
    enabled: showHistory,
  })

  const readyRepos = repos?.filter((r) => r.status === 'ready') ?? []

  const mutation = useMutation({
    mutationFn: ({ question, repo }: { question: string; repo: string }) =>
      queryCodebase(question, repo || undefined),
    onSuccess: (data) => {
      const msg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.answer,
        response: data,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, msg])
    },
    onError: (err: unknown) => {
      const errorMsg = err instanceof Error ? err.message : 'Query failed'
      const msg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `**Error:** ${errorMsg}`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, msg])
    },
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = () => {
    const q = input.trim()
    if (!q) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: q,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    mutation.mutate({ question: q, repo: selectedRepo })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const exampleQuestions = [
    'What does the authentication module do?',
    'How is database connection pooling configured?',
    'Which files are responsible for API routing?',
    'Why was the caching layer added?',
    'What are the main entry points of this application?',
  ]

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="bg-white border-b border-slate-200 px-6 py-4 flex items-center gap-4">
          <Search className="text-brand-500" size={20} />
          <div className="flex-1">
            <h1 className="text-lg font-bold text-slate-900">Ask Codebase</h1>
            <p className="text-xs text-slate-500">Natural language queries over your codebase</p>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500">Repository:</label>
            <select
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="text-sm border border-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
            >
              <option value="">All repositories</option>
              {readyRepos.map((r) => (
                <option key={r.id} value={r.name}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50"
          >
            <BookOpen size={13} />
            History
            <ChevronDown size={12} className={showHistory ? 'rotate-180' : ''} />
          </button>
        </div>

        {/* History panel */}
        {showHistory && history && (
          <div className="bg-amber-50 border-b border-amber-200 px-6 py-3 max-h-48 overflow-y-auto">
            <div className="text-xs font-semibold text-amber-700 mb-2">Recent Queries</div>
            <div className="space-y-1.5">
              {history.slice(0, 10).map((h) => (
                <button
                  key={h.id}
                  onClick={() => setInput(h.question)}
                  className="w-full text-left text-xs text-amber-800 hover:text-amber-900 p-2 rounded bg-white/60 hover:bg-white truncate"
                >
                  {h.question}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center py-12">
              <Search size={40} className="text-slate-300 mb-4" />
              <h2 className="text-lg font-semibold text-slate-600 mb-2">
                Ask anything about your codebase
              </h2>
              <p className="text-sm text-slate-400 mb-6 max-w-md">
                Get AI-powered answers grounded in your actual code, commit history, and pull requests
              </p>
              {readyRepos.length === 0 && (
                <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 mb-6">
                  <AlertCircle size={16} />
                  No repositories ingested yet. Ingest a repo first to get meaningful answers.
                </div>
              )}
              <div className="grid grid-cols-1 gap-2 w-full max-w-md">
                {exampleQuestions.map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="text-sm text-left px-4 py-2.5 rounded-lg border border-slate-200 bg-white hover:bg-brand-50 hover:border-brand-300 text-slate-600 hover:text-brand-700 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'user' ? (
                <div className="max-w-2xl">
                  <div className="bg-brand-600 text-white px-4 py-3 rounded-2xl rounded-tr-sm text-sm">
                    {msg.content}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1 text-right">
                    {msg.timestamp.toLocaleTimeString()}
                  </div>
                </div>
              ) : (
                <div className="max-w-3xl w-full">
                  <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm shadow-sm overflow-hidden">
                    <div className="p-5 prose prose-sm max-w-none prose-headings:text-slate-800 prose-p:text-slate-700 prose-code:text-brand-700 prose-strong:text-slate-800">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>

                    {msg.response?.sources && msg.response.sources.length > 0 && (
                      <div className="border-t border-slate-100 px-5 pb-4 pt-3">
                        <div className="text-xs font-semibold text-slate-500 mb-2">
                          Sources ({msg.response.sources.length})
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                          {msg.response.sources.slice(0, 6).map((source, i) => (
                            <SourceCard key={i} source={source} index={i + 1} />
                          ))}
                        </div>
                      </div>
                    )}

                    {msg.response && (
                      <div className="border-t border-slate-100 px-5 py-2 flex items-center gap-3 text-[10px] text-slate-400">
                        <span className="flex items-center gap-1">
                          <Zap size={10} />
                          {msg.response.model_used}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock size={10} />
                          {msg.response.latency_ms}ms
                        </span>
                        {msg.response.cached && (
                          <span className="bg-green-50 text-green-600 px-1.5 rounded">cached</span>
                        )}
                        <span>{msg.response.context_chunks_used} chunks used</span>
                      </div>
                    )}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1">
                    {msg.timestamp.toLocaleTimeString()}
                  </div>
                </div>
              )}
            </div>
          ))}

          {mutation.isPending && (
            <div className="flex justify-start">
              <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm flex items-center gap-3 text-sm text-slate-500">
                <Loader2 size={16} className="animate-spin text-brand-500" />
                Searching knowledge graph and generating answer…
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="bg-white border-t border-slate-200 px-6 py-4">
          <div className="flex gap-3 items-end max-w-4xl mx-auto">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your codebase… (Enter to send, Shift+Enter for newline)"
              rows={2}
              className="flex-1 px-4 py-2.5 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
            />
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || mutation.isPending}
              className="px-4 py-2.5 rounded-xl bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors text-sm font-medium"
            >
              {mutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
              Ask
            </button>
          </div>
          <p className="text-center text-[10px] text-slate-400 mt-2">
            Press Enter to send · Shift+Enter for newline
          </p>
        </div>
      </main>
    </div>
  )
}

export default function QueryPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen bg-slate-50 items-center justify-center text-slate-400">Loading…</div>}>
      <QueryPageInner />
    </Suspense>
  )
}