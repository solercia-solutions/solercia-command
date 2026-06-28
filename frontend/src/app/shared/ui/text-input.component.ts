import {
  ChangeDetectionStrategy,
  Component,
  Input,
  forwardRef,
  signal,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

/**
 * Themed text input that integrates with Angular Reactive Forms through
 * ControlValueAccessor, so it can be used with formControlName.
 */
@Component({
  selector: 'sp-text-input',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => TextInputComponent),
      multi: true,
    },
  ],
  template: `
    <label class="block">
      @if (label) {
        <span class="mb-1.5 block text-sm font-medium text-text">{{
          label
        }}</span>
      }
      <input
        [type]="type"
        [value]="value()"
        [placeholder]="placeholder"
        [disabled]="disabled()"
        [attr.autocomplete]="autocomplete"
        [attr.aria-label]="label || placeholder"
        (input)="onInput($event)"
        (blur)="onTouched()"
        class="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text
               placeholder:text-muted transition-colors
               focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40
               disabled:cursor-not-allowed disabled:opacity-50"
      />
    </label>
  `,
})
export class TextInputComponent implements ControlValueAccessor {
  @Input() label?: string;
  @Input() type = 'text';
  @Input() placeholder = '';
  @Input() autocomplete?: string;

  protected readonly value = signal('');
  protected readonly disabled = signal(false);

  private onChange: (value: string) => void = () => {};
  protected onTouched: () => void = () => {};

  writeValue(value: string | null): void {
    this.value.set(value ?? '');
  }

  registerOnChange(fn: (value: string) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }

  protected onInput(event: Event): void {
    const next = (event.target as HTMLInputElement).value;
    this.value.set(next);
    this.onChange(next);
  }
}
