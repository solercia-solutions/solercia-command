/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

/** Supported visual variants for ButtonComponent. */
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

/**
 * Themed button with four visual variants. Light/dark handled by --sp-*
 * driven color tokens; no hard-coded color values.
 *
 * Selector: bk-button
 *
 * @input type     — native button type ('button' | 'submit'). Default: 'button'.
 * @input variant  — visual variant ('primary' | 'secondary' | 'ghost' | 'danger').
 * @input disabled — disables the button (opacity + pointer-events-none).
 * @input block    — stretches the button to full container width.
 * @input ariaLabel — sets aria-label for icon-only buttons.
 *
 * Example:
 *   <bk-button variant="primary" (click)="save()">Save</bk-button>
 *   <bk-button variant="danger" [disabled]="loading">Delete</bk-button>
 *   <bk-button variant="ghost" ariaLabel="Close">✕</bk-button>
 */
@Component({
  selector: 'bk-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      [type]="type"
      [disabled]="disabled"
      [attr.aria-label]="ariaLabel"
      [class]="classes"
    >
      <ng-content></ng-content>
    </button>
  `,
})
export class ButtonComponent {
  @Input() type: 'button' | 'submit' = 'button';
  @Input() variant: ButtonVariant = 'primary';
  @Input() disabled = false;
  @Input() block = false;
  @Input() ariaLabel?: string;

  get classes(): string {
    const base =
      'inline-flex items-center justify-center gap-2 h-10 rounded-lg px-4 text-sm font-semibold ' +
      'transition-all duration-150 ease-theme active:translate-y-px focus:outline-none ' +
      'focus-visible:ring-2 focus-visible:ring-ring/55 focus-visible:ring-offset-2 focus-visible:ring-offset-page ' +
      'disabled:opacity-50 disabled:pointer-events-none';
    const width = this.block ? 'w-full' : '';
    const variants: Record<ButtonVariant, string> = {
      primary:
        'bg-brand text-brand-fg shadow-sm hover:bg-brand-hover hover:shadow-md',
      secondary:
        'bg-surface text-text border border-border hover:bg-sunken hover:border-border-strong',
      ghost:
        'bg-transparent text-muted hover:bg-sunken hover:text-text',
      danger:
        'bg-danger text-white shadow-sm hover:brightness-110',
    };
    return `${base} ${width} ${variants[this.variant]}`.trim();
  }
}
