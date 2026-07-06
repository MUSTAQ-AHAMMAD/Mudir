// logger.js
// -----------------------------------------------------------------------------
// Thin wrapper around pino so every module logs in a consistent, structured
// (JSON) format. In development we pretty-print for readability.
// -----------------------------------------------------------------------------
'use strict';

const pino = require('pino');
const { config } = require('./config');

const logger = pino({
  level: config.logLevel,
  base: { service: 'mudir-backend' },
  // Redact anything that looks like a secret so tokens never hit the logs.
  redact: {
    paths: ['req.headers.authorization', '*.authToken', '*.apiKey', '*.serviceKey'],
    censor: '[REDACTED]',
  },
  transport:
    config.env === 'development'
      ? { target: 'pino-pretty', options: { colorize: true, translateTime: 'SYS:standard' } }
      : undefined,
});

module.exports = logger;
