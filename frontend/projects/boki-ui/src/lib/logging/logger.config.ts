/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { InjectionToken } from '@angular/core';
import { LogLevel } from './log-level';

/** Structured log entry produced by BokiLogger. */
export interface LogEntry {
  /** ISO-8601 timestamp at emission time. */
  ts: string;
  level: LogLevel;
  /** Optional scoped context label (e.g. component or service name). */
  context?: string;
  message: string;
  data?: unknown;
}

/** Configuration contract for BokiLogger. */
export interface BokiLoggerConfig {
  /** Minimum level to emit. Entries below this level are silently discarded. */
  minLevel: LogLevel;
  /** Optional prefix prepended to every message (e.g. '[MyApp]'). */
  prefix?: string;
  /**
   * Custom sink function. Receives a fully-formed LogEntry.
   * Defaults to the built-in console sink when not provided.
   * Override to send logs to a remote service, test spy, etc.
   * The default sink is the ONLY place console.* is called inside @boki/ui.
   */
  sink?: (entry: LogEntry) => void;
}

/** Default configuration factory — WARN level, no prefix, console sink. */
const defaultConfig = (): BokiLoggerConfig => ({ minLevel: LogLevel.WARN });

/** Injection token for BokiLoggerConfig. */
export const BOKI_LOGGER_CONFIG = new InjectionToken<BokiLoggerConfig>(
  '@boki/ui BokiLoggerConfig',
  { factory: defaultConfig }
);
