/**
 * Stats Card Widget - Brutalist Design
 */

const blessed = require('blessed');
const theme = require('../theme');

function createStatsCard(parent, opts) {
  const {
    top = 0,
    left = 0,
    width = 15,
    height = 7,
    label = 'LABEL',
    value = '0',
    icon = '●',
    color = theme.accentCyan
  } = opts;

  const card = blessed.box({
    parent,
    top,
    left,
    width,
    height,
    style: {
      fg: color,
      bg: theme.bgTertiary,
      border: { fg: color }
    },
    border: { type: 'line' }
  });

  // Icon
  const iconWidget = blessed.text({
    parent: card,
    top: 0,
    left: 'center',
    content: icon,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgTertiary
    }
  });

  // Value
  const valueWidget = blessed.text({
    parent: card,
    top: 2,
    left: 'center',
    content: `{bold}${value}{/bold}`,
    tags: true,
    style: {
      fg: theme.textPrimary,
      bg: theme.bgTertiary
    }
  });

  // Label
  const labelWidget = blessed.text({
    parent: card,
    top: 4,
    left: 'center',
    content: label,
    style: {
      fg: theme.textMuted,
      bg: theme.bgTertiary
    }
  });

  // Update value
  function setValue(newValue) {
    valueWidget.setContent(`{bold}${newValue}{/bold}`);
  }

  return {
    card,
    setValue
  };
}

module.exports = createStatsCard;
