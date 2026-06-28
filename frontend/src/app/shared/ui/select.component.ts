/**
 * =====================================================================
 * sp-select — Dropdown buscable con selección única y múltiple
 * =====================================================================
 *
 * INPUTS
 *   options       SelectOption[]           Array de opciones. Cada ítem:
 *                                          { value: any, label: string, disabled?: boolean }
 *   multiple      boolean                  Modo multi-selección  (default: false)
 *   placeholder   string                   Texto cuando no hay selección
 *   label         string?                  Etiqueta sobre el control
 *   labelKey      string?                  Clave para leer el label en objetos genéricos
 *   valueKey      string?                  Clave para leer el value en objetos genéricos
 *   disabled      boolean                  Deshabilita el control (default: false)
 *
 * OUTPUTS
 *   change        EventEmitter<any|any[]>  Emite el value (o array) al cambiar
 *
 * FORMS
 *   Implementa ControlValueAccessor → funciona con [(ngModel)] y [formControl].
 *   Valor: any en modo single, any[] en modo multiple.
 *
 * TECLADO
 *   ArrowDown / ArrowUp  Navega opciones
 *   Enter                Selecciona la opción enfocada
 *   Esc                  Cierra el dropdown
 *
 * USO — single con ngModel
 *   <sp-select [options]="roles" placeholder="Selecciona un rol"
 *              [(ngModel)]="selectedRole" (change)="onRol($event)" />
 *
 * USO — múltiple con formControl
 *   <sp-select [options]="etiquetas" [multiple]="true"
 *              placeholder="Selecciona etiquetas"
 *              [formControl]="tagsCtrl" />
 *
 * USO — objetos genéricos
 *   <sp-select [options]="usuarios" labelKey="nombreCompleto" valueKey="id"
 *              placeholder="Asigna un usuario" [(ngModel)]="asignadoId" />
 * =====================================================================
 */

import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  ViewChild,
  computed,
  forwardRef,
  signal,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

export interface SelectOption {
  value: any;
  label: string;
  disabled?: boolean;
}

