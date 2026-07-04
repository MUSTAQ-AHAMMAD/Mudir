// tests/setup.js
// Global Jest setup: force a test-friendly config before any src module loads.
'use strict';

process.env.NODE_ENV = 'test';
process.env.TWILIO_VALIDATE_SIGNATURE = 'false';
process.env.LOG_LEVEL = 'silent';
