/**
 * Header Widget - Brutalist Style
 */

const blessed = require('blessed');
const theme = require('../theme');

function createHeader(screen) {
  const container = blessed.box({
    parent: screen,
    top: 0,
    left: 0,
    width: '100%',
    height: 3,
    style: {
      bg: theme.bgSecondary
    }
  });

  // Title
  const title = blessed.text({
    parent: container,
    top: 0,
    left: 1,
    content: '{bold}≡ IRIS NETWORK ≡{/bold}',
    tags: true,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgSecondary
    }
  });

  // Subtitle
  const subtitle = blessed.text({
    parent: container,
    top: 0,
    left: 20,
    content: 'DISTRIBUTED INFERENCE',
    style: {
      fg: theme.textSecondary,
      bg: theme.bgSecondary
    }
  });

  // Tab indicators
  const tabs = blessed.text({
    parent: container,
    top: 0,
    right: 2,
    content: '{#ff6a00-fg}[1]{/}NET  {#888888-fg}[2]{/}SYS  {#888888-fg}[3]{/}COM',
    tags: true,
    style: {
      bg: theme.bgSecondary
    }
  });

  // Status indicator
  const status = blessed.text({
    parent: container,
    top: 1,
    right: 2,
    content: '{#00ff41-fg}● ONLINE{/}',
    tags: true,
    style: {
      bg: theme.bgSecondary
    }
  });

  // Bottom border
  const border = blessed.line({
    parent: container,
    top: 2,
    left: 0,
    width: '100%',
    orientation: 'horizontal',
    style: {
      fg: theme.accentAmber
    }
  });

  // Update tab highlight
  function updateTab(name) {
    let content = '';
    switch (name) {
      case 'network':
        content = '{#ff6a00-fg}[1]NET{/}  {#888888-fg}[2]SYS  [3]COM{/}';
        break;
      case 'system':
        content = '{#888888-fg}[1]NET{/}  {#ff6a00-fg}[2]SYS{/}  {#888888-fg}[3]COM{/}';
        break;
      case 'comms':
        content = '{#888888-fg}[1]NET  [2]SYS{/}  {#ff6a00-fg}[3]COM{/}';
        break;
    }
    tabs.setContent(content);
  }

  function setStatus(online) {
    if (online) {
      status.setContent('{#00ff41-fg}● ONLINE{/}');
    } else {
      status.setContent('{#ff0000-fg}◼ OFFLINE{/}');
    }
  }

  return {
    container,
    updateTab,
    setStatus
  };
}

module.exports = createHeader;
