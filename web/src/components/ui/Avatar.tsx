import { cn } from '@/lib/utils'
import { avatarColor, initials } from '@/lib/theme'

interface AvatarProps {
  name: string
  src?: string | null
  size?: number
  className?: string
}

export function Avatar({ name, src, size = 40, className }: AvatarProps) {
  const style = { width: size, height: size, fontSize: Math.round(size * 0.4) }
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt={name} style={style} className={cn('rounded-full object-cover', className)} />
  }
  return (
    <div
      style={{ ...style, backgroundColor: avatarColor(name || '?') }}
      className={cn('flex items-center justify-center rounded-full font-semibold text-white shrink-0', className)}
    >
      {initials(name || '?')}
    </div>
  )
}
