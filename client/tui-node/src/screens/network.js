/**
 * Network Screen - Dashboard Overview
 * Brutalist Design with stats, nodes table, and leaderboard
 */

const blessed = require('blessed');
const theme = require('../theme');
const createStatsCard = require('../widgets/statsCard');
const createNodeTable = require('../widgets/nodeTable');
const createLeaderboard = require('../widgets/leaderboard');

function createNetworkScreen(screen, app) {
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

  // Section title
  const title = blessed.text({
    parent: container,
    top: 0,
    left: 1,
    content: '{bold}▌NETWORK OVERVIEW▐{/bold}',
    tags: true,
    style: {
      fg: theme.accentAmber,
      bg: theme.bgPrimary
    }
  });

  // Stats cards row
  const statsRow = blessed.box({
    parent: container,
    top: 2,
    left: 1,
    width: '100%-2',
    height: 7,
    style: {
      bg: theme.bgPrimary
    }
  });

  // Create stats cards
  const nodesCard = createStatsCard(statsRow, {
    top: 0,
    left: 0,
    width: '25%-1',
    label: 'ONLINE',
    value: '0',
    icon: '◉',
    color: theme.accentAmber
  });

  const todayCard = createStatsCard(statsRow, {
    top: 0,
    left: '25%',
    width: '25%-1',
    label: 'TODAY',
    value: '0',
    icon: '▤',
    color: theme.accentCyan
  });

  const totalCard = createStatsCard(statsRow, {
    top: 0,
    left: '50%',
    width: '25%-1',
    label: 'TOTAL',
    value: '0',
    icon: 'Σ',
    color: theme.accentAmber
  });

  const usersCard = createStatsCard(statsRow, {
    top: 0,
    left: '75%',
    width: '25%-1',
    label: 'USERS',
    value: '0',
    icon: '◎',
    color: theme.accentCyan
  });

  // Nodes table
  const nodesTable = createNodeTable(container, {
    top: 10,
    left: 1,
    width: '100%-2',
    height: 12,
    label: ' ACTIVE NODES '
  });

  // Leaderboard
  const leaderboard = createLeaderboard(container, {
    top: 23,
    left: 1,
    width: '100%-2',
    height: 12,
    label: ' LEADERBOARD '
  });

  // Update function
  function update(stats, nodes, reputation) {
    // Update stats cards
    if (stats) {
      nodesCard.setValue(String(stats.nodes_online || 0));
      todayCard.setValue(String(stats.tasks_today || 0));
      totalCard.setValue(formatNumber(stats.total_tasks || 0));
      usersCard.setValue(String(stats.total_users || 0));
    }

    // Update nodes table
    if (nodes && Array.isArray(nodes)) {
      nodesTable.setData(nodes);
    }

    // Update leaderboard
    if (reputation && Array.isArray(reputation)) {
      leaderboard.setData(reputation);
    }
  }

  function formatNumber(num) {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return String(num);
  }

  return {
    container,
    update
  };
}

module.exports = createNetworkScreen;
