/**
 * Iris Network API Client
 * HTTP client for coordinator communication
 */

const axios = require('axios');

class IrisAPI {
  constructor(coordinatorUrl, token = null) {
    this.coordinatorUrl = coordinatorUrl;
    this.token = token;

    this.client = axios.create({
      baseURL: coordinatorUrl,
      timeout: 10000,
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    });
  }

  /**
   * Set authentication token
   */
  setToken(token) {
    this.token = token;
    this.client.defaults.headers.Authorization = `Bearer ${token}`;
  }

  /**
   * Get network statistics
   */
  async getStats() {
    try {
      const { data } = await this.client.get('/stats');
      return { success: true, data };
    } catch (err) {
      return { success: false, error: err.message, data: null };
    }
  }

  /**
   * Get active nodes list
   */
  async getNodes() {
    try {
      const { data } = await this.client.get('/nodes');
      return { success: true, data };
    } catch (err) {
      return { success: false, error: err.message, data: [] };
    }
  }

  /**
   * Get reputation leaderboard
   */
  async getReputation() {
    try {
      const { data } = await this.client.get('/reputation');
      return { success: true, data };
    } catch (err) {
      return { success: false, error: err.message, data: [] };
    }
  }

  /**
   * Send inference request
   */
  async sendInference(prompt, mode = 'subtasks', difficulty = 'simple') {
    try {
      const { data } = await this.client.post('/inference', {
        prompt,
        mode,
        difficulty
      });
      return { success: true, data };
    } catch (err) {
      const message = err.response?.data?.detail || err.message;
      return { success: false, error: message, data: null };
    }
  }

  /**
   * Get task result
   */
  async getTaskResult(taskId) {
    try {
      const { data } = await this.client.get(`/inference/${taskId}`);
      return { success: true, data };
    } catch (err) {
      return { success: false, error: err.message, data: null };
    }
  }

  /**
   * Poll for task completion
   */
  async pollTaskResult(taskId, maxAttempts = 30, interval = 2000, onProgress = null) {
    for (let i = 0; i < maxAttempts; i++) {
      const result = await this.getTaskResult(taskId);

      if (result.success && result.data) {
        const status = result.data.status;

        if (onProgress) {
          onProgress(status, i + 1, maxAttempts);
        }

        if (status === 'completed') {
          return { success: true, response: result.data.response };
        }

        if (status === 'failed' || status === 'partial') {
          return { success: false, error: 'Task failed' };
        }
      }

      await this._sleep(interval);
    }

    return { success: false, error: 'Timeout waiting for result' };
  }

  /**
   * Health check
   */
  async healthCheck() {
    try {
      const { data } = await this.client.get('/health');
      return { success: true, data };
    } catch (err) {
      return { success: false, error: err.message };
    }
  }

  /**
   * Sleep helper
   */
  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

module.exports = IrisAPI;
