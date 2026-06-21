'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { Send, ArrowLeft, CornerUpLeft, SmilePlus, X } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { conversations, apiError, WS_URL, type Conversation, type Message } from '@/lib/api'
import { Avatar } from '@/components/ui/Avatar'
import { PageLoader } from '@/components/ui/Spinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { getAccessToken } from '@/lib/auth'
import { useAuthStore } from '@/store/auth'
import { formatTime, formatDate, cn } from '@/lib/utils'
import { toast } from 'sonner'

const EMOJIS = ['👍', '❤️', '😂', '🙏', '🔥', '👏']

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const me = useAuthStore(s => s.user?.phone_number)
  const [conv, setConv] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [replyTo, setReplyTo] = useState<Message | null>(null)
  const [pickerFor, setPickerFor] = useState<number | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const scrollDown = useCallback(() => setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50), [])

  useEffect(() => {
    Promise.all([conversations.get(id), conversations.messages(id)])
      .then(([cv, msgs]) => { setConv(cv.data); setMessages(msgs); scrollDown() })
      .catch(e => toast.error(apiError(e)))
      .finally(() => setLoading(false))
    conversations.markRead(id).catch(() => {})
  }, [id, scrollDown])

  useEffect(() => {
    const token = getAccessToken()
    if (!token) return
    const ws = new WebSocket(`${WS_URL}/ws/conversation/${id}/?token=${token}`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.type === 'message') {
        setMessages(prev => prev.some(m => m.id === data.id) ? prev : [...prev, data as Message])
        scrollDown()
      } else if (data.type === 'reaction' || data.type === 'message_edited') {
        conversations.messages(id).then(setMessages).catch(() => {})
      } else if (data.type === 'message_deleted') {
        setMessages(prev => prev.filter(m => m.id !== data.id))
      }
    }
    return () => ws.close()
  }, [id, scrollDown])

  function send() {
    const content = text.trim()
    if (!content) return
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'message', content, reply_to_id: replyTo?.id }))
    } else {
      conversations.send(id, content, replyTo?.id).then(m => { setMessages(prev => [...prev, m.data]); scrollDown() }).catch(e => toast.error(apiError(e)))
    }
    setText(''); setReplyTo(null)
  }

  async function react(msgId: number, emoji: string) {
    setPickerFor(null)
    try { await conversations.react(msgId, emoji) } catch (e) { toast.error(apiError(e)) }
  }

  if (loading) return <PageLoader />

  // group by date
  const groups: { date: string; msgs: Message[] }[] = []
  for (const m of messages) {
    const d = formatDate(m.created_at)
    const last = groups[groups.length - 1]
    if (last && last.date === d) last.msgs.push(m)
    else groups.push({ date: d, msgs: [m] })
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col lg:h-[calc(100vh-3.5rem)]">
      <div className="flex items-center gap-3 border-b border-border pb-3">
        <button onClick={() => router.back()} className="rounded-lg p-1 text-text-secondary hover:bg-divider"><ArrowLeft size={20} /></button>
        <div>
          <p className="font-bold text-text">{conv?.topic}</p>
          <p className="text-xs text-text-muted">{conv?.message_count ?? 0} messages</p>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto py-4">
        {messages.length === 0 ? (
          <EmptyState title="No messages yet" description="Be the first to say something." />
        ) : groups.map(g => (
          <div key={g.date}>
            <div className="mb-3 flex justify-center"><span className="rounded-full bg-divider px-3 py-0.5 text-xs text-text-muted">{g.date}</span></div>
            <div className="space-y-2">
              {g.msgs.map(m => {
                const mine = m.sender_phone === me
                if (m.message_type === 'system') {
                  return <div key={m.id} className="text-center text-xs text-text-muted">{m.content}</div>
                }
                return (
                  <div key={m.id} className={cn('group flex items-end gap-2', mine ? 'flex-row-reverse' : '')}>
                    {!mine && <Avatar name={m.sender} size={28} />}
                    <div className={cn('relative max-w-[78%] rounded-2xl px-3.5 py-2', mine ? 'bg-primary text-white' : 'bg-divider text-text')}>
                      {!mine && <p className="mb-0.5 text-xs font-semibold text-primary">{m.sender}</p>}
                      {m.reply_to && (
                        <div className={cn('mb-1 rounded-lg border-l-2 px-2 py-1 text-xs', mine ? 'border-white/50 bg-white/10' : 'border-primary/40 bg-white/50')}>
                          {m.reply_to.deleted ? 'Deleted message' : `${m.reply_to.sender}: ${m.reply_to.content}`}
                        </div>
                      )}
                      <p className="whitespace-pre-wrap break-words text-sm">{m.content}</p>
                      <p className={cn('mt-0.5 text-right text-[10px]', mine ? 'text-white/70' : 'text-text-muted')}>{formatTime(m.created_at)}{m.is_edited ? ' · edited' : ''}</p>
                      {Object.keys(m.reactions || {}).length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {Object.entries(m.reactions).map(([emoji, users]) => (
                            <span key={emoji} className="rounded-full bg-white/90 px-1.5 text-xs text-text shadow-sm">{emoji} {users.length}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button onClick={() => setReplyTo(m)} className="rounded-full p-1 text-text-muted hover:bg-divider"><CornerUpLeft size={15} /></button>
                      <div className="relative">
                        <button onClick={() => setPickerFor(pickerFor === m.id ? null : m.id)} className="rounded-full p-1 text-text-muted hover:bg-divider"><SmilePlus size={15} /></button>
                        {pickerFor === m.id && (
                          <div className="absolute bottom-8 z-10 flex gap-1 rounded-full border border-border bg-surface px-2 py-1 shadow-modal">
                            {EMOJIS.map(em => <button key={em} onClick={() => react(m.id, em)} className="text-lg hover:scale-125">{em}</button>)}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {replyTo && (
        <div className="flex items-center justify-between rounded-t-lg border border-b-0 border-border bg-divider/60 px-3 py-2 text-sm">
          <span className="truncate text-text-secondary">Replying to <span className="font-medium">{replyTo.sender}</span>: {replyTo.content}</span>
          <button onClick={() => setReplyTo(null)} className="text-text-muted hover:text-text"><X size={16} /></button>
        </div>
      )}
      <div className="flex items-center gap-2 border-t border-border pt-3">
        <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Type a message" className="h-11 flex-1 rounded-full border border-border bg-white px-4 text-base focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20" />
        <button onClick={send} disabled={!text.trim()} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-white disabled:opacity-50">
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}
