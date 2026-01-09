/**
 * Iris Network TUI - Main Application
 * Futuristic Brutalist Dashboard
 */

const blessed = require('blessed');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const theme = require('./theme');
const { loadConfig, toHttpUrl, getPaths } = require('./config');
const { ensureAuthenticated } = require('./auth');
const IrisAPI = require('./api');

// Screens
const createNetworkScreen = require('./screens/network');
const createSystemScreen = require('./screens/system');
const createCommsScreen = require('./screens/comms');

// Widgets
const createHeader = require('./widgets/header');
const createFooter = require('./widgets/footer');

class IrisApp {
  constructor() {
    this.screen = null;
    this.api = null;
    this.token = null;
    this.config = loadConfig();
    this.coordinatorUrl = toHttpUrl(this.config.coordinator_url);
    this.currentTab = 'network';
    this.screens = {};
    this.refreshInterval = null;
    this.nodeProcess = null;

    // Data
    this.stats = {};
    this.nodes = [];
    this.reputation = [];
  }

  /**
   * Initialize and run the application
   */
  async run() {
    // Create blessed screen
    this.screen = blessed.screen({
      smartCSR: true,
      title: 'IRIS NETWORK',
      cursor: {
        artificial: true,
        shape: 'line',
        blink: true,
        color: theme.accentAmber
      }
    });

    // Show loading screen
    this._showLoading('AUTHENTICATING...');

    // Authenticate
    const authResult = await ensureAuthenticated(this.coordinatorUrl);

    if (!authResult.success) {
      this._showError(`Authentication failed: ${authResult.message}`);
      await this._sleep(3000);
      process.exit(1);
    }

    this.token = authResult.token;
    this.api = new IrisAPI(this.coordinatorUrl, this.token);

    // Start the node agent
    this._showLoading('STARTING NODE...');
    await this._startNodeAgent();

    // Clear loading and build UI
    this._clearScreen();
    this._buildUI();
    this._setupKeyBindings();

    // Initial data fetch
    await this._refreshData();

    // Start auto-refresh
    this.refreshInterval = setInterval(() => this._refreshData(), 5000);

    // Handle process exit to cleanup node
    process.on('exit', () => this._cleanup());
    process.on('SIGINT', () => { this._cleanup(); process.exit(0); });
    process.on('SIGTERM', () => { this._cleanup(); process.exit(0); });

    // Render
    this.screen.render();
  }

