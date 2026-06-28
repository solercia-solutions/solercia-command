/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { Injectable, signal, computed, effect, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { ThemeConfig, ThemeFile } from './theme.model';
import { DEFAULT_THEME } from './default-theme';

// Unified with the early anti-flash script in index.html.
const THEME_PREF_KEY = 'sp-dark-mode';

/**
 * JSON-driven, signal-based theme controller.
 *
 * Loads a ThemeFile (light + dark) at startup and projects the active mode
 * into CSS custom properties (`--sp-*`). Colors become "R G B" channels so
 * Tailwind utilities can apply alpha; radius/shadow/typography/motion are
 * injected as raw values.
 *
 * Falls back to DEFAULT_THEME (bundled) if the JSON request fails, ensuring
 * the app is always themed even in offline or static-hosting scenarios.
 *
 * To re-theme (incl. per-tenant): call loadTheme() with another JSON URL.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly http = inject(HttpClient);

  private themeFile = signal<ThemeFile>(DEFAULT_THEME);
  private _isDark = signal(this.loadDarkPreference());

  readonly isDark = this._isDark.asReadonly();

  readonly config = computed<ThemeConfig>(() =>
    this._isDark() ? this.themeFile().dark : this.themeFile().light
  );

  constructor() {
    effect(() => {
      this.applyCssVariables(this.config());
    });
  }

  async loadTheme(url: string): Promise<void> {
    try {
      const file = await firstValueFrom(this.http.get<ThemeFile>(url));
      this.themeFile.set(file);
    } catch {
      // DEFAULT_THEME is already active; CSS variables remain valid.
      console.warn('@boki/ui ThemeService: failed to load theme JSON, using bundled default.');
    }
  }

  /** Load a ThemeFile object directly (no HTTP request). */
  loadThemeObject(file: ThemeFile): void {
    this.themeFile.set(file);
  }

  toggleMode(): void {
    const next = !this._isDark();
    this._isDark.set(next);
    localStorage.setItem(THEME_PREF_KEY, String(next));
    this.applyDarkClass(next);
  }

  setDarkMode(dark: boolean): void {
    this._isDark.set(dark);
    localStorage.setItem(THEME_PREF_KEY, String(dark));
    this.applyDarkClass(dark);
  }

  private loadDarkPreference(): boolean {
    const stored = localStorage.getItem(THEME_PREF_KEY);
    if (stored !== null) return stored === 'true';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  private applyDarkClass(dark: boolean): void {
    document.documentElement.classList.toggle('dark', dark);
  }

  private applyCssVariables(cfg: ThemeConfig): void {
    const root = document.documentElement.style;

    // Colors -> "R G B" channels so Tailwind can do rgb(var(--sp-x) / <alpha>).
    for (const [key, value] of Object.entries(cfg.color)) {
      root.setProperty(`--sp-${this.kebab(key)}`, this.toChannels(value));
    }

    // Raw-value scales.
    for (const [key, value] of Object.entries(cfg.radius)) {
      root.setProperty(`--sp-radius-${key}`, value);
    }
    for (const [key, value] of Object.entries(cfg.shadow)) {
      root.setProperty(`--sp-shadow-${key}`, value);
    }

    root.setProperty('--sp-font-sans', cfg.typography.fontSans);
    root.setProperty('--sp-font-display', cfg.typography.fontDisplay);
    root.setProperty('--sp-font-mono', cfg.typography.fontMono);

    root.setProperty('--sp-motion-fast', cfg.motion.fast);
    root.setProperty('--sp-motion-base', cfg.motion.base);
    root.setProperty('--sp-motion-slow', cfg.motion.slow);
    root.setProperty('--sp-ease', cfg.motion.ease);

    this.applyDarkClass(this._isDark());
  }

  /** camelCase -> kebab-case (brandFg -> brand-fg, borderStrong -> border-strong). */
  private kebab(key: string): string {
    return key.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
  }

  /** "#4F46E5" -> "79 70 229". Passes through non-hex values unchanged. */
  private toChannels(hex: string): string {
    const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
    if (!m) return hex;
    let h = m[1];
    if (h.length === 3) {
      h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    }
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `${r} ${g} ${b}`;
  }
}
