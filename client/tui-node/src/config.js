/**
 * Configuration loader for Iris TUI
 * Reads from ~/.iris/config.yaml
 */

const fs = require('fs');
const path = require('path');
const yaml = require('yaml');
const os = require('os');

const IRIS_DIR = path.join(os.homedir(), '.iris');
const CONFIG_PATH = path.join(IRIS_DIR, 'config.yaml');
const TOKEN_PATH = path.join(IRIS_DIR, 'token');

const DEFAULT_CONFIG = {
  coordinator_url: 'http://168.119.10.189:8000',
  node_id: null,
  lmstudio_url: 'http://localhost:1234/v1'
};

/**
 * Convert WebSocket URL to HTTP URL
 * ws://host:port/path -> http://host:port
 * wss://host:port/path -> https://host:port
 */
function toHttpUrl(url) {
  if (!url) return DEFAULT_CONFIG.coordinator_url;

  // If already HTTP, return as-is (but strip path for API base)
  if (url.startsWith('http://') || url.startsWith('https://')) {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}`;
  }

  // Convert ws:// to http://
  if (url.startsWith('ws://')) {
    const parsed = new URL(url);
    return `http://${parsed.host}`;
  }

  // Convert wss:// to https://
  if (url.startsWith('wss://')) {
    const parsed = new URL(url);
    return `https://${parsed.host}`;
  }

  return url;
}

/**
 * Load configuration from YAML file
 */
function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const content = fs.readFileSync(CONFIG_PATH, 'utf8');
      const config = yaml.parse(content) || {};
      return { ...DEFAULT_CONFIG, ...config };
    }
  } catch (err) {
    // Ignore errors, use defaults
  }
  return { ...DEFAULT_CONFIG };
}

/**
 * Save configuration to YAML file
 */
function saveConfig(config) {
  try {
    ensureIrisDir();
    fs.writeFileSync(CONFIG_PATH, yaml.stringify(config));
    return true;
  } catch (err) {
    return false;
  }
}

/**
 * Load saved token
 */
function loadToken() {
  try {
    if (fs.existsSync(TOKEN_PATH)) {
      return fs.readFileSync(TOKEN_PATH, 'utf8').trim();
    }
  } catch (err) {
    // Ignore
  }
  return null;
}

/**
 * Save token to file
 */
function saveToken(token) {
  try {
    ensureIrisDir();
    fs.writeFileSync(TOKEN_PATH, token);
    return true;
  } catch (err) {
    return false;
  }
}

/**
 * Ensure ~/.iris directory exists
 */
function ensureIrisDir() {
  if (!fs.existsSync(IRIS_DIR)) {
    fs.mkdirSync(IRIS_DIR, { recursive: true });
  }
}

/**
 * Get paths
 */
function getPaths() {
  return {
    irisDir: IRIS_DIR,
    configPath: CONFIG_PATH,
    tokenPath: TOKEN_PATH
  };
}

module.exports = {
  loadConfig,
  saveConfig,
  loadToken,
  saveToken,
  ensureIrisDir,
  getPaths,
  toHttpUrl,
  DEFAULT_CONFIG
};