@Component({
  selector: 'sp-select',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => SelectComponent),
      multi: true,
    },
  ],
  template: `
    <div class="relative w-full">

      <!-- Label -->
      @if (label) {
        <span class="mb-1.5 block text-sm font-medium text-text">{{ label }}</span>
      }

      <!-- ── Trigger ─────────────────────────────────────────────────── -->
      <button
        type="button"
        [attr.aria-expanded]="isOpen()"
        aria-haspopup="listbox"
        [attr.aria-label]="label || placeholder"
        [disabled]="disabled()"
        (click)="toggleDropdown()"
        (keydown)="onTriggerKeydown($event)"
        [class]="triggerClasses"
      >
        <!-- Selected value(s) -->
        <span class="flex min-w-0 flex-1 flex-wrap items-center gap-1">

          <!-- Modo múltiple: chips -->
          @if (multiple && hasSelection()) {
            @for (opt of selectedOptions(); track opt.value) {
              <span
                class="inline-flex items-center gap-0.5 rounded-full bg-brand/15 px-2 py-0.5
                       text-xs font-medium text-brand"
              >
                {{ opt.label }}
                @if (!disabled()) {
                  <button
                    type="button"
                    [attr.aria-label]="'Quitar ' + opt.label"
                    (click)="removeChip($event, opt.value)"
                    class="ml-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full
                           text-brand/60 transition-colors hover:bg-brand/20 hover:text-brand
                           focus:outline-none focus-visible:ring-1 focus-visible:ring-brand"
                  >
                    <svg viewBox="0 0 10 10" class="h-2 w-2" aria-hidden="true">
                      <path d="M1 1l8 8M9 1l-8 8" stroke="currentColor" stroke-width="1.5"
                            stroke-linecap="round"/>
                    </svg>
                  </button>
                }
              </span>
            }
          }

          <!-- Modo simple: etiqueta seleccionada -->
          @if (!multiple && selectedSingleOption()) {
            <span class="truncate text-sm text-text">
              {{ selectedSingleOption()!.label }}
            </span>
          }

          <!-- Placeholder -->
          @if (!hasSelection()) {
            <span class="truncate text-sm text-muted">{{ placeholder }}</span>
          }
        </span>

        <!-- Botones de acción derechos -->
        <span class="ml-2 flex shrink-0 items-center gap-1">

          <!-- Clear -->
          @if (hasSelection() && !disabled()) {
            <span
              role="button"
              tabindex="0"
              aria-label="Limpiar selección"
              (click)="clearSelection($event)"
              (keydown.enter)="clearSelection($event)"
              (keydown.space)="clearSelection($event)"
              class="flex h-4 w-4 items-center justify-center rounded-full text-muted
                     transition-colors hover:bg-muted/20 hover:text-text
                     focus:outline-none focus-visible:ring-1 focus-visible:ring-brand"
            >
              <svg viewBox="0 0 10 10" class="h-2.5 w-2.5" aria-hidden="true">
                <path d="M1 1l8 8M9 1l-8 8" stroke="currentColor" stroke-width="1.5"
                      stroke-linecap="round"/>
              </svg>
            </span>
          }

          <!-- Chevron -->
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            class="h-4 w-4 text-muted transition-transform duration-150"
            [class.rotate-180]="isOpen()"
            aria-hidden="true"
          >
            <path fill-rule="evenodd" clip-rule="evenodd"
                  d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1
                     1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1
                     0-1.06Z"/>
          </svg>
        </span>
      </button>

      <!-- ── Dropdown panel ───────────────────────────────────────────── -->
      @if (isOpen()) {
        <div
          class="absolute z-50 mt-1 w-full rounded-lg border border-border bg-surface shadow-lg"
        >
          <!-- Buscador -->
          <div class="border-b border-border p-2">
            <input
              #searchInput
              type="text"
              role="searchbox"
              aria-autocomplete="list"
              [attr.aria-controls]="listboxId"
              [attr.aria-label]="'Buscar en ' + (label || placeholder)"
              placeholder="Buscar..."
              [value]="searchQuery()"
              (input)="onSearch($event)"
              (keydown)="onSearchKeydown($event)"
              class="h-8 w-full rounded-md border border-border bg-page px-3 text-sm text-text
                     placeholder:text-muted transition-colors
                     focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/40"
            />
          </div>

          <!-- Lista de opciones -->
          <ul
            [id]="listboxId"
            role="listbox"
            [attr.aria-multiselectable]="multiple"
            [attr.aria-label]="label || placeholder"
            class="max-h-60 overflow-y-auto py-1"
          >
            @for (option of filteredOptions(); track option.value; let i = $index) {
              <li
                role="option"
                [attr.aria-selected]="isSelected(option.value)"
                [attr.aria-disabled]="option.disabled ?? false"
                [id]="listboxId + '-opt-' + i"
                (click)="selectOption(option)"
                (mouseenter)="setFocusedIndex(i)"
                [class]="optionClasses(option, i)"
              >
                <!-- Checkmark en modo múltiple -->
                @if (multiple) {
                  <span
                    class="flex h-4 w-4 shrink-0 items-center justify-center rounded border
                           transition-colors"
                    [class]="isSelected(option.value)
                      ? 'border-brand bg-brand text-brand-fg'
                      : 'border-border bg-transparent'"
                    aria-hidden="true"
                  >
                    @if (isSelected(option.value)) {
                      <svg viewBox="0 0 10 10" class="h-2.5 w-2.5">
                        <path d="M1.5 5.5L4 8l4.5-5.5" stroke="currentColor"
                              stroke-width="1.5" fill="none" stroke-linecap="round"
                              stroke-linejoin="round"/>
                      </svg>
                    }
                  </span>
                }

                <span class="truncate">{{ option.label }}</span>

                <!-- Tick en modo single -->
                @if (!multiple && isSelected(option.value)) {
                  <svg viewBox="0 0 20 20" fill="currentColor"
                       class="ml-auto h-4 w-4 shrink-0 text-brand" aria-hidden="true">
                    <path fill-rule="evenodd" clip-rule="evenodd"
                          d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0
                             1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893
                             7.48-9.817a.75.75 0 0 1 1.05-.143Z"/>
                  </svg>
                }
              </li>
            } @empty {
              <li class="px-3 py-6 text-center text-sm text-muted">
                Sin resultados
              </li>
            }
          </ul>
        </div>
      }

    </div>
  `,
})
export class SelectComponent implements ControlValueAccessor, OnChanges {
  // ── Inputs ────────────────────────────────────────────────────────────
  @Input() options: SelectOption[] | Record<string, any>[] = [];
  @Input() multiple = false;
  @Input() placeholder = 'Selecciona una opción';
  @Input() label?: string;
  @Input() labelKey?: string;
  @Input() valueKey?: string;

