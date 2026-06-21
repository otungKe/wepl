import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Toaster } from 'sonner'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'WEPL — Community Finance',
  description: 'Contributions, ROSCA, welfare funds, and emergency advances — now on the web.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-primary-bg font-sans text-text antialiased">
        {children}
        <Toaster position="top-right" richColors />
      </body>
    </html>
  )
}
