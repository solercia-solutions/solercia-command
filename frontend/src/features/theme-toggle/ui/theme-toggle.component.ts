import { Component, ChangeDetectionStrategy, inject } from '@angular/core';
import { ThemeService } from '@shared/tokens';
import { SolIconComponent } from '@shared/ui';

@Component({
  standalone: true,
  selector: 'sol-theme-toggle',
  imports: [SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      type="button"
      class="sol-theme-toggle"
      (click)="themeService.toggleMode()"
      [attr.aria-label]="themeService.isDark() ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'"
    >
      @if (themeService.isDark()) {
        <sol-icon name="sun" variant="fill" class="sol-theme-toggle__icon" />
      } @else {
        <sol-icon name="moon" variant="fill" class="sol-theme-toggle__icon" />
      }
    </button>
  `,
  styles: [`
    .sol-theme-toggle {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border: none;
      border-radius: var(--sol-border-radius-md, 8px);
      background: transparent;
      color: var(--sol-color-text-secondary, #4B5563);
      cursor: pointer;
      transition: background-color 0.2s, color 0.2s;
    }
    .sol-theme-toggle:hover {
      background: color-mix(in srgb, var(--sol-color-primary, #2563EB) 10%, transparent);
      color: var(--sol-color-primary, #2563EB);
    }
    .sol-theme-toggle__icon { width: 20px; height: 20px; }

    /* Objetivo táctil bajo el breakpoint canónico (ley de Fitts, 44 px):
       crece la caja del <button>, que es el elemento que recibe el toque; el ícono sigue
       en 20px. Aditivo, nunca global: en escritorio el control conserva su densidad. */
    @media (max-width: 767px) {
      .sol-theme-toggle {
        width: var(--sol-size-control-touch, 44px);
        height: var(--sol-size-control-touch, 44px);
      }
    }
  `],
})
export class ThemeToggleComponent {
  protected themeService = inject(ThemeService);
}
