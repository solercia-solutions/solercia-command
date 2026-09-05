import { Injectable, signal } from '@angular/core';

export type ToastKind = 'success' | 'error' | 'warning' | 'info';

export interface ToastAction {
  /** Visible label of the single optional action button. */
  label: string;
  /** Runs when the person presses the action; the toast closes afterwards. */
  run: () => void;
}

export interface ToastOptions {
  /** Auto-close delay in ms. `0` keeps the toast until dismissed. Default 6000. */
  durationMs?: number;
  action?: ToastAction;
}

export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
  durationMs: number;
  action: ToastAction | null;
}

/** Default auto-close delay (UX spec: 6 s, pausable on hover). */
const DEFAULT_DURATION_MS = 6000;

/**
 * Minimal transient-feedback store: a signal with the visible toasts plus the
 * timers that close them. Pages call `success/error/warning/info`; the host
 * component (`sol-toast-host`, mounted once in the app shell) renders the
 * stack and pauses the timer while the pointer is over a toast.
 *
 * Lives in `shared/lib` so no page owns the toast logic (UX spec).
 */
@Injectable({ providedIn: 'root' })
export class ToastStore {
  private nextId = 1;
  private readonly timers = new Map<
    number,
    { handle: ReturnType<typeof setTimeout> | null; remainingMs: number; startedAt: number }
  >();

  readonly toasts = signal<readonly Toast[]>([]);

  show(kind: ToastKind, text: string, options: ToastOptions = {}): number {
    const toast: Toast = {
      id: this.nextId++,
      kind,
      text,
      durationMs: options.durationMs ?? DEFAULT_DURATION_MS,
      action: options.action ?? null,
    };
    this.toasts.update((list) => [...list, toast]);
    if (toast.durationMs > 0) {
      this.timers.set(toast.id, { handle: null, remainingMs: toast.durationMs, startedAt: 0 });
      this.resume(toast.id);
    }
    return toast.id;
  }

  success(text: string, options?: ToastOptions): number {
    return this.show('success', text, options);
  }

  error(text: string, options?: ToastOptions): number {
    return this.show('error', text, options);
  }

  warning(text: string, options?: ToastOptions): number {
    return this.show('warning', text, options);
  }

  info(text: string, options?: ToastOptions): number {
    return this.show('info', text, options);
  }

  dismiss(id: number): void {
    const timer = this.timers.get(id);
    if (timer?.handle !== null && timer?.handle !== undefined) {
      clearTimeout(timer.handle);
    }
    this.timers.delete(id);
    this.toasts.update((list) => list.filter((toast) => toast.id !== id));
  }

  /** Stops the auto-close countdown (pointer over the toast). */
  pause(id: number): void {
    const timer = this.timers.get(id);
    if (!timer || timer.handle === null) {
      return;
    }
    clearTimeout(timer.handle);
    timer.handle = null;
    timer.remainingMs = Math.max(0, timer.remainingMs - (Date.now() - timer.startedAt));
  }

  /** Restarts the countdown with whatever time was left. */
  resume(id: number): void {
    const timer = this.timers.get(id);
    if (!timer || timer.handle !== null) {
      return;
    }
    timer.startedAt = Date.now();
    timer.handle = setTimeout(() => this.dismiss(id), timer.remainingMs);
  }

  /** Runs the toast action (if any) and closes the toast. */
  act(id: number): void {
    const toast = this.toasts().find((item) => item.id === id);
    this.dismiss(id);
    toast?.action?.run();
  }
}
