import { Injectable, signal } from '@angular/core';

const THEME_KEY = 'sp-dark-mode';

/**
 * Signal-based light/dark theme controller.
 * Toggles the 'dark' class on <html> (Tailwind darkMode:'class') and
 * persists the choice in localStorage. Initial value comes from
 * localStorage, falling back to the OS prefers-color-scheme.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly _isDark = signal<boolean>(this.readInitial());

  /** Read-only signal exposing the current dark-mode state. */
  readonly isDark = this._isDark.asReadonly();

  constructor() {
    // Keep the DOM class in sync with the initial value (index.html may
    // have already applied it, but this guarantees consistency).
    this.applyDarkClass(this._isDark());
  }

  /** Flip between light and dark, persisting the new value. */
  toggle(): void {
    const next = !this._isDark();
    this._isDark.set(next);
    localStorage.setItem(THEME_KEY, String(next));
    this.applyDarkClass(next);
  }

  private readInitial(): boolean {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored !== null) {
      return stored === 'true';
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  private applyDarkClass(dark: boolean): void {
    const root = document.documentElement;
    if (dark) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }
}
