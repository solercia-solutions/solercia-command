/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

// ─── Theme ────────────────────────────────────────────────────────────────────
export { ThemeService }        from './lib/theme/theme.service';
export { provideTheme }        from './lib/theme/theme.provider';
export { DEFAULT_THEME }       from './lib/theme/default-theme';
export type {
  ThemeFile,
  ThemeConfig,
  ThemeMeta,
  ThemeColors,
  ThemeTypography,
  ThemeMotion,
  ThemeScale,
}                              from './lib/theme/theme.model';

// ─── Logging ──────────────────────────────────────────────────────────────────
export { LogLevel }            from './lib/logging/log-level';
export { BokiLogger }          from './lib/logging/logger.service';
export type { ScopedLogger }   from './lib/logging/logger.service';
export { provideBokiLogger }   from './lib/logging/provide-logger';
export { BOKI_LOGGER_CONFIG }  from './lib/logging/logger.config';
export type {
  BokiLoggerConfig,
  LogEntry,
}                              from './lib/logging/logger.config';

// ─── Errors ───────────────────────────────────────────────────────────────────
export { AppError }                   from './lib/errors/app-error';
export { BokiErrorHandler }           from './lib/errors/error-handler';
export { bokiHttpErrorInterceptor }   from './lib/errors/http-error.interceptor';
export { provideBokiErrors }          from './lib/errors/provide-errors';

// ─── Components ───────────────────────────────────────────────────────────────
export { CardComponent }       from './lib/components/card/card.component';
export { ButtonComponent }     from './lib/components/button/button.component';
export type { ButtonVariant }  from './lib/components/button/button.component';
