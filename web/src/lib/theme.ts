// Design tokens — mirrors mobile constants/theme.ts
export const COLORS = {
  primary:      '#1A5C38',
  primaryDark:  '#0F3D24',
  primaryLight: '#2E7D4F',
  primaryPale:  '#E8F4ED',
  primaryBg:    '#F5F8F6',
  accent:       '#C49A28',
  accentPale:   '#FDF6E3',
  white:        '#FFFFFF',
  surface:      '#FFFFFF',
  border:       '#D8E5DC',
  divider:      '#EEF3EF',
  text:         '#111C16',
  textSecondary:'#4D6358',
  textMuted:    '#8FA89A',
  error:        '#C0392B',
  success:      '#1A5C38',
  warning:      '#C49A28',
  messageSent:        '#1A5C38',
  messageReceived:    '#EEF3EF',
  messageSentText:    '#FFFFFF',
  messageReceivedText:'#111C16',
} as const

// Deterministic avatar colors — same algorithm as mobile
const AVATAR_PALETTE = [
  '#1A5C38', '#C49A28', '#2E86AB', '#A23B72', '#F18F01', '#4D6358',
]

export function avatarColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return AVATAR_PALETTE[Math.abs(hash) % AVATAR_PALETTE.length]
}

export function initials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
}
