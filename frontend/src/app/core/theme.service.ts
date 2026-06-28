import { Injectable, signal, computed, effect } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { ThemeConfig, ThemeFile } from './theme.model';

// Unified with the early anti-flash script in index.html.
const THEME_PREF_KEY = 'sp-dark-mode';

/**
 * JSON-driven, signal-based theme controller.
 *
 * Loads a ThemeFile (light + dark) at startup and projects the active mode
 * into CSS custom properties (`--sp-*`). Colors become "R G B" channels so
 * Tailwind utilities can apply alpha; radius/shadow/typography/motion are
 * injected as raw values. styles.scss holds an identical static fallback for
 * first paint and the JSON-failed path.
 *
 * To re-theme (incl. per-tenant): point loadTheme() at another JSON URL.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private themeFile = signal<ThemeFile | null>(null);
  private _isDark = signal(this.loadDarkPreference());

  readonly isDark = this._isDark.asReadonly();

  readonly config = computed<ThemeConfig | null>(() => {
    const file = this.themeFile();
    if (!file) return null;
    return this._isDark() ? file.dark : file.light;
  });

  constructor(private http: HttpClient) {
    effect(() => {
      const cfg = this.config();
      if (cfg) {
        this.applyCssVariables(cfg);
      }
    });
  }

  async loadTheme(url: string): Promise<void> {
    try {
      const file = await firstValueFrom(this.http.get<ThemeFile>(url));
      this.themeFile.set(file);
    } catch {
      // Fallback: the static :root / .dark variables in styles.scss stay in
      // effect, so the app remains fully themed even if the JSON fails to load.
      console.warn('ThemeService: failed to load theme JSON, using CSS fallback.');
    }
  }

  toggleMode(): void {
    const next = !this._isDark();
    this._isDark.set(next);
    localStorage.setItem(THEME_PREF_KEY, String(next));
    this.applyDarkClass(next);
  }

  private loadDarkPreference(): boolean {
    const stored = localStorage.getItem(THEME_PREF_KEY);
    if (stored !== null) return stored === 'true';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  private applyDarkClass(dark: boolean): void {
    const root = document.documentElement;
    root.classList.toggle('dark', dark);
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
