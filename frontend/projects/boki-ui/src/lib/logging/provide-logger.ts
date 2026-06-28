/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { Provider } from '@angular/core';
import { LogLevel } from './log-level';
import { BokiLoggerConfig, BOKI_LOGGER_CONFIG } from './logger.config';

/**
 * Registers BokiLogger configuration via BOKI_LOGGER_CONFIG.
 *
 * Call in app.config.ts providers:
 *   provideBokiLogger({ minLevel: LogLevel.DEBUG })        // development
 *   provideBokiLogger({ minLevel: LogLevel.WARN })         // production
 *   provideBokiLogger({ minLevel: LogLevel.ERROR, sink })  // custom sink
 *
 * If omitted entirely, the default factory on BOKI_LOGGER_CONFIG kicks in
 * (minLevel WARN, console sink, no prefix) — safe for production.
 */
export function provideBokiLogger(config?: Partial<BokiLoggerConfig>): Provider[] {
  const resolved: BokiLoggerConfig = {
    minLevel: config?.minLevel ?? LogLevel.WARN,
    prefix:   config?.prefix,
    sink:     config?.sink,
  };

  return [
    {
      provide:  BOKI_LOGGER_CONFIG,
      useValue: resolved,
    },
  ];
}
