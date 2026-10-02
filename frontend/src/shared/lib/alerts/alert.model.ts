export type AlertType = 'success' | 'error' | 'warning' | 'info';

export type AlertPosition = 'top-right' | 'top-center' | 'bottom-right';

/** Única acción opcional de una alerta (por ejemplo «Ver detalle»). */
export interface AlertAction {
  /** Texto visible del botón de acción. */
  label: string;
  /** Se ejecuta cuando la persona pulsa la acción; la alerta se cierra después. */
  run: () => void;
}

export interface AlertItem {
  id: string;
  type: AlertType;
  message: string;
  duration: number;
  createdAt: number;
  action?: AlertAction;
}
