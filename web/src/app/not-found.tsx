import Link from 'next/link'
import { Button } from '@/components/ui/Button'

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-primary-bg px-4 text-center">
      <p className="text-5xl font-bold text-primary">404</p>
      <p className="text-text-secondary">This page could not be found.</p>
      <Link href="/communities"><Button>Go home</Button></Link>
    </div>
  )
}
