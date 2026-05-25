// I&M-inspired palette — deep forest green + gold, minimalist
export const COLORS = {
  // Primary — I&M forest green
  primary:      '#1A5C38',
  primaryDark:  '#0F3D24',
  primaryLight: '#2E7D4F',
  primaryPale:  '#E8F4ED',
  primaryBg:    '#F5F8F6',

  // Accent gold
  accent:       '#C49A28',
  accentPale:   '#FDF6E3',

  // Neutrals
  white:        '#FFFFFF',
  background:   '#F5F8F6',
  surface:      '#FFFFFF',
  border:       '#D8E5DC',
  divider:      '#EEF3EF',

  // Text
  text:         '#111C16',
  textSecondary:'#4D6358',
  textMuted:    '#8FA89A',

  // Status
  error:        '#C0392B',
  success:      '#1A5C38',
  warning:      '#C49A28',

  // Chat bubbles
  messageSent:        '#1A5C38',
  messageReceived:    '#EEF3EF',
  messageSentText:    '#FFFFFF',
  messageReceivedText:'#111C16',
};

export const FONTS = {
  xs:   11,
  sm:   13,
  md:   15,
  lg:   17,
  xl:   20,
  xxl:  26,
  hero: 34,
};

export const RADIUS = {
  sm:   6,
  md:   10,
  lg:   14,
  full: 999,
};

const AVATAR_COLORS = [
  { bg: '#E8F4ED', text: '#1A5C38' },
  { bg: '#FDF6E3', text: '#8A6910' },
  { bg: '#E8EDF4', text: '#1A3A5C' },
  { bg: '#F4E8E8', text: '#5C1A1A' },
  { bg: '#EDE8F4', text: '#3A1A5C' },
  { bg: '#E8F4F4', text: '#1A505C' },
];

export function avatarColorFor(key: string) {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

export function initialsFor(name: string): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.trim()[0].toUpperCase();
}
