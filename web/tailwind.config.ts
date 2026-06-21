import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Primary — forest green (matches mobile theme.ts)
        primary: {
          DEFAULT: '#1A5C38',
          dark:    '#0F3D24',
          light:   '#2E7D4F',
          pale:    '#E8F4ED',
          bg:      '#F5F8F6',
        },
        // Accent gold
        accent: {
          DEFAULT: '#C49A28',
          pale:    '#FDF6E3',
        },
        // Surfaces
        surface: '#FFFFFF',
        border:  '#D8E5DC',
        divider: '#EEF3EF',
        // Text
        text: {
          DEFAULT:   '#111C16',
          secondary: '#4D6358',
          muted:     '#8FA89A',
        },
        // Status
        success: '#1A5C38',
        warning: '#C49A28',
        error:   '#C0392B',
        // Chat bubbles
        bubble: {
          sent:         '#1A5C38',
          received:     '#EEF3EF',
          'sent-text':  '#FFFFFF',
          'recv-text':  '#111C16',
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
        card: '0 4px 12px rgba(0,0,0,0.06)',
        fab:  '0 4px 8px rgba(0,0,0,0.22)',
        modal:'0 8px 32px rgba(0,0,0,0.12)',
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
