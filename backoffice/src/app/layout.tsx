import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'WEPL Back Office',
  description: 'WEPL operations console — staff only.',
}

// The console defaults to dark; the shell manages the class after mount. Setting
// it pre-paint avoids a flash for signed-in operators.
const themeInit = `
(function(){try{var t=localStorage.getItem('ops-theme');
if(t!=='light'){document.documentElement.classList.add('dark');}}catch(e){}})();`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeInit }} /></head>
      <body className="bg-slate-50 text-slate-800 dark:bg-slate-950 dark:text-slate-100">{children}</body>
    </html>
  )
}
