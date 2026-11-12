import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { I18nService } from '@shared/i18n';
import {
  SolDrawerComponent,
  SolEmptyStateComponent,
  SolErrorStateComponent,
  SolSkeletonComponent,
  SolTabsComponent,
  type SolTabItem,
  errorTitleKey,
} from '@shared/ui';

/** Situación del contenido de ayuda; la decide quien lo carga. */
export type HelpDrawerStatus = 'loading' | 'ready' | 'empty' | 'error';

/** Un recurso de ayuda: se abre SIEMPRE en una pestaña nueva, nunca embebido. */
export interface HelpResource {
  readonly id: string;
  readonly title: string;
  readonly description?: string;
  readonly url: string;
  /** Tipo del recurso (manual, video, preguntas frecuentes…): con dos o más tipos hay pestañas. */
  readonly kind: string;
  /** Rótulo visible del tipo, para la pestaña. */
  readonly kindLabel: string;
}

/**
 * Panel lateral de «Ayuda y soporte». Genérico: no sabe de dónde sale la ayuda. Quien lo monta
 * pasa el estado, los recursos y el canal de soporte; el panel resuelve la presentación.
 *
 * - Arriba, una ranura `[helpDiagnostics]` para información de diagnóstico que la persona
 *   pueda copiar a soporte (va primero: es lo que se necesita cuando algo falla).
 * - Pestañas solo con dos o más tipos de recurso (ley de Hick); con uno, el contenido va directo
 *   y la pestaña activa arranca en el primer tipo disponible.
 * - «No hay material» y «no fue posible cargar la ayuda» son estados distintos, con acciones
 *   distintas (enlace a soporte vs. reintentar).
 * - Foco, desenfoque del fondo, bloqueo del scroll y `Escape` los aporta `sol-drawer`.
 */
