import type { Config } from 'tailwindcss'

// Semantic color backed by a CSS variable (RGB channels in globals.css).
// The `<alpha-value>` shim keeps Tailwind opacity modifiers (e.g. bg-primary/50).
const v = (name: string) => `rgb(var(--color-${name}) / <alpha-value>)`

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  // Dark mode is opt-in via a `.dark` class on <html> (set pre-paint in layout.tsx
  // to avoid a flash). Token *values* live in globals.css :root / .dark.
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Primary — forest green (matches mobile theme.ts)
        primary: {
          DEFAULT: v('primary'),
          dark:    v('primary-dark'),
          light:   v('primary-light'),
          pale:    v('primary-pale'),
          bg:      v('primary-bg'),
        },
        // Accent gold
        accent: {
          DEFAULT: v('accent'),
          pale:    v('accent-pale'),
        },
        // Surfaces
        surface: v('surface'),
        border:  v('border'),
        divider: v('divider'),
        // Text
        text: {
          DEFAULT:   v('text'),
          secondary: v('text-secondary'),
          muted:     v('text-muted'),
        },
        // Status
        success: v('success'),
        warning: v('warning'),
        error:   v('error'),
        info:    v('info'),
        // Chat bubbles
        bubble: {
          sent:         v('bubble-sent'),
          received:     v('bubble-received'),
          'sent-text':  v('bubble-sent-text'),
          'recv-text':  v('bubble-recv-text'),
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        xs:   ['11px', '16px'],
        sm:   ['13px', '18px'],
        base: ['15px', '22px'],
        lg:   ['17px', '24px'],
        xl:   ['20px', '28px'],
        '2xl':['26px', '34px'],
        '3xl':['34px', '42px'],
      },
      borderRadius: {
        sm:   '6px',
        DEFAULT: '10px',
        lg:   '14px',
        full: '9999px',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        fab:  'var(--shadow-fab)',
        modal:'var(--shadow-modal)',
      },
      keyframes: {
        slideUp: {
          '0%':   { transform: 'translateY(12px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',     opacity: '1' },
        },
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        slideUp: 'slideUp 0.2s ease-out',
        fadeIn:  'fadeIn 0.15s ease-out',
        shimmer: 'shimmer 1.5s infinite',
      },
    },
  },
  plugins: [],
}

export default config
