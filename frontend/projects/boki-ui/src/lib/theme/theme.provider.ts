/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { APP_INITIALIZER, Provider } from '@angular/core';
import { ThemeService } from './theme.service';

const DEFAULT_THEME_URL = 'assets/themes/default.json';

function initializeTheme(themeService: ThemeService): () => Promise<void> {
  return () => themeService.loadTheme(DEFAULT_THEME_URL);
}

/**
 * Registers ThemeService as an APP_INITIALIZER so the theme JSON is loaded
 * before the first render. Falls back to the bundled DEFAULT_THEME if the
 * HTTP request fails.
 *
 * Usage in app.config.ts:
 *   providers: [provideHttpClient(), provideTheme()]
 *
 * To load a custom URL, call ThemeService.loadTheme(url) directly after init.
 */
export function provideTheme(): Provider[] {
  return [
    {
      provide: APP_INITIALIZER,
      useFactory: initializeTheme,
      deps: [ThemeService],
      multi: true,
    },
  ];
}
