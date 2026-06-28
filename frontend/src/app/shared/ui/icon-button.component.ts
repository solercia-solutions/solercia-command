import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

type IconName = 'edit' | 'delete' | 'link' | 'plus';

/**
 * Square icon-only button with a mandatory aria-label for accessibility.
 * Used for row actions in admin tables (edit, delete, manage relations).
 */
@Component({
  selector: 'bk-icon-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      [type]="type"
      [disabled]="disabled"
      [attr.aria-label]="ariaLabel"
      [class]="classes"
    >
      @switch (icon) {
        @case ('edit') {
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        }
        @case ('delete') {
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
          </svg>
        }
        @case ('link') {
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
          </svg>
        }
        @case ('plus') {
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        }
      }
    </button>
  `,
})
export class IconButtonComponent {
  @Input({ required: true }) icon: IconName = 'edit';
  @Input({ required: true }) ariaLabel = '';
  @Input() type: 'button' | 'submit' = 'button';
  @Input() tone: 'default' | 'danger' = 'default';
  @Input() disabled = false;

  get classes(): string {
    const base =
      'grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface ' +
      'transition-colors hover:bg-muted/10 focus:outline-none focus-visible:ring-2 ' +
      'focus-visible:ring-brand/50 disabled:opacity-50 disabled:cursor-not-allowed';
    const tone =
      this.tone === 'danger'
        ? 'text-danger hover:text-danger'
        : 'text-muted hover:text-text';
    return `${base} ${tone}`;
  }
}
