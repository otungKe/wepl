'use client'
/**
 * UI primitives preview (UX-02) — a living catalogue of every primitive's state
 * matrix, for visual QA in light and dark. Not linked in the app nav; reach it at
 * /preview. Toggle the theme (top-right) to check both palettes.
 */
import { useState } from 'react'
import { Users, Plus, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input, Textarea, Select } from '@/components/ui/Input'
import { Card, CardBody } from '@/components/ui/Card'
import { StatCard } from '@/components/ui/StatCard'
import { Badge } from '@/components/ui/Badge'
import { Tabs } from '@/components/ui/Tabs'
import { Modal } from '@/components/ui/Modal'
import { EmptyState, ErrorState } from '@/components/ui/EmptyState'
import { Spinner, PageLoader, Skeleton, CardSkeleton } from '@/components/ui/Spinner'
import { ThemeToggle } from '@/components/ui/ThemeToggle'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-bold uppercase tracking-wide text-text-muted">{title}</h2>
      <div className="flex flex-wrap items-start gap-3">{children}</div>
    </section>
  )
}

export default function PreviewPage() {
  const [tab, setTab] = useState('one')
  const [modal, setModal] = useState(false)

  return (
    <div className="min-h-screen bg-primary-bg p-8 text-text">
      <div className="mx-auto max-w-5xl space-y-10">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">UI primitives</h1>
            <p className="text-sm text-text-muted">State matrix for visual QA (UX-02). Toggle the theme →</p>
          </div>
          <ThemeToggle className="border border-border" />
        </header>

        <Section title="Button — variants">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
        </Section>

        <Section title="Button — sizes / states">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
          <Button loading>Loading</Button>
          <Button disabled>Disabled</Button>
          <Button><Plus size={16} /> With icon</Button>
        </Section>

        <Section title="Inputs">
          <div className="grid w-full max-w-md gap-4">
            <Input label="Label" placeholder="Placeholder" />
            <Input label="Required" required placeholder="Required field" />
            <Input label="With hint" hint="Helper text under the field" placeholder="…" />
            <Input label="With error" error="This field is required" defaultValue="bad value" />
            <Input label="Disabled" disabled placeholder="Disabled" />
            <Textarea label="Textarea" placeholder="Multi-line…" />
            <Select label="Select" defaultValue="">
              <option value="" disabled>Choose one…</option>
              <option>Option A</option>
              <option>Option B</option>
            </Select>
          </div>
        </Section>

        <Section title="Badges">
          <Badge tone="neutral">Neutral</Badge>
          <Badge tone="primary">Primary</Badge>
          <Badge tone="success">Success</Badge>
          <Badge tone="warning">Warning</Badge>
          <Badge tone="danger">Danger</Badge>
          <Badge tone="info">Info</Badge>
        </Section>

        <Section title="Cards & stats">
          <Card className="w-56"><CardBody>Basic card</CardBody></Card>
          <Card hoverable className="w-56"><CardBody>Hoverable card</CardBody></Card>
          <StatCard label="Communities" value="12" icon={Users} className="w-56" />
          <StatCard label="Managed" value="KES 1.2M" icon={Wallet} accent className="w-56" />
          <StatCard label="Loading" value="" loading className="w-56" />
        </Section>

        <Section title="Tabs">
          <Tabs
            className="w-full"
            active={tab}
            onChange={setTab}
            tabs={[
              { key: 'one', label: 'Overview' },
              { key: 'two', label: 'Members', badge: 3 },
              { key: 'three', label: 'Activity' },
            ]}
          />
        </Section>

        <Section title="Loading">
          <Spinner size={24} className="text-primary" />
          <div className="w-56"><Skeleton className="h-10 w-full" /></div>
          <CardSkeleton className="w-72" />
          <div className="w-full"><PageLoader label="Loading…" /></div>
        </Section>

        <Section title="Empty & error states">
          <div className="w-full max-w-md">
            <EmptyState icon={Users} title="No communities yet" description="Create one to get started."
              action={<Button size="sm"><Plus size={15} /> Create</Button>} />
          </div>
          <div className="w-full max-w-md">
            <ErrorState onRetry={() => {}} />
          </div>
        </Section>

        <Section title="Modal">
          <Button onClick={() => setModal(true)}>Open modal</Button>
          <Modal open={modal} onClose={() => setModal(false)} title="Example modal">
            <p className="text-sm text-text-secondary">Modal body content goes here.</p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setModal(false)}>Cancel</Button>
              <Button size="sm" onClick={() => setModal(false)}>Confirm</Button>
            </div>
          </Modal>
        </Section>
      </div>
    </div>
  )
}
