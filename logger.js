/**
 * logger.js — Centralized leveled logger for the Window Move & Resize extension.
 *
 * GNOME Shell extensions run inside the gnome-shell process, so their output is
 * routed to the systemd journal (read with `journalctl --user -f /usr/bin/gnome-shell`
 * or `journalctl -f -o cat _COMM=gnome-shell`). This module provides a small
 * leveled wrapper over the global `console` so every component logs through one
 * consistent, timestamped, prefixed path with a tunable verbosity threshold.
 *
 * Components:
 *   - LogLevel: Ordered severity levels (error < warn < info < debug < verbose).
 *   - setLogLevel(): Adjust the active verbosity threshold.
 *   - logger: Object exposing error/warn/info/debug/verbose log methods.
 *
 * Usage:
 *   import { logger } from './logger.js';
 *   logger.info('extension enabled');
 *   logger.debug(`starting drag for "${win.get_title()}"`);
 */

/** Tag prepended to every log line so the extension's output is greppable. */
const LOG_PREFIX = 'window-move-resize';

/**
 * Ordered severity levels. A message is emitted only when its level is at or
 * below the active threshold, so a threshold of INFO suppresses DEBUG/VERBOSE.
 *
 * @enum {number}
 */
export const LogLevel = Object.freeze({
  ERROR: 0,
  WARN: 1,
  INFO: 2,
  DEBUG: 3,
  VERBOSE: 4,
});

/** Human-readable name for each level, used in the formatted log line. */
const LEVEL_NAMES = Object.freeze({
  [LogLevel.ERROR]: 'ERROR',
  [LogLevel.WARN]: 'WARN',
  [LogLevel.INFO]: 'INFO',
  [LogLevel.DEBUG]: 'DEBUG',
  [LogLevel.VERBOSE]: 'VERBOSE',
});

/**
 * Active verbosity threshold. Messages with a level above this value are
 * dropped. Defaults to INFO so normal installs keep the journal readable while
 * still recording lifecycle and gesture transitions.
 *
 * @type {number}
 */
let activeLevel = LogLevel.INFO;

/**
 * Set the active verbosity threshold.
 *
 * @param {number} level One of the LogLevel values; messages above it are
 *   suppressed.
 * @returns {void}
 */
export function setLogLevel(level) {
  activeLevel = level;
}

/**
 * Format and emit a single log line when its level passes the threshold.
 *
 * @param {number} level Severity of this message (a LogLevel value).
 * @param {string} message Text to log.
 * @returns {void}
 */
function emit(level, message) {
  if (level > activeLevel) {
    return;
  }

  const line = `${LOG_PREFIX} [${LEVEL_NAMES[level]}] ${new Date().toISOString()} ${message}`;

  // console.error routes to the journal at error priority; everything else uses
  // console.log/debug so severity is preserved in journalctl filtering.
  if (level === LogLevel.ERROR) {
    console.error(line);
  } else if (level === LogLevel.WARN) {
    console.warn(line);
  } else if (level === LogLevel.DEBUG || level === LogLevel.VERBOSE) {
    console.debug(line);
  } else {
    console.log(line);
  }
}

/**
 * Leveled logging facade shared by every component of the extension.
 *
 * Each method takes a single pre-formatted message string and forwards it to
 * emit() at the matching severity.
 */
export const logger = Object.freeze({
  /**
   * Log an error (always emitted).
   *
   * @param {string} message Text describing the failure.
   * @returns {void}
   */
  error(message) {
    emit(LogLevel.ERROR, message);
  },

  /**
   * Log a warning about a recoverable or unexpected condition.
   *
   * @param {string} message Text describing the condition.
   * @returns {void}
   */
  warn(message) {
    emit(LogLevel.WARN, message);
  },

  /**
   * Log an informational lifecycle message (enable/disable, gesture start/end).
   *
   * @param {string} message Text describing the event.
   * @returns {void}
   */
  info(message) {
    emit(LogLevel.INFO, message);
  },

  /**
   * Log a debug-level detail useful while diagnosing gesture behavior.
   *
   * @param {string} message Text describing the detail.
   * @returns {void}
   */
  debug(message) {
    emit(LogLevel.DEBUG, message);
  },

  /**
   * Log the most fine-grained tracing detail (suppressed by default).
   *
   * @param {string} message Text describing the detail.
   * @returns {void}
   */
  verbose(message) {
    emit(LogLevel.VERBOSE, message);
  },
});
