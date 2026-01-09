/**
 * Communications Screen - Chat Interface
 * Brutalist Design with messages, input, and controls
 */

const blessed = require('blessed');
const theme = require('../theme');
const createChatBox = require('../widgets/chatBox');

function createCommsScreen(screen, app) {
  // Main container
  const container = blessed.box({
    parent: screen,
    top: 3,
    left: 0,
    width: '100%',
    height: '100%-4',
    style: {
      bg: theme.bgPrimary
    }
  });

  // Section title with status
  const titleRow = blessed.box({
    parent: container,
    top: 0,
    left: 0,
    width: '100%',
    height: 1,
    style: {
      bg: theme.bgPrimary
    }
  });

  blessed.text({
    parent: titleRow,
    top: 0,
    left: 1,
    content: '{bold}▌COMMUNICATIONS▐{/bold}',
    tags: true,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgPrimary
    }
  });

  const statusText = blessed.text({
    parent: titleRow,
    top: 0,
    right: 2,
    content: '{#00ffff-fg}● READY{/}',
    tags: true,
    style: {
      bg: theme.bgPrimary
    }
  });

  // Chat box
  const chatBox = createChatBox(container, {
    top: 2,
    left: 1,
    width: '100%-2',
    height: '60%',
    label: ' MESSAGES '
  });

  // Controls row
  const controlsRow = blessed.box({
    parent: container,
    top: '65%',
    left: 1,
    width: '100%-2',
    height: 3,
    style: {
      bg: theme.bgPrimary
    }
  });

  // Mode selector
  blessed.text({
    parent: controlsRow,
    top: 1,
    left: 0,
    content: '{#ff6a00-fg}MODE:{/}',
    tags: true,
    style: { bg: theme.bgPrimary }
  });

  const modes = ['SUBTASKS', 'CONSENSUS', 'CONTEXT'];
  let currentMode = 0;

  const modeButton = blessed.button({
    parent: controlsRow,
    top: 0,
    left: 7,
    width: 14,
    height: 3,
    content: `{center}${modes[currentMode]}{/center}`,
    tags: true,
    style: {
      fg: theme.accentCyan,
      bg: theme.bgTertiary,
      border: { fg: theme.accentCyan },
      focus: {
        fg: theme.bgPrimary,
        bg: theme.accentAmber,
        border: { fg: theme.accentAmber }
      }
    },
    border: { type: 'line' }
  });

  modeButton.on('press', () => {
    currentMode = (currentMode + 1) % modes.length;
    modeButton.setContent(`{center}${modes[currentMode]}{/center}`);
    screen.render();
  });

  // Difficulty selector
  blessed.text({
    parent: controlsRow,
    top: 1,
    left: 24,
    content: '{#00ffff-fg}DIFF:{/}',
    tags: true,
    style: { bg: theme.bgPrimary }
  });

  const diffs = ['SIMPLE', 'COMPLEX', 'ADVANCED'];
  let currentDiff = 0;

  const diffButton = blessed.button({
    parent: controlsRow,
    top: 0,
    left: 31,
    width: 12,
    height: 3,
    content: `{center}${diffs[currentDiff]}{/center}`,
    tags: true,
    style: {
      fg: theme.accentCyan,
      bg: theme.bgTertiary,
      border: { fg: theme.accentCyan },
      focus: {
        fg: theme.bgPrimary,
        bg: theme.accentAmber,
        border: { fg: theme.accentAmber }
      }
    },
    border: { type: 'line' }
  });

  diffButton.on('press', () => {
    currentDiff = (currentDiff + 1) % diffs.length;
    diffButton.setContent(`{center}${diffs[currentDiff]}{/center}`);
    screen.render();
  });

  // Input area
  const inputLabel = blessed.text({
    parent: container,
    top: '72%',
    left: 1,
    content: '{#ff6a00-fg}>{/}',
    tags: true,
    style: { bg: theme.bgPrimary }
  });

  const inputBox = blessed.textarea({
    parent: container,
    top: '72%',
    left: 3,
    width: '100%-5',
    height: 5,
    label: '',
    inputOnFocus: true,
    style: {
      fg: theme.textPrimary,
      bg: theme.bgTertiary,
      border: { fg: theme.accentAmber },
      focus: {
        border: { fg: theme.accentCyan }
      }
    },
    border: { type: 'line' }
  });

  // Submit button
  const submitButton = blessed.button({
    parent: container,
    top: '85%',
    left: 1,
    width: 16,
    height: 3,
    content: '{center}▶ TRANSMIT{/center}',
    tags: true,
    style: {
      fg: theme.bgPrimary,
      bg: theme.accentAmber,
      border: { fg: theme.accentAmber },
      focus: {
        bg: theme.warning
      }
    },
    border: { type: 'line' }
  });

  // Help text
  blessed.text({
    parent: container,
    top: '86%',
    left: 20,
    content: '{#444444-fg}[Enter] Send   [Tab] Navigate   [Esc] Clear{/}',
    tags: true,
    style: { bg: theme.bgPrimary }
  });

  // Sending state
  let isSending = false;

  // Send message handler
  async function sendMessage() {
    const prompt = inputBox.getValue().trim();

    if (!prompt) {
      setStatus('ENTER PROMPT', 'warning');
      return;
    }

    if (!app.token) {
      setStatus('NOT AUTHENTICATED', 'error');
      chatBox.addSystemMessage('Authentication required. Restart TUI.');
      return;
    }

    if (isSending) return;
    isSending = true;

    // Clear input
    inputBox.clearValue();

    // Add user message
    chatBox.addMessage('USER', prompt, true);

    // Update status
    setStatus('TRANSMITTING...', 'warning');
    screen.render();

    try {
      const mode = modes[currentMode].toLowerCase();
      const difficulty = diffs[currentDiff].toLowerCase();

      const result = await app.api.sendInference(prompt, mode, difficulty);

      if (!result.success) {
        setStatus('ERROR', 'error');
        chatBox.addSystemMessage(`Error: ${result.error}`);
        isSending = false;
        screen.render();
        return;
      }

      const taskId = result.data.task_id;
      setStatus(`PROCESSING ${taskId.substring(0, 8)}`, 'info');
      screen.render();

      // Poll for result
      const pollResult = await app.api.pollTaskResult(
        taskId,
        30,
        2000,
        (status, attempt, max) => {
          const dots = '.'.repeat((attempt % 3) + 1);
          setStatus(`PROCESSING${dots}`, 'info');
          screen.render();
        }
      );

      if (pollResult.success) {
        chatBox.addMessage('IRIS', pollResult.response, false);
        setStatus('COMPLETE', 'success');
      } else {
        chatBox.addSystemMessage(`Error: ${pollResult.error}`);
        setStatus('FAILED', 'error');
      }

    } catch (err) {
      setStatus('ERROR', 'error');
      chatBox.addSystemMessage(`Error: ${err.message}`);
    }

    isSending = false;
    screen.render();
  }

  // Update status
  function setStatus(text, level = 'info') {
    const colors = {
      info: '#00ffff',
      success: '#00ff41',
      warning: '#ffaa00',
      error: '#ff0000'
    };
    const icons = {
      info: '◐',
      success: '▶',
      warning: '◐',
      error: '◼'
    };
    const color = colors[level] || colors.info;
    const icon = icons[level] || '●';
    statusText.setContent(`{${color}-fg}${icon} ${text}{/}`);
  }

  // Event handlers
  submitButton.on('press', () => {
    sendMessage();
  });

  inputBox.key('enter', () => {
    sendMessage();
  });

  inputBox.key('escape', () => {
    inputBox.clearValue();
    screen.render();
  });

  // Focus input on show
  container.on('show', () => {
    inputBox.focus();
  });

  return {
    container,
    setStatus
  };
}

module.exports = createCommsScreen;
