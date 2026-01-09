/**
 * Iris Network TUI - Color Theme
 * Futuristic Brutalist palette inspired by:
 * - Blade Runner (amber/orange)
 * - Neon Genesis Evangelion (warning indicators)
 * - Cyberpunk (neon on dark)
 */

module.exports = {
  // Background colors
  bgPrimary: '#0a0a0a',
  bgSecondary: '#111111',
  bgTertiary: '#1a1a1a',
  bgPanel: '#0f0f0f',

  // Accent colors
  accentAmber: '#ff6a00',
  accentCyan: '#00ffff',
  accentMagenta: '#ff0055',

  // Text colors
  textPrimary: '#ffffff',
  textSecondary: '#888888',
  textMuted: '#444444',

  // Status colors
  success: '#00ff41',
  error: '#ff0000',
  warning: '#ffaa00',

  // Tier colors
  tierPremium: '#ff6a00',
  tierStandard: '#00ffff',
  tierBasic: '#666666',

  // Border characters for brutalist style
  borders: {
    heavy: {
      topLeft: '┏',
      top: '━',
      topRight: '┓',
      left: '┃',
      right: '┃',
      bottomLeft: '┗',
      bottom: '━',
      bottomRight: '┛'
    },
    light: {
      topLeft: '┌',
      top: '─',
      topRight: '┐',
      left: '│',
      right: '│',
      bottomLeft: '└',
      bottom: '─',
      bottomRight: '┘'
    },
    double: {
      topLeft: '╔',
      top: '═',
      topRight: '╗',
      left: '║',
      right: '║',
      bottomLeft: '╚',
      bottom: '═',
      bottomRight: '╝'
    }
  },

  // Status indicators (Evangelion style)
  indicators: {
    online: '▶',
    offline: '◼',
    connecting: '◐',
    warning: '⚠',
    error: '✖',
    success: '✓',
    bullet: '●',
    empty: '○'
  }
};
