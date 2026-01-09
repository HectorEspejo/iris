/**
 * Footer Widget - Brutalist Style
 */

const blessed = require('blessed');
const theme = require('../theme');

function createFooter(screen) {
  const container = blessed.box({
    parent: screen,
    bottom: 0,
    left: 0,
    width: '100%',
    height: 1,
    style: {
      bg: theme.bgSecondary
    }
  });

  // Commands
  const commands = blessed.text({
    parent: container,
    top: 0,
    left: 1,
    content: '{#ff6a00-fg}[1-3]{/} Tab  {#ff6a00-fg}[R]{/} Sync  {#ff6a00-fg}[?]{/} Help  {#ff6a00-fg}[Q]{/} Exit',
    tags: true,
    style: {
      bg: theme.bgSecondary
    }
  });

  // Version
  const version = blessed.text({
    parent: container,
    top: 0,
    right: 1,
    content: 'v1.0.0',
    style: {
      fg: theme.textMuted,
      bg: theme.bgSecondary
    }
  });

  return {
    container
  };
}

module.exports = createFooter;