@Component({
  selector: 'sol-help-drawer',
  standalone: true,
  imports: [SolDrawerComponent, SolEmptyStateComponent, SolErrorStateComponent, SolSkeletonComponent, SolTabsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sol-drawer [open]="open()" [title]="panelTitle()" side="end" size="md" (closed)="closed.emit()">
      <ng-content select="[helpDiagnostics]" />

      @switch (status()) {
        @case ('loading') {
          <div class="sol-help__loading" role="status" aria-live="polite">
            <span class="sol-help__sr">{{ loadingLabel() }}</span>
            <sol-skeleton variant="text" [count]="3" />
          </div>
        }

        @case ('error') {
          <sol-error-state
            [code]="errorCode()"
            [title]="errorTitle()"
            [message]="errorMessage()"
            [traceId]="errorTraceId()"
            data-testid="help-error"
          >
            <button type="button" class="sol-help__action" (click)="retry.emit()">{{ retryLabel() }}</button>
          </sol-error-state>
        }

        @case ('empty') {
          <sol-empty-state
            icon="document-text"
            titleKey="widgets.helpDrawer.empty.title"
            descriptionKey="widgets.helpDrawer.empty.description"
            data-testid="help-empty"
          >
            @if (supportUrl(); as support) {
              <a class="sol-help__action" [href]="support" target="_blank" rel="noopener noreferrer" data-testid="help-support">
                {{ supportLabel() }}
              </a>
            }
          </sol-empty-state>
        }

        @default {
          @if (tabs().length > 1) {
            <sol-tabs [tabs]="tabs()" [activeTab]="activeKind()" (tabChange)="selectedKind.set($event)" />
          }
          <div class="sol-help__content" data-testid="help-content">
            @for (resource of visibleResources(); track resource.id) {
              <article class="sol-help__resource">
                <h3 class="sol-help__resource-title">{{ resource.title }}</h3>
                @if (resource.description) {
                  <p class="sol-help__resource-description">{{ resource.description }}</p>
                }
                <a class="sol-help__action" [href]="resource.url" target="_blank" rel="noopener noreferrer">
                  {{ openLabel() }}
                </a>
              </article>
            }
          </div>
        }
      }

      <div drawerFooter class="sol-help__footer">
        @if (status() === 'ready' && supportUrl(); as support) {
          <a class="sol-help__action" [href]="support" target="_blank" rel="noopener noreferrer">{{ supportLabel() }}</a>
        }
        <button type="button" class="sol-help__action" data-testid="help-close" (click)="closed.emit()">
          {{ closeLabel() }}
        </button>
      </div>
    </sol-drawer>
  `,
  styles: `
    .sol-help__content {
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-md, 16px);
      padding-top: var(--sol-space-md, 16px);
    }

    /* Agrupación por espacio, no por borde: la separación la hace el aire. */
    .sol-help__resource {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: var(--sol-space-sm, 8px);
    }

    .sol-help__resource-title {
      margin: 0;
      color: var(--sol-color-text-primary, #111827);
      font-size: var(--sol-font-size-base, 1rem);
      font-weight: var(--sol-font-weight-bold, 600);
      line-height: 1.5;
    }

    .sol-help__resource-description {
      margin: 0;
      color: var(--sol-color-text-secondary, #6b7280);
      font-size: var(--sol-font-size-sm, 0.875rem);
      line-height: 1.5;
    }

    .sol-help__footer {
      display: flex;
      flex-direction: column;
      gap: var(--sol-space-sm, 8px);
    }

    .sol-help__action {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: var(--sol-size-component-md, 36px);
      padding: var(--sol-space-sm, 8px) var(--sol-space-md, 16px);
      border: var(--sol-border-width-default, 1px) solid var(--sol-border-color-default, #e5e7eb);
      border-radius: var(--sol-border-radius-md, 8px);
      background: var(--sol-bg-surface, #ffffff);
      color: var(--sol-color-text-primary, #111827);
      font: inherit;
      font-size: var(--sol-font-size-sm, 0.875rem);
      font-weight: 600;
      text-align: center;
      text-decoration: none;
      cursor: pointer;
    }

    .sol-help__action:focus-visible {
      outline: 2px solid var(--sol-color-primary, #2563eb);
      outline-offset: var(--sol-space-xs, 4px);
    }

    /* Bajo el breakpoint móvil el objetivo táctil manda (ley de Fitts, 44 px). */
    @media (max-width: 767px) {
      .sol-help__action {
        min-height: var(--sol-size-control-touch, 44px);
      }
    }

    /* Texto solo para lectores de pantalla: el esqueleto ya comunica la espera a la vista. */
    .sol-help__sr {
      position: absolute;
      width: 1px;
      height: 1px;
      margin: -1px;
      padding: 0;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
      border: 0;
    }
  `,
})
export class SolHelpDrawerComponent {
  private readonly i18n = inject(I18nService);

  readonly open = input<boolean>(false);
  /** Título del panel; sin valor, el genérico «Ayuda y soporte». */
  readonly title = input<string | null>(null);
  readonly status = input<HelpDrawerStatus>('empty');
  readonly resources = input<readonly HelpResource[]>([]);
  /** Canal de soporte (URL externa); sin valor no se ofrece el enlace. */
  readonly supportUrl = input<string | null>(null);
  /** Código HTTP del fallo de carga, para el estado de error. */
  readonly errorCode = input<number>(500);
  /** Código de seguimiento del fallo, si la respuesta lo trajo. */
  readonly errorTraceId = input<string | null>(null);

  readonly closed = output<void>();
  readonly retry = output<void>();

  /** Tipo elegido por la persona; `null` = el primero disponible. */
  protected readonly selectedKind = signal<string | null>(null);

  protected readonly loadingLabel = this.i18n.t('widgets.helpDrawer.loading');
  protected readonly retryLabel = this.i18n.t('widgets.helpDrawer.retry');
  protected readonly supportLabel = this.i18n.t('widgets.helpDrawer.support');
  protected readonly openLabel = this.i18n.t('widgets.helpDrawer.openInNewTab');
  protected readonly closeLabel = this.i18n.t('widgets.helpDrawer.close');
  protected readonly errorMessage = this.i18n.t('widgets.helpDrawer.errorMessage');

  protected readonly panelTitle = computed(() => {
    this.i18n.activeLang();
    const own = this.title()?.trim();
    return own ? own : this.i18n.translate('widgets.helpDrawer.title');
  });

  protected readonly errorTitle = computed(() => {
    this.i18n.activeLang();
    return this.i18n.translate(errorTitleKey(this.errorCode()));
  });

  /** Una pestaña por tipo, en el orden en que aparece cada tipo por primera vez. */
  protected readonly tabs = computed<SolTabItem[]>(() => {
    const byKind = new Map<string, SolTabItem>();
    for (const resource of this.resources()) {
      if (!byKind.has(resource.kind)) byKind.set(resource.kind, { id: resource.kind, label: resource.kindLabel });
    }
    return [...byKind.values()];
  });

  /** Nada arranca vacío: sin elección (o con una que ya no existe) vale el primer tipo. */
  protected readonly activeKind = computed(() => {
    const kinds = this.tabs().map(tab => tab.id);
    const selected = this.selectedKind();
    return selected !== null && kinds.includes(selected) ? selected : (kinds[0] ?? '');
  });

  protected readonly visibleResources = computed(() =>
    this.resources().filter(resource => resource.kind === this.activeKind()),
  );
}
