import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { debounceTime } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  SolButtonComponent,
  SolInputComponent,
  SolPageHeaderComponent,
  isRenderableTheme,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { TenantThemeService } from '@features/theme/tenant-theme.service';
import {
  DEFAULT_APPEARANCE,
  buildThemeFile,
  readAppearance,
} from '@features/theme/theme-builder';

const HEX_PATTERN = /^#[0-9a-fA-F]{6}$/;

/**
 * Editor de apariencia por organización (solo ADMIN — la entrada de menú
 * "Apariencia" se otorga únicamente al rol ADMIN; el backend rechaza con 403
 * cualquier PUT/DELETE de un no-admin).
 *
 * Edita un subconjunto del ThemeFile (ver `theme-builder.ts`) con vista
 * previa EN VIVO vía `TenantThemeService.preview()` (sin persistir). Guardar
 * hace PUT del ThemeFile completo; Restablecer hace DELETE (tema por
 * defecto). Al salir sin guardar se restaura el tema persistido.
 */
@Component({
  selector: 'sol-appearance-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolInputComponent,
    SolPageHeaderComponent,
  ],
  template: `
    <section class="mx-auto flex max-w-3xl flex-col gap-6">
      <sol-page-header [title]="text.title()" [subtitle]="text.subtitle()" />

      <form [formGroup]="form" class="flex flex-col gap-6" novalidate>
        <!-- Marca -->
        <fieldset
          class="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5"
        >
          <legend class="px-1 text-sm font-semibold text-text">
            {{ text.brandSection() }}
          </legend>
          <sol-input
            [label]="text.brandName()"
            [placeholder]="text.brandNamePlaceholder()"
            formControlName="brandName"
          ></sol-input>
          <sol-input
            [label]="text.logoUrl()"
            [placeholder]="text.logoUrlPlaceholder()"
            formControlName="logoUrl"
          ></sol-input>
          <p class="text-xs text-muted">{{ text.logoUrlHint() }}</p>
        </fieldset>

        <!-- Colores -->
        <fieldset
          class="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5"
        >
          <legend class="px-1 text-sm font-semibold text-text">
            {{ text.colorsSection() }}
          </legend>
          <div class="grid gap-4 sm:grid-cols-3">
            @for (field of colorFields; track field.control) {
              <div class="flex flex-col gap-1">
                <label
                  class="text-sm font-medium text-text"
                  [for]="'color-' + field.control"
                >
                  {{ text[field.labelKey]() }}
                </label>
                <div class="flex items-center gap-2">
                  <input
                    type="color"
                    [id]="'color-' + field.control"
                    [formControlName]="field.control"
                    class="h-9 w-9 shrink-0 cursor-pointer rounded-lg border border-border bg-surface p-0.5"
                    [attr.aria-label]="text[field.labelKey]()"
                  />
                  <input
                    type="text"
                    [formControlName]="field.control"
                    [attr.aria-label]="text[field.labelKey]() + ' (hex)'"
                    class="h-9 w-full rounded-lg border border-border bg-surface px-2
                           font-mono text-sm text-text focus:outline-none
                           focus-visible:ring-2 focus-visible:ring-ring/55"
                  />
                </div>
                @if (showHexError(field.control)) {
                  <p class="text-xs text-danger">{{ text.hexInvalid() }}</p>
                }
              </div>
            }
          </div>
        </fieldset>

        <!-- Forma y densidad -->
        <fieldset
          class="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5"
        >
          <legend class="px-1 text-sm font-semibold text-text">
            {{ text.shapeSection() }}
          </legend>
          <div class="grid gap-5 sm:grid-cols-3">
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-text" for="radius-input">
                {{ text.radius() }}
                <span class="font-mono text-xs text-muted">
                  ({{ form.controls.radius.value }}px)
                </span>
              </label>
              <input
                id="radius-input"
                type="range"
                min="0"
                max="24"
                step="2"
                formControlName="radius"
                class="accent-primary"
              />
            </div>
            <div class="flex flex-col gap-1">
              <span class="text-sm font-medium text-text">{{ text.density() }}</span>
              <div class="flex items-center gap-4" role="radiogroup"
                   [attr.aria-label]="text.density()">
                <label class="flex items-center gap-2 text-sm text-text">
                  <input
                    type="radio"
                    value="comfortable"
                    formControlName="density"
                    class="h-4 w-4 accent-primary"
                  />
                  {{ text.densityComfortable() }}
                </label>
                <label class="flex items-center gap-2 text-sm text-text">
                  <input
                    type="radio"
                    value="compact"
                    formControlName="density"
                    class="h-4 w-4 accent-primary"
                  />
                  {{ text.densityCompact() }}
                </label>
              </div>
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-sm font-medium text-text" for="border-input">
                {{ text.borderWidth() }}
                <span class="font-mono text-xs text-muted">
                  ({{ form.controls.borderWidth.value }}px)
                </span>
              </label>
              <input
                id="border-input"
                type="range"
                min="1"
                max="3"
                step="1"
                formControlName="borderWidth"
                class="accent-primary"
              />
            </div>
          </div>
        </fieldset>

        <!-- Sidebar y header -->
        <fieldset
          class="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5"
        >
          <legend class="px-1 text-sm font-semibold text-text">
            {{ text.chromeSection() }}
          </legend>
          <label class="flex items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              formControlName="customChrome"
              class="h-4 w-4 rounded border-border accent-primary"
            />
            {{ text.customChrome() }}
          </label>
          <p class="text-xs text-muted">{{ text.customChromeHint() }}</p>
          @if (form.controls.customChrome.value) {
            <div class="grid gap-4 sm:grid-cols-3">
              @for (field of chromeFields; track field.control) {
                <div class="flex flex-col gap-1">
                  <label
                    class="text-sm font-medium text-text"
                    [for]="'color-' + field.control"
                  >
                    {{ text[field.labelKey]() }}
                  </label>
                  <div class="flex items-center gap-2">
                    <input
                      type="color"
                      [id]="'color-' + field.control"
                      [formControlName]="field.control"
                      class="h-9 w-9 shrink-0 cursor-pointer rounded-lg border border-border bg-surface p-0.5"
                      [attr.aria-label]="text[field.labelKey]()"
                    />
                    <input
                      type="text"
                      [formControlName]="field.control"
                      [attr.aria-label]="text[field.labelKey]() + ' (hex)'"
                      class="h-9 w-full rounded-lg border border-border bg-surface px-2
                             font-mono text-sm text-text focus:outline-none
                             focus-visible:ring-2 focus-visible:ring-ring/55"
                    />
                  </div>
                  @if (showHexError(field.control)) {
                    <p class="text-xs text-danger">{{ text.hexInvalid() }}</p>
                  }
                </div>
              }
            </div>
          }
        </fieldset>

        @if (error()) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
          >
            {{ error() }}
          </div>
        }
        @if (savedMessage()) {
          <div
            role="status"
            class="rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success"
          >
            {{ savedMessage() }}
          </div>
        }

        <div class="flex flex-wrap items-center justify-end gap-2">
          <sol-button
            type="button"
            variant="ghost"
            [disabled]="saving()"
            (click)="onReset()"
            [ariaLabel]="text.resetAria()"
          >
            {{ text.reset() }}
          </sol-button>
          <sol-button
            type="button"
            variant="primary"
            [disabled]="saving() || form.invalid"
            (click)="onSave()"
            [ariaLabel]="text.saveAria()"
          >
            {{ saving() ? text.saving() : text.save() }}
          </sol-button>
        </div>
      </form>
    </section>
  `,
})
export class AppearancePageComponent implements OnInit, OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly i18n = inject(I18nService);
  private readonly tenantTheme = inject(TenantThemeService);

  protected readonly text = {
    title: this.i18n.t('appearance.title'),
    subtitle: this.i18n.t('appearance.subtitle'),
    brandSection: this.i18n.t('appearance.sections.brand'),
    brandName: this.i18n.t('appearance.fields.brandName'),
    brandNamePlaceholder: this.i18n.t('appearance.fields.brandNamePlaceholder'),
    logoUrl: this.i18n.t('appearance.fields.logoUrl'),
    logoUrlPlaceholder: this.i18n.t('appearance.fields.logoUrlPlaceholder'),
    logoUrlHint: this.i18n.t('appearance.fields.logoUrlHint'),
    colorsSection: this.i18n.t('appearance.sections.colors'),
    primaryColor: this.i18n.t('appearance.fields.primaryColor'),
    accentColor: this.i18n.t('appearance.fields.accentColor'),
    pageBg: this.i18n.t('appearance.fields.pageBg'),
    shapeSection: this.i18n.t('appearance.sections.shape'),
    radius: this.i18n.t('appearance.fields.radius'),
    density: this.i18n.t('appearance.fields.density'),
    densityCompact: this.i18n.t('appearance.fields.densityCompact'),
    densityComfortable: this.i18n.t('appearance.fields.densityComfortable'),
    borderWidth: this.i18n.t('appearance.fields.borderWidth'),
    chromeSection: this.i18n.t('appearance.sections.chrome'),
    customChrome: this.i18n.t('appearance.fields.customChrome'),
    customChromeHint: this.i18n.t('appearance.fields.customChromeHint'),
    sidebarBg: this.i18n.t('appearance.fields.sidebarBg'),
    sidebarText: this.i18n.t('appearance.fields.sidebarText'),
    headerBg: this.i18n.t('appearance.fields.headerBg'),
    hexInvalid: this.i18n.t('appearance.errors.hexInvalid'),
    save: this.i18n.t('appearance.actions.save'),
    saveAria: this.i18n.t('appearance.actions.saveAria'),
    saving: this.i18n.t('appearance.actions.saving'),
    reset: this.i18n.t('appearance.actions.reset'),
    resetAria: this.i18n.t('appearance.actions.resetAria'),
  } as const;

  /** Campos de color del bloque principal (control ↔ clave i18n). */
  protected readonly colorFields = [
    { control: 'primaryColor', labelKey: 'primaryColor' },
    { control: 'accentColor', labelKey: 'accentColor' },
    { control: 'pageBg', labelKey: 'pageBg' },
  ] as const;

  /** Campos de color de sidebar/header. */
  protected readonly chromeFields = [
    { control: 'sidebarBg', labelKey: 'sidebarBg' },
    { control: 'sidebarText', labelKey: 'sidebarText' },
    { control: 'headerBg', labelKey: 'headerBg' },
  ] as const;

  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly savedMessage = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    brandName: [DEFAULT_APPEARANCE.brandName],
    logoUrl: [DEFAULT_APPEARANCE.logoUrl],
    primaryColor: [
      DEFAULT_APPEARANCE.primaryColor,
      [Validators.required, Validators.pattern(HEX_PATTERN)],
    ],
    accentColor: [
      DEFAULT_APPEARANCE.accentColor,
      [Validators.required, Validators.pattern(HEX_PATTERN)],
    ],
    pageBg: [
      DEFAULT_APPEARANCE.pageBg,
      [Validators.required, Validators.pattern(HEX_PATTERN)],
    ],
    radius: [DEFAULT_APPEARANCE.radius],
    density: [DEFAULT_APPEARANCE.density],
    borderWidth: [DEFAULT_APPEARANCE.borderWidth],
    customChrome: [DEFAULT_APPEARANCE.customChrome],
    sidebarBg: [
      DEFAULT_APPEARANCE.sidebarBg,
      [Validators.required, Validators.pattern(HEX_PATTERN)],
    ],
    sidebarText: [
      DEFAULT_APPEARANCE.sidebarText,
      [Validators.required, Validators.pattern(HEX_PATTERN)],
    ],
    headerBg: [
      DEFAULT_APPEARANCE.headerBg,
      [Validators.required, Validators.pattern(HEX_PATTERN)],
    ],
  });

  constructor() {
    // Vista previa EN VIVO: cada cambio válido del formulario aplica el tema
    // candidato SIN persistir (debounce corto para el arrastre de sliders).
    this.form.valueChanges
      .pipe(debounceTime(150), takeUntilDestroyed())
      .subscribe(() => this.previewCurrent());
  }

  ngOnInit(): void {
    this.form.patchValue(readAppearance(this.tenantTheme.saved()), {
      emitEvent: false,
    });
  }

  /** Al salir sin guardar, restaura el tema persistido de la organización. */
  ngOnDestroy(): void {
    this.tenantTheme.applySaved();
  }

  protected showHexError(
    control:
      | 'primaryColor'
      | 'accentColor'
      | 'pageBg'
      | 'sidebarBg'
      | 'sidebarText'
      | 'headerBg',
  ): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected onSave(): void {
    this.error.set(null);
    this.savedMessage.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const built = buildThemeFile(this.form.getRawValue());
    if (!isRenderableTheme(built)) {
      this.error.set(this.i18n.translate('appearance.errors.notRenderable'));
      return;
    }
    this.saving.set(true);
    this.tenantTheme.save(built).subscribe({
      next: () => {
        this.saving.set(false);
        this.savedMessage.set(this.i18n.translate('appearance.messages.saved'));
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.error.set(this.messageFor(err));
      },
    });
  }

  protected onReset(): void {
    this.error.set(null);
    this.savedMessage.set(null);
    this.saving.set(true);
    this.tenantTheme.reset().subscribe({
      next: () => {
        this.saving.set(false);
        this.form.reset({ ...DEFAULT_APPEARANCE }, { emitEvent: false });
        this.savedMessage.set(this.i18n.translate('appearance.messages.reset'));
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.error.set(this.messageFor(err));
      },
    });
  }

  private previewCurrent(): void {
    if (this.form.invalid) {
      return;
    }
    const built = buildThemeFile(this.form.getRawValue());
    if (isRenderableTheme(built)) {
      this.tenantTheme.preview(built);
    }
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return this.i18n.translate('appearance.errors.network');
    }
    if (err.status === 403) {
      return this.i18n.translate('appearance.errors.forbidden');
    }
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    return this.i18n.translate('appearance.errors.saveFailed');
  }
}
