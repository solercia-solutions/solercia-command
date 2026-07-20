import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  input,
  output,
  viewChild,
} from '@angular/core';
import { SolIconComponent } from '@solercia/ui';
import { I18nService } from '@shared/i18n';

/**
 * Panel lateral deslizante (drawer) — componente app-local.
 *
 * NOTA: candidato a promoverse a `@solercia/ui` (la lib aún no trae un
 * sol-drawer); mientras tanto vive aquí siguiendo el mismo contrato visual
 * de `sol-modal` (tokens `--sol-*`, BEM, sin Tailwind interno — mismo patrón
 * que `widgets/sidebar/ui/sidebar.component.ts`).
 *
 * API:
 * - `open`            — controla la visibilidad (el padre es el dueño del estado).
 * - `title`           — encabezado del panel.
 * - `position`        — solo 'right' por ahora (default).
 * - `size`            — 'md' (420px) | 'lg' (560px).
 * - `blur`            — cuando es `false` el backdrop NO aplica backdrop-filter,
 *                       solo un velo suave (útil sobre vistas densas).
 * - `closeOnBackdrop` — clic en el velo cierra (default `true`).
 * - `closed`          — emitido cuando el drawer pide cerrarse (Escape,
 *                       backdrop o botón X); el padre decide poner `open=false`.
 *
 * Accesibilidad: role="dialog" + aria-modal, cierre con Escape y foco
 * gestionado (entra al panel al abrir, regresa al elemento previo al cerrar).
 */
@Component({
  selector: 'sol-drawer',
  standalone: true,
  imports: [SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (open()) {
      <div
        class="sol-drawer"
        [class.sol-drawer--no-blur]="!blur()"
      >
        <div
          class="sol-drawer__backdrop"
          aria-hidden="true"
          (click)="onBackdropClick()"
        ></div>

        <div
          #panel
          class="sol-drawer__panel"
          [class.sol-drawer__panel--lg]="size() === 'lg'"
          role="dialog"
          aria-modal="true"
          [attr.aria-label]="title()"
          tabindex="-1"
          (keydown.escape)="requestClose()"
        >
          <header class="sol-drawer__header">
            <h2 class="sol-drawer__title">{{ title() }}</h2>
            <button
              type="button"
              class="sol-drawer__close"
              [attr.aria-label]="closeAria()"
              (click)="requestClose()"
            >
              <sol-icon name="x-mark" size="sm" />
            </button>
          </header>

          <div class="sol-drawer__body">
            <ng-content></ng-content>
          </div>
        </div>
      </div>
    }
  `,
  styles: `
    .sol-drawer {
      position: fixed;
      inset: 0;
      z-index: var(--sol-z-modal, 1000);
      display: flex;
      justify-content: flex-end;
    }

    .sol-drawer__backdrop {
      position: absolute;
      inset: 0;
      background: color-mix(in srgb, #000 45%, transparent);
      backdrop-filter: blur(2px);
      animation: sol-drawer-fade-in 0.2s ease;
    }

    /* blur=false: velo suave sin backdrop-filter (más liviano sobre vistas densas). */
    .sol-drawer--no-blur .sol-drawer__backdrop {
      backdrop-filter: none;
      background: color-mix(in srgb, #000 30%, transparent);
    }

    .sol-drawer__panel {
      position: relative;
      display: flex;
      flex-direction: column;
      width: min(420px, 100vw);
      height: 100%;
      background: var(--sol-bg-surface, #ffffff);
      color: var(--sol-color-text-primary, #111827);
      border-left: var(--sol-border-width-default, 1px) solid var(--sol-border-color-default, #e5e7eb);
      box-shadow: var(--sol-shadow-lg, -8px 0 24px rgba(0, 0, 0, 0.12));
      animation: sol-drawer-slide-in 0.25s ease;
      outline: none;
    }

    .sol-drawer__panel--lg {
      width: min(560px, 100vw);
    }

    .sol-drawer__header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--sol-space-sm, 0.5rem);
      padding: var(--sol-space-md, 0.75rem) var(--sol-space-lg, 1rem);
      border-bottom: var(--sol-border-width-default, 1px) solid var(--sol-border-color-default, #e5e7eb);
    }

    .sol-drawer__title {
      margin: 0;
      font-size: var(--sol-font-size-lg, 1.125rem);
      font-weight: 600;
      color: var(--sol-color-text-primary, #111827);
    }

    .sol-drawer__close {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border: none;
      border-radius: var(--sol-border-radius-md, 8px);
      background: transparent;
      color: var(--sol-color-text-secondary, #6b7280);
      cursor: pointer;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    .sol-drawer__close:hover {
      background: color-mix(in srgb, var(--sol-color-primary, #2563eb) 8%, transparent);
      color: var(--sol-color-primary, #2563eb);
    }

    .sol-drawer__body {
      flex: 1;
      overflow-y: auto;
      padding: var(--sol-space-lg, 1rem);
    }

    @keyframes sol-drawer-fade-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    @keyframes sol-drawer-slide-in {
      from { transform: translateX(100%); }
      to { transform: translateX(0); }
    }
  `,
})
export class SolDrawerComponent {
  private readonly i18n = inject(I18nService);

  /** Etiqueta accesible del botón de cierre, reactiva al idioma activo. */
  protected readonly closeAria = this.i18n.t('shared.drawer.closeAria');

  /** Controla la visibilidad del drawer (estado propiedad del padre). */
  readonly open = input<boolean>(false);

  /** Título mostrado en el encabezado del panel. */
  readonly title = input<string>('');

  /** Lado del que emerge el panel. Solo 'right' está implementado. */
  readonly position = input<'right'>('right');

  /** Ancho del panel: 'md' (420px) o 'lg' (560px). */
  readonly size = input<'md' | 'lg'>('md');

  /** Con `false`, el backdrop no aplica backdrop-filter (solo un velo suave). */
  readonly blur = input<boolean>(true);

  /** Si el clic sobre el backdrop cierra el drawer. */
  readonly closeOnBackdrop = input<boolean>(true);

  /** Emitido cuando el drawer solicita cerrarse (Escape, backdrop o X). */
  readonly closed = output<void>();

  private readonly panel = viewChild<ElementRef<HTMLElement>>('panel');

  /** Elemento con foco antes de abrir, para restaurarlo al cerrar. */
  private previouslyFocused: HTMLElement | null = null;

  constructor() {
    // Focus trap básico: al abrir, el foco entra al panel; al cerrar, regresa
    // al elemento que lo tenía (patrón mínimo de diálogo accesible).
    effect(() => {
      if (this.open()) {
        this.previouslyFocused =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null;
        // El panel se renderiza dentro del mismo ciclo del effect (@if).
        queueMicrotask(() => this.panel()?.nativeElement.focus());
      } else if (this.previouslyFocused) {
        this.previouslyFocused.focus();
        this.previouslyFocused = null;
      }
    });
  }

  protected onBackdropClick(): void {
    if (this.closeOnBackdrop()) {
      this.requestClose();
    }
  }

  protected requestClose(): void {
    this.closed.emit();
  }
}
