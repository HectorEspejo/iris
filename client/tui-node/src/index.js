#!/usr/bin/env node
/**
 * Iris Network TUI - Entry Point
 * Futuristic Brutalist Dashboard
 */

const IrisApp = require('./app');

async function main() {
  const app = new IrisApp();

  try {
    await app.run();
  } catch (err) {
    console.error('Fatal error:', err.message);
    process.exit(1);
  }
}

main();
