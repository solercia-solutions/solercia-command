/** @boki/ui — © 2026 Camilo Calderón. All rights reserved. */

import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

/**
 * Surface container with border + soft elevation, theme-aware.
 *
 * Selector: bk-card
 *
 * @input interactive — enables hover lift effect (translate + stronger shadow
 *   + stronger border). Use for clickable card surfaces.
 *
 * Example:
 *   <bk-card [interactive]="true">
 *     <h3>Title</h3>
 *     <p>Content</p>
 *   </bk-card>
 */
@Component({
  selector: 'bk-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div [class]="classes"><ng-content></ng-content></div>`,
})
export class CardComponent {
  @Input() interactive = false;

  get classes(): string {
    const base =
      'rounded-xl border border-border bg-surface p-5 shadow-sm ' +
      'transition-[transform,box-shadow,border-color] duration-200 ease-theme';
    const hover = this.interactive
      ? 'cursor-pointer hover:-translate-y-0.5 hover:shadow-md hover:border-border-strong'
      : '';
    return `${base} ${hover}`.trim();
  }
}
