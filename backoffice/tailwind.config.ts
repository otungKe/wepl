import type { Config } from 'tailwindcss'

// The console has its own institutional identity (slate + blue), distinct from
// the customer app's green. Uses Tailwind's built-in palette; dark by default.
const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  darkMode: 'class',
  theme: { extend: {} },
  plugins: [],
}
export default config
