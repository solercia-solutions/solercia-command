import type { AlertService } from '@shared/lib/alerts';
import type { I18nService } from '@shared/i18n';

/**
 * Copia un código de seguimiento al portapapeles y avisa el resultado. Verifica la Clipboard API
 * antes de usarla: sin ella (contexto no seguro, navegador antiguo) avisa que se copie a mano.
 */
export function copyTraceIdToClipboard(traceId: string, alert: AlertService, i18n: I18nService): void {
  const clipboard = navigator.clipboard;
  if (!clipboard?.writeText) {
    alert.showWarning(i18n.translate('shared.errorState.copyError'));
    return;
  }
  clipboard.writeText(traceId).then(
    () => alert.showSuccess(i18n.translate('shared.errorState.copied')),
    () => alert.showWarning(i18n.translate('shared.errorState.copyError')),
  );
}
