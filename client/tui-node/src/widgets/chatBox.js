/**
 * Chat Box Widget - Brutalist Design
 */

const blessed = require('blessed');
const theme = require('../theme');

function createChatBox(parent, opts = {}) {
  const {
    top = 0,
    left = 0,
    width = '100%',
    height = '60%',
    label = ' MESSAGES '
  } = opts;

  // Container
  const container = blessed.box({
    parent,
    top,
    left,
    width,
    height,
    label,
    tags: true,  // Enable tag parsing for colors
    scrollable: true,
    alwaysScroll: true,
    scrollbar: {
      ch: '│',
      track: {
        bg: theme.bgTertiary
      },
      style: {
        fg: theme.accentAmber
      }
    },
    style: {
      fg: theme.textPrimary,
      bg: theme.bgTertiary,
      border: { fg: theme.accentCyan },
      label: { fg: theme.accentAmber }
    },
    border: { type: 'line' },
    keys: true,
    vi: true,
    mouse: true
  });

  const messages = [];

  // Add a message
  function addMessage(sender, content, isUser = false) {
    const color = isUser ? theme.accentAmber : theme.accentCyan;
    const header = isUser ? '▌USER▐' : '▌IRIS▐';

    messages.push({ sender, content, isUser });

    // Rebuild content
    let displayContent = '';
    messages.forEach((msg, i) => {
      const msgColor = msg.isUser ? '#ff6a00' : '#00ffff';
      const msgHeader = msg.isUser ? '▌USER▐' : '▌IRIS▐';
      displayContent += `{${msgColor}-fg}{bold}${msgHeader}{/}\n`;
      displayContent += `{#ffffff-fg}${msg.content}{/}\n\n`;
    });

    container.setContent(displayContent);
    container.setScrollPerc(100);
  }

  // Add system message
  function addSystemMessage(content) {
    messages.push({ sender: 'SYSTEM', content, isUser: false });

    let displayContent = '';
    messages.forEach((msg) => {
      if (msg.sender === 'SYSTEM') {
        displayContent += `{#ffaa00-fg}▌SYSTEM▐ {#888888-fg}${msg.content}{/}\n\n`;
      } else {
        const msgColor = msg.isUser ? '#ff6a00' : '#00ffff';
        const msgHeader = msg.isUser ? '▌USER▐' : '▌IRIS▐';
        displayContent += `{${msgColor}-fg}{bold}${msgHeader}{/}\n`;
        displayContent += `{#ffffff-fg}${msg.content}{/}\n\n`;
      }
    });

    container.setContent(displayContent);
    container.setScrollPerc(100);
  }

  // Clear messages
  function clear() {
    messages.length = 0;
    container.setContent('');
  }

  // Set initial content
  container.setContent(
    '{#444444-fg}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{/}\n\n' +
    '{#ff6a00-fg}{bold}▌IRIS NETWORK COMMUNICATIONS TERMINAL▐{/}\n\n' +
    '{#888888-fg}Send a message to initiate distributed inference.\n' +
    'Your prompts will be processed across the network.{/}\n\n' +
    '{#444444-fg}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{/}'
  );

  return {
    container,
    addMessage,
    addSystemMessage,
    clear
  };
}

module.exports = createChatBox;
