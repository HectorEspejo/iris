/**
 * System Screen - Local Node Status
 * Brutalist Design with node info, performance metrics, and activity log
 */

const blessed = require('blessed');
const theme = require('../theme');
const createStatsCard = require('../widgets/statsCard');

function createSystemScreen(screen, app) {
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
    content: '{bold}▌SYSTEM STATUS▐{/bold}',
    tags: true,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgPrimary
    }
  });

  const statusIndicator = blessed.text({
    parent: titleRow,
    top: 0,
    right: 2,
    content: '{#00ff41-fg}▶ CONNECTED{/}',
    tags: true,
    style: {
      bg: theme.bgPrimary
    }
  });

  // Node info panel
  const infoPanel = blessed.box({
    parent: container,
    top: 2,
    left: 1,
    width: '100%-2',
    height: 8,
    label: ' NODE INFO ',
    style: {
      fg: theme.textPrimary,
      bg: theme.bgTertiary,
      border: { fg: theme.accentCyan },
      label: { fg: theme.accentAmber }
    },
    border: { type: 'line' }
  });

  // Info fields
  const nodeIdLabel = blessed.text({
    parent: infoPanel,
    top: 1,
    left: 2,
    content: 'NODE ID:',
    style: { fg: theme.accentAmber, bg: theme.bgTertiary }
  });

  const nodeIdValue = blessed.text({
    parent: infoPanel,
    top: 1,
    left: 14,
    content: 'Not configured',
    style: { fg: theme.textPrimary, bg: theme.bgTertiary }
  });

  const modelLabel = blessed.text({
    parent: infoPanel,
    top: 2,
    left: 2,
    content: 'MODEL:',
    style: { fg: theme.accentAmber, bg: theme.bgTertiary }
  });

  const modelValue = blessed.text({
    parent: infoPanel,
    top: 2,
    left: 14,
    content: '-',
    style: { fg: theme.textPrimary, bg: theme.bgTertiary }
  });

  const endpointLabel = blessed.text({
    parent: infoPanel,
    top: 3,
    left: 2,
    content: 'ENDPOINT:',
    style: { fg: theme.accentAmber, bg: theme.bgTertiary }
  });

  const endpointValue = blessed.text({
    parent: infoPanel,
    top: 3,
    left: 14,
    content: '-',
    style: { fg: theme.textPrimary, bg: theme.bgTertiary }
  });

  // Separator
  blessed.text({
    parent: infoPanel,
    top: 5,
    left: 2,
    content: '━'.repeat(50),
    style: { fg: theme.textMuted, bg: theme.bgTertiary }
  });

  // Performance section title
  blessed.text({
    parent: container,
    top: 11,
    left: 1,
    content: '{bold}▌PERFORMANCE▐{/bold}',
    tags: true,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgPrimary
    }
  });

  // Stats cards row
  const statsRow = blessed.box({
    parent: container,
    top: 13,
    left: 1,
    width: '100%-2',
    height: 7,
    style: {
      bg: theme.bgPrimary
    }
  });

  const loadCard = createStatsCard(statsRow, {
    top: 0,
    left: 0,
    width: '25%-1',
    label: 'LOAD',
    value: '0/10',
    icon: '◈',
    color: theme.accentAmber
  });

  const vramCard = createStatsCard(statsRow, {
    top: 0,
    left: '25%',
    width: '25%-1',
    label: 'VRAM',
    value: '- GB',
    icon: '▣',
    color: theme.accentCyan
  });

  const speedCard = createStatsCard(statsRow, {
    top: 0,
    left: '50%',
    width: '25%-1',
    label: 'SPEED',
    value: '- t/s',
    icon: '▸',
    color: theme.accentAmber
  });

  const tasksCard = createStatsCard(statsRow, {
    top: 0,
    left: '75%',
    width: '25%-1',
    label: 'TASKS',
    value: '0',
    icon: '◆',
    color: theme.accentCyan
  });

  // Reputation section
  blessed.text({
    parent: container,
    top: 21,
    left: 1,
    content: '{bold}▌REPUTATION▐{/bold}',
    tags: true,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgPrimary
    }
  });

  const repPanel = blessed.box({
    parent: container,
    top: 23,
    left: 1,
    width: '100%-2',
    height: 3,
    style: {
      fg: theme.textPrimary,
      bg: theme.bgTertiary,
      border: { fg: theme.accentAmber }
    },
    border: { type: 'line' }
  });

  const repText = blessed.text({
    parent: repPanel,
    top: 0,
    left: 2,
    content: '[░░░░░░░░░░░░] -/100                    RANK: -',
    style: { fg: theme.accentAmber, bg: theme.bgTertiary }
  });

  // Activity log
  blessed.text({
    parent: container,
    top: 27,
    left: 1,
    content: '{bold}▌ACTIVITY LOG▐{/bold}',
    tags: true,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgPrimary
    }
  });

  const activityLog = blessed.log({
    parent: container,
    top: 29,
    left: 1,
    width: '100%-2',
    height: 8,
    label: '',
    scrollable: true,
    alwaysScroll: true,
    scrollbar: {
      ch: '│',
      style: { fg: theme.accentAmber }
    },
    style: {
      fg: theme.textSecondary,
      bg: theme.bgTertiary,
      border: { fg: theme.accentCyan }
    },
    border: { type: 'line' },
    tags: true
  });

  activityLog.log('{#444444-fg}▶ Waiting for node data...{/}');

  // Update function - shows current node info
  function update(config, reputation, nodes) {
    if (!config) return;

    // Always show config data
    const nodeId = config.node_id || 'Not configured';
    const endpoint = config.coordinator_url || '-';
    const lmstudio = config.lmstudio_url || 'http://localhost:1234/v1';

    nodeIdValue.setContent(nodeId);
    endpointValue.setContent(endpoint.substring(0, 50));

    // Check if node is connected (in nodes list)
    let nodeData = null;
    let isOnline = false;

    if (nodes && Array.isArray(nodes) && nodeId !== 'Not configured') {
      nodeData = nodes.find(n => n.node_id === nodeId);
      isOnline = !!nodeData;
    }

    // Update connection status
    if (isOnline) {
      statusIndicator.setContent('{#00ff41-fg}▶ ONLINE{/}');

      // Show data from connected node
      if (nodeData.model_name) modelValue.setContent(nodeData.model_name);
      if (nodeData.vram_gb) vramCard.setValue(`${nodeData.vram_gb.toFixed(1)} GB`);
      if (nodeData.current_load !== undefined) loadCard.setValue(`${nodeData.current_load}/10`);
    } else {
      statusIndicator.setContent('{#ff0000-fg}◼ OFFLINE{/}');
      modelValue.setContent('(not connected)');
    }

    // Get reputation data for this node
    if (reputation && Array.isArray(reputation) && nodeId !== 'Not configured') {
      const nodeRep = reputation.find(n => n.node_id === nodeId);

      if (nodeRep) {
        const rank = reputation.findIndex(n => n.node_id === nodeId) + 1;
        const repValue = Math.round(nodeRep.reputation || 0);
        const tasks = nodeRep.tasks_completed || 0;

        // Update tasks
        tasksCard.setValue(String(tasks));

        // Update reputation bar (clamp values to valid range)
        const filled = Math.min(12, Math.max(0, Math.floor(repValue / 100 * 12)));
        const empty = Math.max(0, 12 - filled);
        const bar = '▓'.repeat(filled) + '░'.repeat(empty);
        repText.setContent(`[${bar}] ${repValue}/100                    RANK: #${String(rank).padStart(2, '0')}`);

        // If has model in reputation but not connected, show it
        if (!isOnline && nodeRep.model_name) {
          modelValue.setContent(nodeRep.model_name + ' (cached)');
        }
      }
    }

    // Log activity on first update
    if (!update._logged) {
      update._logged = true;
      log(`Node ${nodeId.substring(0, 20)}... initialized`, 'info');
    }
  }

  function log(message, level = 'info') {
    const colors = {
      info: '#00ffff',
      success: '#00ff41',
      warning: '#ffaa00',
      error: '#ff0000'
    };
    const color = colors[level] || '#888888';
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    activityLog.log(`{${color}-fg}${time}  ▶ ${message}{/}`);
  }

  return {
    container,
    update,
    log
  };
}

module.exports = createSystemScreen;
