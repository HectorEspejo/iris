/**
 * Authentication Module for Iris TUI
 * Uses token saved by installer
 */

const axios = require('axios');
const { loadToken, saveToken } = require('./config');

/**
 * Ensure user is authenticated
 * @param {string} coordinatorUrl - Coordinator URL
 * @returns {Promise<{success: boolean, token: string|null, message: string}>}
 */
async function ensureAuthenticated(coordinatorUrl) {
  // Try existing token from ~/.iris/token
  const existingToken = loadToken();

  if (!existingToken) {
    return {
      success: false,
      token: null,
      message: 'No token found. Run the installer first: curl -fsSL https://iris.network/install.sh | bash'
    };
  }

  // Validate the token
  const isValid = await validateToken(existingToken, coordinatorUrl);

  if (isValid) {
    return { success: true, token: existingToken, message: 'Token validated' };
  }

  return {
    success: false,
    token: null,
    message: 'Token expired or invalid. Run the installer again to re-authenticate.'
  };
}

/**
 * Validate token with coordinator
 */
async function validateToken(token, coordinatorUrl) {
  try {
    const response = await axios.get(`${coordinatorUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 10000
    });
    return response.status === 200;
  } catch (err) {
    return false;
  }
}

/**
 * Clear saved token
 */
function clearToken() {
  const fs = require('fs');
  const { getPaths } = require('./config');
  const { tokenPath } = getPaths();
  try {
    if (fs.existsSync(tokenPath)) {
      fs.unlinkSync(tokenPath);
    }
  } catch (err) {
    // Ignore
  }
}

module.exports = {
  ensureAuthenticated,
  validateToken,
  clearToken
};
