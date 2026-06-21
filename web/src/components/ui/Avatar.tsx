import { avatarColor, initials } from '@/lib/theme'
import { cn } from '@/lib/utils'
import Image from 'next/image'

interface Props {
  name: string
  src?: string | null
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  online?: boolean | null
  className?: string
}

const sizes = {
  xs: 'w-6 h-6 text-xs',
  sm: 'w-8 h-8 text-sm',
  md: 'w-10 h-10 text-base',
  lg: 'w-12 h-12 text-lg',
  xl: 'w-16 h-16 text-xl',
}

const dotSizes = {
  xs: 'w-1.5 h-1.5 bottom-0 right-0',
  sm: 'w-2 h-2 bottom-0 right-0',
  md: 'w-2.5 h-2.5 bottom-0.5 right-0.5',
  lg: 'w-3 h-3 bottom-0.5 right-0.5',
  xl: 'w-3.5 h-3.5 bottom-1 right-1',
}

export function Avatar({ name, src, size = 'md', online, className }: Props) {
  const bg = avatarColor(name)

  return (
    <div className={cn('relative inline-flex flex-shrink-0', sizes[size], className)}>
      <div
        className={cn('w-full h-full rounded-full flex items-center justify-center overflow-hidden')}
        style={{ backgroundColor: src ? undefined : bg }}
      >
        {src
          ? <Image src={src} alt={name} fill className="object-cover" />
          : <span className="font-semibold text-white leading-none">{initials(name)}</span>
        }
      </div>
      {online !== null && online !== undefined && (
        <span
          className={cn(
            'absolute rounded-full border-2 border-white',
            dotSizes[size],
            online ? 'bg-success' : 'bg-text-muted'
          )}
        />
      )}
    </div>
  )
}
