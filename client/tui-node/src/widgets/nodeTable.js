/**
 * Nodes Table Widget - Brutalist Design
 */

const blessed = require('blessed');
const contrib = require('blessed-contrib');
const theme = require('../theme');

function createNodeTable(parent, opts = {}) {
  const {
    top = 0,
    left = 0,
    width = '100%',
    height = 10,
    label = ' ACTIVE NODES '
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
    columnWidth: [18, 12, 14, 8, 10],
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
    headers: ['NODE ID', 'TIER', 'MODEL', 'LOAD', 'STATUS'],
    data: []
  });

  // Update table data
  function setData(nodes) {
    const data = nodes.slice(0, 10).map(node => {
      const nodeId = (node.node_id || 'Unknown').substring(0, 16);
      const tier = formatTier(node.node_tier || 'BASIC');
      const model = (node.model_name || '-').substring(0, 12);
      const load = `${node.current_load || 0}/10`;
      const status = node.is_online !== false ? '▶ ON' : '◼ OFF';

      return [nodeId, tier, model, load, status];
    });

    table.setData({
      headers: ['NODE ID', 'TIER', 'MODEL', 'LOAD', 'STATUS'],
      data
    });
  }

  function formatTier(tier) {
    switch (tier.toUpperCase()) {
      case 'PREMIUM':
        return '▌PREMIUM▐';
      case 'STANDARD':
        return '▌STANDARD▐';
      default:
        return '▌BASIC▐';
    }
  }

  return {
    table,
    setData
  };
}

module.exports = createNodeTable;