  /**
   * Cleanup on exit
   */
  _cleanup() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
    if (this.nodeProcess) {
      this.nodeProcess.kill();
    }
  }

  /**
   * Build the main UI
   */
  _buildUI() {
    // Create header
    this.header = createHeader(this.screen);

    // Create footer
    this.footer = createFooter(this.screen);

    // Create screen containers
    this.screens.network = createNetworkScreen(this.screen, this);
    this.screens.system = createSystemScreen(this.screen, this);
    this.screens.comms = createCommsScreen(this.screen, this);

    // Show initial screen
    this._showScreen('network');
  }

  /**
   * Setup keyboard bindings
   */
  _setupKeyBindings() {
    // Tab navigation
    this.screen.key(['1'], () => this._showScreen('network'));
    this.screen.key(['2'], () => this._showScreen('system'));
    this.screen.key(['3'], () => this._showScreen('comms'));

    // Refresh
    this.screen.key(['r'], () => this._refreshData());

    // Quit
    this.screen.key(['q', 'C-c'], () => {
      this._cleanup();
      process.exit(0);
    });

    // Help
    this.screen.key(['?', 'h'], () => this._showHelp());
  }

  /**
   * Show a specific screen
   */
  _showScreen(name) {
    // Hide all screens
    Object.values(this.screens).forEach(screen => {
      if (screen.container) {
        screen.container.hide();
      }
    });

    // Show selected screen
    if (this.screens[name] && this.screens[name].container) {
      this.screens[name].container.show();
      this.currentTab = name;

      // Update header tab indicator
      if (this.header && this.header.updateTab) {
        this.header.updateTab(name);
      }
    }

    this.screen.render();
  }

  /**
   * Refresh data from API
   */
  async _refreshData() {
    try {
      // Fetch all data in parallel
      const [statsResult, nodesResult, repResult] = await Promise.all([
        this.api.getStats(),
        this.api.getNodes(),
        this.api.getReputation()
      ]);

      if (statsResult.success) this.stats = statsResult.data;
      if (nodesResult.success) this.nodes = nodesResult.data;
      if (repResult.success) this.reputation = repResult.data;
    } catch (err) {
      // API error, but continue to update screens with available data
    }

    // Always update screens (even if API failed, show config data)
    this._updateScreens();
  }

  /**
   * Update all screens with new data
   */
  _updateScreens() {
    if (this.screens.network && this.screens.network.update) {
      this.screens.network.update(this.stats, this.nodes, this.reputation);
    }
    if (this.screens.system && this.screens.system.update) {
      this.screens.system.update(this.config, this.reputation, this.nodes);
    }

    this.screen.render();
  }

  /**
   * Show loading message
   */
  _showLoading(message) {
    if (this._loadingBox) {
      this._loadingBox.setContent(`{center}${message}{/center}`);
    } else {
      this._loadingBox = blessed.box({
        parent: this.screen,
        top: 'center',
        left: 'center',
        width: 40,
        height: 5,
        content: `{center}${message}{/center}`,
        tags: true,
        style: {
          fg: theme.accentAmber,
          bg: theme.bgSecondary,
          border: { fg: theme.accentAmber }
        },
        border: { type: 'line' }
      });
    }
    this.screen.render();
  }

  /**
   * Show error message
   */
  _showError(message) {
    if (this._loadingBox) {
      this._loadingBox.style.fg = theme.error;
      this._loadingBox.style.border.fg = theme.error;
      this._loadingBox.setContent(`{center}${message}{/center}`);
    }
    this.screen.render();
  }

  /**
   * Clear screen of loading/error boxes
   */
  _clearScreen() {
    if (this._loadingBox) {
      this._loadingBox.destroy();
      this._loadingBox = null;
    }
  }

  /**
   * Show help dialog
   */
  _showHelp() {
    const helpBox = blessed.box({
      parent: this.screen,
      top: 'center',
      left: 'center',
      width: 50,
      height: 15,
      content:
        '{bold}{#ff6a00-fg}IRIS NETWORK - COMMANDS{/}\n\n' +
        '{#00ffff-fg}[1]{/} Network Overview\n' +
        '{#00ffff-fg}[2]{/} System Status\n' +
        '{#00ffff-fg}[3]{/} Communications\n\n' +
        '{#00ffff-fg}[R]{/} Refresh Data\n' +
        '{#00ffff-fg}[Q]{/} Quit\n\n' +
        '{#444444-fg}Press any key to close{/}',
      tags: true,
      style: {
        fg: theme.textPrimary,
        bg: theme.bgSecondary,
        border: { fg: theme.accentAmber }
      },
      border: { type: 'line' }
    });

    helpBox.key(['escape', 'enter', 'space', 'q'], () => {
      helpBox.destroy();
      this.screen.render();
    });

    helpBox.focus();
    this.screen.render();
  }

  /**
   * Start the node agent in the background
   */
  async _startNodeAgent() {
    const { irisDir } = getPaths();
    const nodeAgentPath = path.join(irisDir, 'bin', 'iris-node');
    const configPath = path.join(irisDir, 'config.yaml');
    const logPath = path.join(irisDir, 'logs', 'node.log');

    // Check if iris-node exists
    if (!fs.existsSync(nodeAgentPath)) {
      // Try alternative paths
      const altPaths = [
        '/usr/local/bin/iris-node',
        path.join(process.env.HOME, '.iris', 'bin', 'iris-node')
      ];

      let found = false;
      for (const p of altPaths) {
        if (fs.existsSync(p)) {
          this._spawnNode(p, configPath, logPath);
          found = true;
          break;
        }
      }

      if (!found) {
        // Node agent not found, but continue anyway (might be running as service)
        return;
      }
    } else {
      this._spawnNode(nodeAgentPath, configPath, logPath);
    }

    // Wait a moment for the node to start
    await this._sleep(1000);
  }

  /**
   * Spawn the node process
   */
  _spawnNode(nodePath, configPath, logPath) {
    try {
      // Ensure log directory exists
      const logDir = path.dirname(logPath);
      if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
      }

      // Open log file for writing
      const logStream = fs.openSync(logPath, 'a');

      // Spawn node agent in background
      this.nodeProcess = spawn(nodePath, ['--config', configPath], {
        detached: false,
        stdio: ['ignore', logStream, logStream],
        env: { ...process.env }
      });

      this.nodeProcess.on('error', (err) => {
        // Silently handle errors - node might already be running
      });

      this.nodeProcess.on('exit', (code) => {
        this.nodeProcess = null;
      });

    } catch (err) {
      // Silently fail - node might be running as a service
    }
  }

  /**
   * Sleep helper
   */
  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

module.exports = IrisApp;
