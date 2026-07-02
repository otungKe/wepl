import { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds hover elevation + border emphasis for clickable cards. */
  hoverable?: boolean
}

export function Card({ className, hoverable, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-surface',
        hoverable && 'cursor-pointer transition-colors transition-shadow hover:border-primary/40 hover:shadow-card',
        className,
      )}
      {...rest}
    />
  )
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-4', className)} {...rest} />
}
