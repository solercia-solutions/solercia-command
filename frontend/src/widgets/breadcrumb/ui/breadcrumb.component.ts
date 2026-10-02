import { Component, ChangeDetectionStrategy, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { I18nService } from '@shared/i18n';
import { SolIconComponent } from '@shared/ui';
import type { BreadcrumbItem } from '../model/breadcrumb.model';

/**
 * Breadcrumb del shell: sección → agrupaciones → opción actual. Presentacional puro — recibe los
 * tramos ya resueltos (quien lo monta los arma desde el árbol del menú y la URL actual, ver
 * `breadcrumbTrail` en `entities/menu`).
 *
 * Reglas de render:
 *   - El ÚLTIMO tramo es la ubicación actual (`aria-current="page"`) y nunca es enlace, traiga o no
 *     `route`.
 *   - Un tramo intermedio sin `route` (agrupación del menú, sin vista propia) es texto plano.
 *   - Bajo 768px los tramos intermedios se reemplazan por una elipsis: en 390px un camino de cuatro
 *     niveles no cabe y lo importante es de dónde viene (sección) y dónde está (opción actual).
 */
@Component({
  selector: 'sol-breadcrumb',
  standalone: true,
  imports: [RouterLink, SolIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <nav class="sol-breadcrumb" [attr.aria-label]="navLabel()">
      <ol class="sol-breadcrumb__list">
        @for (item of items(); track $index; let first = $first; let last = $last) {
          <li
            class="sol-breadcrumb__item"
            [class.sol-breadcrumb__item--middle]="!first && !last"
            [class.sol-breadcrumb__item--current]="last"
          >
            @if (!first) {
              <sol-icon class="sol-breadcrumb__separator" name="chevron-right" size="sm" aria-hidden="true" />
            }
            @if (item.route && !last) {
              <a class="sol-breadcrumb__link" [routerLink]="item.route">
                @if (item.icon) {
                  <sol-icon class="sol-breadcrumb__icon" [name]="item.icon" size="sm" />
                }
                <span class="sol-breadcrumb__label">{{ item.label }}</span>
              </a>
            } @else {
              <span class="sol-breadcrumb__text" [attr.aria-current]="last ? 'page' : null">
                @if (item.icon) {
                  <sol-icon class="sol-breadcrumb__icon" [name]="item.icon" size="sm" />
                }
                <span class="sol-breadcrumb__label">{{ item.label }}</span>
              </span>
            }
          </li>
          @if (first && hasMiddle()) {
            <!-- Solo visible bajo el breakpoint móvil (CSS), en el lugar de los tramos intermedios. -->
            <li class="sol-breadcrumb__ellipsis" aria-hidden="true">
              <sol-icon class="sol-breadcrumb__separator" name="chevron-right" size="sm" />
              <span class="sol-breadcrumb__text">…</span>
            </li>
          }
        }
      </ol>
    </nav>
  `,
  styles: `
    .sol-breadcrumb {
      display: flex;
      align-items: center;
      min-height: 100%;
      /* Un camino largo se desplaza dentro de su propia franja: el documento nunca hace scroll
         horizontal por culpa del breadcrumb. */
      overflow-x: auto;
      scrollbar-width: none;
    }

    .sol-breadcrumb::-webkit-scrollbar {
      display: none;
    }

    .sol-breadcrumb__list {
      display: flex;
      align-items: center;
      gap: var(--sol-space-xs, 4px);
      max-width: 100%;
      min-width: 0;
      margin: 0;
      padding: 0;
      list-style: none;
      white-space: nowrap;
    }

    /* Cada tramo puede encogerse (min-width:0 en toda la cadena hasta la etiqueta): así, cuando el
       camino no cabe, las etiquetas se recortan con elipsis en vez de empujar la fila fuera de la
       franja. El tramo actual es el que más ancho conserva porque responde «¿dónde estoy?». */
    .sol-breadcrumb__item,
    .sol-breadcrumb__ellipsis {
      display: inline-flex;
      align-items: center;
      gap: var(--sol-space-xs, 4px);
      flex: 0 1 auto;
      min-width: 0;
    }

    .sol-breadcrumb__item--current {
      flex: 1 1 auto;
    }

    .sol-breadcrumb__ellipsis {
      flex: 0 0 auto;
    }

    .sol-breadcrumb__separator {
      flex-shrink: 0;
      color: var(--sol-color-text-muted, #8a94a6);
    }

    .sol-breadcrumb__link,
    .sol-breadcrumb__text {
      display: inline-flex;
      align-items: center;
      gap: var(--sol-space-xs, 4px);
      min-width: 0;
      max-width: 100%;
      min-height: var(--sol-size-control-sm, 32px);
      padding: 0 var(--sol-space-xs, 4px);
      border-radius: var(--sol-border-radius-sm, 6px);
      font-size: var(--sol-font-size-sm, 0.875rem);
      color: var(--sol-color-text-secondary, #6b7280);
    }

    .sol-breadcrumb__link {
      text-decoration: none;
      transition: background-color var(--sol-dur-fast, 120ms) var(--sol-ease, ease), color var(--sol-dur-fast, 120ms) var(--sol-ease, ease);
    }

    .sol-breadcrumb__link:hover,
    .sol-breadcrumb__link:focus-visible {
      background: color-mix(in srgb, var(--sol-color-primary, #2563eb) 8%, transparent);
      color: var(--sol-color-primary, #2563eb);
    }

    .sol-breadcrumb__item--current .sol-breadcrumb__text {
      color: var(--sol-color-text-primary, #111827);
      font-weight: 600;
    }

    .sol-breadcrumb__icon {
      flex-shrink: 0;
    }

    /* Cada tramo se recorta con elipsis antes que empujar al siguiente fuera de la franja; el
       tramo actual conserva más ancho porque es el que responde «¿dónde estoy?». */
    .sol-breadcrumb__label {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 14rem;
    }

    .sol-breadcrumb__item--current .sol-breadcrumb__label {
      max-width: 22rem;
    }

    /* La elipsis móvil no existe en desktop. */
    .sol-breadcrumb__ellipsis {
      display: none;
    }

    @media (max-width: 767px) {
      .sol-breadcrumb__item--middle {
        display: none;
      }

      .sol-breadcrumb__ellipsis {
        display: inline-flex;
      }

      /* Objetivo táctil mínimo (ley de Fitts) e inputs/enlaces legibles sin zoom. */
      .sol-breadcrumb__link,
      .sol-breadcrumb__text {
        min-height: var(--sol-size-control-touch, 44px);
        font-size: var(--sol-font-size-touch-input, 1rem);
      }

      /* La sección cede primero (tope corto); el tramo actual toma lo que quede de la franja. */
      .sol-breadcrumb__label {
        max-width: 8rem;
      }

      .sol-breadcrumb__item--current .sol-breadcrumb__label {
        max-width: none;
      }
    }
  `,
})
export class SolBreadcrumbComponent {
  protected readonly navLabel = inject(I18nService).t('widgets.breadcrumb.navLabel');

  /** Tramos en orden: el primero es la sección, el último la ubicación actual. */
  readonly items = input<BreadcrumbItem[]>([]);

  /** Hay tramos intermedios (agrupaciones): decide si la elipsis móvil se renderiza. */
  protected readonly hasMiddle = computed(() => this.items().length > 2);
}
