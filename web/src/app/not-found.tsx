import Link from 'next/link'
import { Button } from '@/components/ui/Button'

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-center px-4">
      <p className="text-6xl font-bold text-primary mb-4">404</p>
      <h1 className="text-2xl font-bold text-text mb-2">Page not found</h1>
      <p className="text-text-secondary mb-8">This page doesn&apos;t exist or you don&apos;t have access.</p>
      <Link href="/communities">
        <Button>Go to Communities</Button>
      </Link>
    </div>
  )
}
