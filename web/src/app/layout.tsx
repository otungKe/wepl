import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Toaster } from 'sonner'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'WEPL — Community Finance',
  description: 'Contributions, ROSCA, welfare funds, and emergency advances — now on the web.',
}

// Set the theme class before first paint to avoid a light→dark flash. Reads the
// saved preference, falling back to the OS setting. Kept inline (not a component)
// so it runs before React hydrates.
const themeInitScript = `
(function () {
  try {
    var t = localStorage.getItem('theme');
    if (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}
})();
`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="bg-primary-bg font-sans text-text antialiased">
        {children}
        <Toaster position="top-right" richColors />
      </body>
    </html>
  )
}