  // ── Outputs ───────────────────────────────────────────────────────────
  @Output() change = new EventEmitter<any | any[]>();

  // ── View refs ─────────────────────────────────────────────────────────
  @ViewChild('searchInput') private searchInputRef?: ElementRef<HTMLInputElement>;

  // ── State signals ─────────────────────────────────────────────────────
  protected readonly isOpen = signal(false);
  protected readonly searchQuery = signal('');
  protected readonly selectedValues = signal<any[]>([]);
  protected readonly focusedIndex = signal(-1);
  protected readonly disabled = signal(false);

  private readonly normalizedOptions = signal<SelectOption[]>([]);

  // ── Derived (computed) ────────────────────────────────────────────────
  protected readonly filteredOptions = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    if (!q) return this.normalizedOptions();
    return this.normalizedOptions().filter(o =>
      o.label.toLowerCase().includes(q),
    );
  });

  protected readonly selectedSingleOption = computed<SelectOption | null>(() => {
    if (this.multiple) return null;
    const vals = this.selectedValues();
    if (!vals.length) return null;
    return this.normalizedOptions().find(o => o.value === vals[0]) ?? null;
  });

  protected readonly selectedOptions = computed<SelectOption[]>(() => {
    const set = new Set(this.selectedValues());
    return this.normalizedOptions().filter(o => set.has(o.value));
  });

  protected readonly hasSelection = computed(() => this.selectedValues().length > 0);

  // Unique ID per instance for aria linking
  protected readonly listboxId =
    'sp-select-listbox-' + Math.random().toString(36).slice(2, 8);

  // ── CVA callbacks ─────────────────────────────────────────────────────
  private onChange: (value: any) => void = () => {};
  protected onTouched: () => void = () => {};

  constructor(private readonly elRef: ElementRef) {}

  // ── Lifecycle ─────────────────────────────────────────────────────────
  ngOnChanges(changes: SimpleChanges): void {
    if (changes['options'] || changes['labelKey'] || changes['valueKey']) {
      this.normalizedOptions.set(this.buildOptions(this.options));
    }
  }

  private buildOptions(raw: any[]): SelectOption[] {
    return (raw ?? []).map(item => {
      if (
        typeof item === 'object' &&
        item !== null &&
        !('value' in item && 'label' in item)
      ) {
        return {
          value: this.valueKey ? item[this.valueKey] : item,
          label: this.labelKey ? String(item[this.labelKey]) : JSON.stringify(item),
          disabled: item['disabled'] ?? false,
        } satisfies SelectOption;
      }
      return item as SelectOption;
    });
  }

  // ── ControlValueAccessor ──────────────────────────────────────────────
  writeValue(value: any): void {
    if (this.multiple) {
      this.selectedValues.set(
        Array.isArray(value) ? value : value != null ? [value] : [],
      );
    } else {
      this.selectedValues.set(value != null ? [value] : []);
    }
  }

  registerOnChange(fn: (value: any) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }

  // ── Trigger classes (computed inline for purity) ──────────────────────
  protected get triggerClasses(): string {
    const base =
      'flex w-full items-center justify-between rounded-lg border ' +
      'bg-surface px-3 py-2 text-left text-sm transition-colors ' +
      'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ' +
      'disabled:cursor-not-allowed disabled:opacity-50';
    const border = this.isOpen()
      ? 'border-brand ring-2 ring-brand/40'
      : 'border-border hover:border-brand/50';
    const minH = this.multiple && this.hasSelection() ? 'min-h-10' : 'h-10';
    return `${base} ${border} ${minH}`;
  }

  // ── Option classes ────────────────────────────────────────────────────
  protected optionClasses(option: SelectOption, index: number): string {
    const base =
      'flex cursor-pointer select-none items-center gap-2 px-3 py-2 text-sm transition-colors';
    const focused =
      index === this.focusedIndex()
        ? 'bg-brand/10 text-brand'
        : 'text-text hover:bg-muted/10';
    const selected =
      this.isSelected(option.value) && index !== this.focusedIndex()
        ? 'font-medium'
        : '';
    const dis = option.disabled ? 'cursor-not-allowed opacity-50' : '';
    return [base, focused, selected, dis].filter(Boolean).join(' ');
  }

  // ── Dropdown control ──────────────────────────────────────────────────
  protected toggleDropdown(): void {
    if (this.disabled()) return;
    this.isOpen() ? this.close() : this.open();
  }

  private open(): void {
    this.isOpen.set(true);
    this.searchQuery.set('');
    this.focusedIndex.set(-1);
    // Defer focus until the element is in the DOM
    setTimeout(() => this.searchInputRef?.nativeElement.focus(), 0);
  }

  private close(): void {
    this.isOpen.set(false);
    this.searchQuery.set('');
    this.focusedIndex.set(-1);
    this.onTouched();
  }

  // ── Option selection ──────────────────────────────────────────────────
  protected selectOption(option: SelectOption): void {
    if (option.disabled) return;
    if (this.multiple) {
      const current = this.selectedValues();
      const next = current.includes(option.value)
        ? current.filter(v => v !== option.value)
        : [...current, option.value];
      this.selectedValues.set(next);
      this.emit(next);
    } else {
      this.selectedValues.set([option.value]);
      this.emit(option.value);
      this.close();
    }
  }

  protected removeChip(event: MouseEvent, value: any): void {
    event.stopPropagation();
    const next = this.selectedValues().filter(v => v !== value);
    this.selectedValues.set(next);
    this.emit(next);
  }

  protected clearSelection(event: Event): void {
    event.stopPropagation();
    this.selectedValues.set([]);
    this.emit(this.multiple ? [] : null);
  }

  private emit(value: any): void {
    this.onChange(value);
    this.change.emit(value);
  }

  // ── Search ────────────────────────────────────────────────────────────
  protected onSearch(event: Event): void {
    this.searchQuery.set((event.target as HTMLInputElement).value);
    this.focusedIndex.set(-1);
  }

  // ── Keyboard — search input ───────────────────────────────────────────
  protected onSearchKeydown(event: KeyboardEvent): void {
    const opts = this.filteredOptions();
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.focusedIndex.set(
          Math.min(this.focusedIndex() + 1, opts.length - 1),
        );
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.focusedIndex.set(Math.max(this.focusedIndex() - 1, 0));
        break;
      case 'Enter':
        event.preventDefault();
        {
          const idx = this.focusedIndex();
          if (idx >= 0 && idx < opts.length) {
            this.selectOption(opts[idx]);
          }
        }
        break;
      case 'Escape':
        event.preventDefault();
        this.close();
        break;
    }
  }

  // ── Keyboard — trigger button ─────────────────────────────────────────
  protected onTriggerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      this.toggleDropdown();
    } else if (event.key === 'Escape') {
      this.close();
    } else if (event.key === 'ArrowDown' && !this.isOpen()) {
      event.preventDefault();
      this.open();
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────
  protected isSelected(value: any): boolean {
    return this.selectedValues().includes(value);
  }

  protected setFocusedIndex(index: number): void {
    this.focusedIndex.set(index);
  }

  // ── Close on outside click ────────────────────────────────────────────
  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (
      this.isOpen() &&
      !this.elRef.nativeElement.contains(event.target)
    ) {
      this.close();
    }
  }
}
