/**
 * Leaderboard Widget - Brutalist Design
 */

const blessed = require('blessed');
const contrib = require('blessed-contrib');
const theme = require('../theme');

function createLeaderboard(parent, opts = {}) {
  const {
    top = 0,
    left = 0,
    width = '100%',
    height = 10,
    label = ' LEADERBOARD '
  } = opts;

  const table = contrib.table({
    parent,
    top,
    left,
    width,
    height,
    label,
    keys: true,
    fg: theme.accentCyan,
    selectedFg: theme.bgPrimary,
    selectedBg: theme.accentAmber,
    interactive: false,
    columnSpacing: 2,
    columnWidth: [6, 18, 22, 10],
    style: {
      fg: theme.accentCyan,
      bg: theme.bgTertiary,
      header: {
        fg: theme.accentAmber,
        bold: true
      },
      cell: {
        fg: theme.accentCyan
      },
      border: {
        fg: theme.accentCyan
      },
      label: {
        fg: theme.accentAmber
      }
    },
    border: { type: 'line' }
  });

  // Initialize with empty data
  table.setData({
    headers: ['RANK', 'NODE ID', 'REPUTATION', 'TASKS'],
    data: []
  });

  // Update leaderboard data
  function setData(reputation) {
    const data = reputation.slice(0, 10).map((node, index) => {
      const rank = formatRank(index + 1);
      const nodeId = (node.node_id || 'Unknown').substring(0, 16);
      const rep = formatReputation(node.reputation || 0);
      const tasks = String(node.tasks_completed || 0);

      return [rank, nodeId, rep, tasks];
    });

    table.setData({
      headers: ['RANK', 'NODE ID', 'REPUTATION', 'TASKS'],
      data
    });
  }

  function formatRank(rank) {
    if (rank === 1) return '#01';
    if (rank === 2) return '#02';
    if (rank === 3) return '#03';
    return `#${String(rank).padStart(2, '0')}`;
  }

  function formatReputation(rep) {
    const filled = Math.min(10, Math.max(0, Math.floor(rep / 100 * 10)));
    const empty = Math.max(0, 10 - filled);
    const bar = '▓'.repeat(filled) + '░'.repeat(empty);
    return `${bar} ${Math.round(rep)}`;
  }

  return {
    table,
    setData
  };
}

module.exports = createLeaderboard;
