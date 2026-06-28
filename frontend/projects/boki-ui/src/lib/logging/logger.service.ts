/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { Injectable, inject } from '@angular/core';
import { LogLevel } from './log-level';
import { BokiLoggerConfig, LogEntry, BOKI_LOGGER_CONFIG } from './logger.config';

/**
 * Structured, level-gated logger for @boki/ui consumers.
 *
 * - Emits structured LogEntry objects (ts, level, context, message, data).
 * - Output is gated by `minLevel` from BOKI_LOGGER_CONFIG.
 * - The default sink uses console.{debug,info,warn,error} — the only place
 *   console.* is called inside @boki/ui. Override `sink` to replace it.
 * - Use `withContext(ctx)` to get a scoped logger tied to a component/service.
 *
 * Usage:
 *   private readonly log = inject(BokiLogger).withContext('MyComponent');
 *   this.log.warn('Item not found', { id });
 */
@Injectable({ providedIn: 'root' })
export class BokiLogger {
  private readonly config: BokiLoggerConfig = inject(BOKI_LOGGER_CONFIG);

  debug(message: string, data?: unknown, context?: string): void {
    this.emit(LogLevel.DEBUG, message, data, context);
  }

  info(message: string, data?: unknown, context?: string): void {
    this.emit(LogLevel.INFO, message, data, context);
  }

  warn(message: string, data?: unknown, context?: string): void {
    this.emit(LogLevel.WARN, message, data, context);
  }

  error(message: string, data?: unknown, context?: string): void {
    this.emit(LogLevel.ERROR, message, data, context);
  }

  /**
   * Returns a scoped wrapper whose methods pre-fill the `context` parameter.
   * The wrapper holds no state — it delegates to this BokiLogger instance.
   *
   * Example:
   *   private log = inject(BokiLogger).withContext('AuthService');
   *   this.log.warn('Token expired');
   */
  withContext(ctx: string): ScopedLogger {
    return {
      debug: (msg, data?) => this.debug(msg, data, ctx),
      info:  (msg, data?) => this.info(msg, data, ctx),
      warn:  (msg, data?) => this.warn(msg, data, ctx),
      error: (msg, data?) => this.error(msg, data, ctx),
    };
  }

  private emit(level: LogLevel, message: string, data: unknown, context?: string): void {
    if (level < this.config.minLevel) return;

    const entry: LogEntry = {
      ts: new Date().toISOString(),
      level,
      context,
      message: this.config.prefix ? `${this.config.prefix} ${message}` : message,
      data,
    };

    if (this.config.sink) {
      this.config.sink(entry);
    } else {
      defaultConsoleSink(entry);
    }
  }
}

/** Scoped logger interface returned by BokiLogger.withContext(). */
export interface ScopedLogger {
  debug(message: string, data?: unknown): void;
  info(message: string, data?: unknown): void;
  warn(message: string, data?: unknown): void;
  error(message: string, data?: unknown): void;
}

/**
 * Built-in console sink. This is the ONLY place in @boki/ui that calls
 * console.*. Replace it via BokiLoggerConfig.sink.
 */
function defaultConsoleSink(entry: LogEntry): void {
  const prefix = entry.context ? `[${entry.context}]` : '';
  const label  = `${entry.ts} ${LogLevel[entry.level]}${prefix ? ' ' + prefix : ''}`;
  const args: unknown[] = [label, entry.message];
  if (entry.data !== undefined) args.push(entry.data);

  switch (entry.level) {
    case LogLevel.DEBUG: console.debug(...args); break;
    case LogLevel.INFO:  console.info(...args);  break;
    case LogLevel.WARN:  console.warn(...args);  break;
    case LogLevel.ERROR: console.error(...args); break;
    default:             console.log(...args);
  }
}
