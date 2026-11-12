import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ErrorDiagnosticsService } from '@shared/api/error-diagnostics.service';
import { I18nService } from '@shared/i18n';
import { errorMessageKey, errorTitleKey, SolErrorStateComponent } from '@shared/ui';

/**
 * Página única de error, parametrizada por `route.data['code']` (`401 | 403 | 500`).
 * Registrada tres veces en `app.routes.ts` (`no-autorizado`, `prohibido`, `error-servidor`), cada
 * una con su propio `data.code` — el mismo componente, sin recompilar nada por código.
 *
 * El mensaje mostrado es el `detail` REAL del último error que registró `error.interceptor.ts`
 * cuando su estado coincide con el código de esta ruta; si no coincide —navegación directa, F5,
 * marcador guardado sin pasar por el interceptor— cae al texto genérico del catálogo local y no
 * muestra código de seguimiento (no hay ninguno correlacionado con ESTA visita).
 */
@Component({
  standalone: true,
  selector: 'sol-error-page',
  imports: [RouterLink, SolErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="sol-error-page">
      <sol-error-state [code]="code" [title]="title" [message]="message()" [traceId]="traceId()">
        <a routerLink="/" class="sol-error-page__link">{{ backLabel() }}</a>
      </sol-error-state>
    </div>
  `,
  styles: [`
    .sol-error-page {
      position: relative;
      isolation: isolate;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      min-height: 100dvh;
      background-color: var(--sol-bg-page);
      padding: var(--sol-space-lg, 24px);
    }

    /* Misma textura de página fijada al viewport que not-found-page.component.ts. */
    .sol-error-page::before {
      content: '';
      position: fixed;
      inset: 0;
      z-index: -1;
      pointer-events: none;
      background-image: var(--sol-bg-page-texture, none);
      background-repeat: no-repeat;
      background-size: cover;
      background-position: center;
    }

    .sol-error-page__link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: var(--sol-size-button-height, 40px);
      padding: 0 var(--sol-space-lg, 24px);
      background-color: var(--sol-color-primary);
      color: var(--sol-color-primary-contrast, #fff);
      border-radius: var(--sol-button-radius, var(--sol-border-radius-md));
      box-shadow: var(--sol-button-shadow, none);
      font-family: var(--sol-font-family);
      font-weight: var(--sol-button-weight, 500);
      text-transform: var(--sol-button-transform, none);
      text-decoration: none;
    }

    .sol-error-page__link:hover {
      filter: brightness(1.1);
    }
  `],
})
export class ErrorPageComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly diagnostics = inject(ErrorDiagnosticsService);
  private readonly i18n = inject(I18nService);

  protected readonly code: number =
    (this.route.snapshot.data['code'] as number | undefined) ?? 500;

  protected readonly title: string = this.i18n.translate(errorTitleKey(this.code));

  private readonly localCatalogMessage: string = this.i18n.translate(errorMessageKey(this.code));

  protected readonly message = computed<string>(() => {
    const last = this.diagnostics.last();
    return last && last.status === this.code && last.detail ? last.detail : this.localCatalogMessage;
  });

  protected readonly traceId = computed<string | null>(() => {
    const last = this.diagnostics.last();
    return last && last.status === this.code ? last.traceId : null;
  });

  protected readonly backLabel = this.i18n.t('shared.errorState.backHome');
}
