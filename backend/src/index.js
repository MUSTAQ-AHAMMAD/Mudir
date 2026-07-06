// index.js
// -----------------------------------------------------------------------------
// Application entrypoint. Wires up Express, security middleware, the Twilio
// webhook, the dashboard API, and the cron scheduler, then starts listening.
// -----------------------------------------------------------------------------
'use strict';

const express = require('express');
const rateLimit = require('express-rate-limit');
const { config, assertProductionConfig } = require('./config');
const logger = require('./logger');
const { router: webhookRouter } = require('./webhook');
const { router: apiRouter } = require('./api');
const cronJobs = require('./cron-jobs');

/**
 * Build the Express app (exported so tests can mount it with supertest).
 * @returns {import('express').Express}
 */
function createApp() {
  const app = express();
  app.disable('x-powered-by');

  // Twilio posts urlencoded bodies; the dashboard API uses JSON.
  app.use(express.urlencoded({ extended: false }));
  app.use(express.json());

  // Rate limit the public webhook to prevent spam/abuse.
  const limiter = rateLimit({
    windowMs: config.rateLimit.windowMs,
    max: config.rateLimit.max,
    standardHeaders: true,
    legacyHeaders: false,
  });
  app.use('/webhook', limiter);

  // Health check for load balancers / uptime monitors.
  app.get('/health', (req, res) => res.json({ status: 'ok', service: 'mudir', env: config.env }));

  app.use('/', webhookRouter);
  app.use('/api', apiRouter);

  return app;
}

/**
 * Boot the server and cron scheduler.
 */
function start() {
  assertProductionConfig();
  const app = createApp();
  const server = app.listen(config.port, () => {
    logger.info({ port: config.port, env: config.env }, 'Mudir backend listening');
  });
  // Only schedule cron in long-running processes (not during tests).
  cronJobs.start();

  // Graceful shutdown.
  const shutdown = (signal) => {
    logger.info({ signal }, 'Shutting down');
    server.close(() => process.exit(0));
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
  return server;
}

// Start only when run directly (not when imported by tests).
if (require.main === module) {
  start();
}

module.exports = { createApp, start };
