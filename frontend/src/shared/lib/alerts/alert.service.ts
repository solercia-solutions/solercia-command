import { Injectable, signal } from '@angular/core';
import { AlertAction, AlertItem, AlertType } from './alert.model';

const DEFAULT_DURATION = 5000;
let nextId = 0;

@Injectable({ providedIn: 'root' })
export class AlertService {
  private _alerts = signal<AlertItem[]>([]);
  alerts = this._alerts.asReadonly();

  showSuccess(message: string, duration = DEFAULT_DURATION, action?: AlertAction): void {
    this.add('success', message, duration, action);
  }

  showError(message: string, duration = DEFAULT_DURATION, action?: AlertAction): void {
    this.add('error', message, duration, action);
  }

  showWarning(message: string, duration = DEFAULT_DURATION, action?: AlertAction): void {
    this.add('warning', message, duration, action);
  }

  showInfo(message: string, duration = DEFAULT_DURATION, action?: AlertAction): void {
    this.add('info', message, duration, action);
  }

  dismiss(id: string): void {
    this._alerts.update(list => list.filter(a => a.id !== id));
  }

  dismissAll(): void {
    this._alerts.set([]);
  }

  /** Ejecuta la acción de la alerta (si tiene) y la cierra. */
  act(id: string): void {
    const item = this._alerts().find(a => a.id === id);
    this.dismiss(id);
    item?.action?.run();
  }

  private add(type: AlertType, message: string, duration: number, action?: AlertAction): void {
    const id = `alert-${++nextId}`;
    const item: AlertItem = { id, type, message, duration, createdAt: Date.now(), action };
    this._alerts.update(list => [...list, item]);

    if (duration > 0) {
      setTimeout(() => this.dismiss(id), duration);
    }
  }
}
