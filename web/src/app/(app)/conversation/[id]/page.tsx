'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { conversations as convApi } from '@/lib/api'
import { WS_URL } from '@/lib/api'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { ArrowLeft, Send, Smile, Paperclip, CornerDownLeft } from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { formatTime, formatDate, cn } from '@/lib/utils'
import { toast } from 'sonner'

const QUICK_REACTIONS = ['❤️', '👍', '😂', '😮', '😢', '🙏']

interface Message {
  id: string
  sender_id: string
  sender_name: string
  sender_photo?: string
  content: string
  created_at: string
  reactions?: Record<string, string[]>
  reply_to?: { id: string; content: string; sender_name: string }
  is_edited?: boolean
}

interface Conversation {
  id: string
  name: string
  participants?: { id: string; name: string; profile_photo?: string }[]
}

export default function ConversationPage() {
  const { id }   = useParams<{ id: string }>()
  const router   = useRouter()
  const user     = useAuthStore(s => s.user)

  const [conv, setConv]         = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [text, setText]         = useState('')
  const [replyTo, setReplyTo]   = useState<Message | null>(null)
  const [typingNames, setTypingNames] = useState<string[]>([])
  const [sending, setSending]   = useState(false)

  const wsRef        = useRef<WebSocket | null>(null)
  const bottomRef    = useRef<HTMLDivElement>(null)
  const inputRef     = useRef<HTMLTextAreaElement>(null)
  const typingTimer  = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load initial data
  const load = useCallback(async () => {
    try {
      const [convRes, msgsRes] = await Promise.all([
        convApi.get(id),
        convApi.messages(id),
      ])
      setConv(convRes.data)
      const msgs: Message[] = (msgsRes.data.results ?? msgsRes.data).reverse()
      setMessages(msgs)
      convApi.markRead(id).catch(() => {})
    } catch {
      toast.error('Failed to load conversation')
    }
  }, [id])

  useEffect(() => { load() }, [load])

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // WebSocket
  useEffect(() => {
    const token = localStorage.getItem('access_token')
    const ws = new WebSocket(`${WS_URL}/ws/conversations/${id}/?token=${token}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.type === 'message') {
        setMessages(prev => [...prev, data.message])
      } else if (data.type === 'typing') {
        setTypingNames(data.names ?? [])
        if (typingTimer.current) clearTimeout(typingTimer.current)
        typingTimer.current = setTimeout(() => setTypingNames([]), 3000)
      } else if (data.type === 'reaction') {
        setMessages(prev => prev.map(m =>
          m.id === data.message_id ? { ...m, reactions: data.reactions } : m
        ))
      }
    }

    return () => { ws.close(); wsRef.current = null }
  }, [id])

  function sendTyping() {
    wsRef.current?.send(JSON.stringify({ type: 'typing' }))
  }

  async function sendMessage() {
    if (!text.trim()) return
    setSending(true)
    try {
      await convApi.send(id, {
        content: text.trim(),
        reply_to: replyTo?.id ?? null,
      })
      setText('')
      setReplyTo(null)
    } catch {
      toast.error('Failed to send message')
    } finally {
      setSending(false)
    }
    inputRef.current?.focus()
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  async function react(msgId: string, emoji: string) {
    try { await convApi.react(id, msgId, emoji) } catch { toast.error('Reaction failed') }
  }

  // Group messages by date
  const grouped = groupByDate(messages)

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3.5 border-b border-divider bg-white sticky top-0 z-10 shadow-sm">
        <button onClick={() => router.back()} className="p-1.5 rounded-lg hover:bg-divider text-text-secondary">
          <ArrowLeft size={18} />
        </button>
        <div className="flex -space-x-1">
          {(conv?.participants ?? []).slice(0, 3).map(p => (
            <Avatar key={p.id} name={p.name} src={p.profile_photo} size="sm" className="border-2 border-white" />
          ))}
        </div>
        <div>
          <p className="font-semibold text-text">{conv?.name ?? '…'}</p>
          {typingNames.length > 0 && (
            <p className="text-xs text-text-secondary animate-pulse">
              {typingNames.join(', ')} {typingNames.length === 1 ? 'is' : 'are'} typing…
            </p>
          )}
          {typingNames.length === 0 && conv?.participants && (
            <p className="text-xs text-text-muted">{conv.participants.length} members</p>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
        {grouped.map(({ date, msgs }) => (
          <div key={date}>
            <div className="flex justify-center my-3">
              <span className="text-xs text-text-muted bg-divider rounded-full px-3 py-1">{date}</span>
            </div>
            {msgs.map((msg, i) => {
              const isMine = msg.sender_id === user?.id
              const isFirst = i === 0 || msgs[i-1].sender_id !== msg.sender_id
              return (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  isMine={isMine}
                  showAvatar={!isMine && isFirst}
                  onReply={setReplyTo}
                  onReact={react}
                />
              )
            })}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Reply preview */}
      {replyTo && (
        <div className="mx-4 mb-1 flex items-center gap-2 bg-primary-pale rounded-lg px-3 py-2 border-l-4 border-primary">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-primary">{replyTo.sender_name}</p>
            <p className="text-xs text-text-secondary truncate">{replyTo.content}</p>
          </div>
          <button onClick={() => setReplyTo(null)} className="text-text-muted hover:text-text p-0.5">✕</button>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-divider bg-white px-4 py-3 flex items-end gap-3">
        <button className="p-2 rounded-lg hover:bg-divider text-text-muted flex-shrink-0">
          <Paperclip size={18} />
        </button>
        <textarea
          ref={inputRef}
          value={text}
          onChange={e => { setText(e.target.value); sendTyping() }}
          onKeyDown={handleKey}
          placeholder="Type a message… (Enter to send, Shift+Enter for new line)"
          rows={1}
          className={cn(
            'flex-1 resize-none rounded-lg border border-border bg-primary-bg px-3 py-2.5 text-sm text-text',
            'placeholder:text-text-muted focus:outline-none focus:border-primary max-h-32',
          )}
          style={{ overflowY: text.split('\n').length > 3 ? 'auto' : 'hidden' }}
        />
        <button className="p-2 rounded-lg hover:bg-divider text-text-muted flex-shrink-0">
          <Smile size={18} />
        </button>
        <Button size="sm" onClick={sendMessage} loading={sending} className="flex-shrink-0 h-9 px-3">
          <Send size={16} />
        </Button>
      </div>
    </div>
  )
}

// ── MessageBubble ─────────────────────────────────────────────────────────────
function MessageBubble({ msg, isMine, showAvatar, onReply, onReact }: {
  msg: Message; isMine: boolean; showAvatar: boolean;
  onReply: (m: Message) => void; onReact: (id: string, emoji: string) => void
}) {
  const [showReactions, setShowReactions] = useState(false)

  return (
    <div
      className={cn('flex items-end gap-2 group', isMine ? 'flex-row-reverse' : 'flex-row')}
      onMouseEnter={() => {}} onMouseLeave={() => setShowReactions(false)}
    >
      {/* Avatar */}
      {!isMine && (
        <div className="w-8 flex-shrink-0">
          {showAvatar && <Avatar name={msg.sender_name} src={msg.sender_photo} size="sm" />}
        </div>
      )}

      <div className={cn('max-w-[68%] flex flex-col', isMine ? 'items-end' : 'items-start')}>
        {/* Sender name */}
        {!isMine && showAvatar && (
          <p className="text-xs font-semibold text-text-secondary mb-1 ml-1">{msg.sender_name}</p>
        )}

        {/* Reply preview */}
        {msg.reply_to && (
          <div className={cn(
            'mb-1 border-l-2 border-primary px-2 py-1 rounded text-xs text-text-secondary max-w-full',
            isMine ? 'bg-primary/10' : 'bg-divider'
          )}>
            <p className="font-semibold text-primary text-xs">{msg.reply_to.sender_name}</p>
            <p className="truncate">{msg.reply_to.content}</p>
          </div>
        )}

        {/* Bubble */}
        <div className="relative group/bubble">
          <div
            className={cn(
              'rounded-2xl px-3.5 py-2.5 text-sm leading-snug',
              isMine
                ? 'bg-bubble-sent text-bubble-sent-text rounded-br-sm'
                : 'bg-bubble-received text-bubble-recv-text rounded-bl-sm'
            )}
          >
            <p className="whitespace-pre-wrap break-words">{msg.content}</p>
            {msg.is_edited && <span className="text-xs opacity-60 ml-1">(edited)</span>}
          </div>

          {/* Hover actions */}
          <div className={cn(
            'absolute top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover/bubble:opacity-100 transition-opacity',
            isMine ? '-left-20' : '-right-20'
          )}>
            <button
              onClick={() => setShowReactions(s => !s)}
              className="p-1.5 rounded-full bg-white shadow-card hover:bg-divider text-text-muted text-xs"
            >😊</button>
            <button
              onClick={() => onReply(msg)}
              className="p-1.5 rounded-full bg-white shadow-card hover:bg-divider text-text-muted"
            ><CornerDownLeft size={12} /></button>
          </div>

          {/* Quick reactions popup */}
          {showReactions && (
            <div className={cn(
              'absolute bottom-full mb-1 flex gap-1 bg-white shadow-modal rounded-full px-2 py-1 z-20',
              isMine ? 'right-0' : 'left-0'
            )}>
              {QUICK_REACTIONS.map(emoji => (
                <button
                  key={emoji}
                  onClick={() => { onReact(msg.id, emoji); setShowReactions(false) }}
                  className="text-lg hover:scale-125 transition-transform"
                >{emoji}</button>
              ))}
            </div>
          )}
        </div>

        {/* Reactions */}
        {msg.reactions && Object.keys(msg.reactions).length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {Object.entries(msg.reactions).map(([emoji, users]) => users.length > 0 && (
              <span
                key={emoji}
                onClick={() => onReact(msg.id, emoji)}
                className="inline-flex items-center gap-0.5 bg-divider rounded-full px-2 py-0.5 text-xs cursor-pointer hover:bg-primary-pale"
              >
                {emoji} <span className="text-text-secondary">{users.length}</span>
              </span>
            ))}
          </div>
        )}

        {/* Timestamp */}
        <p className="text-xs text-text-muted mt-0.5 mx-1">{formatTime(msg.created_at)}</p>
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function groupByDate(messages: Message[]): { date: string; msgs: Message[] }[] {
  const map = new Map<string, Message[]>()
  const today   = new Date()
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1)

  for (const m of messages) {
    const d = new Date(m.created_at)
    let label: string
    if (isSameDay(d, today))     label = 'Today'
    else if (isSameDay(d, yesterday)) label = 'Yesterday'
    else label = formatDate(m.created_at)

    if (!map.has(label)) map.set(label, [])
    map.get(label)!.push(m)
  }

  return Array.from(map.entries()).map(([date, msgs]) => ({ date, msgs }))
}

function isSameDay(a: Date, b: Date) {
  return a.getDate() === b.getDate() && a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()
}
