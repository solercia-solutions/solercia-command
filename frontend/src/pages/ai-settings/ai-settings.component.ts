import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolInputComponent,
  SolSelectComponent,
  SolSelectOption,
  SolSkeletonComponent,
  SolToggleComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { readApiError } from '@shared/lib/api-error';
import { formatBogotaDateTime } from '@shared/lib/utils/bogota-date.util';
import { ActiveRoleService } from '@features/organizations/active-role.service';
import { AiSettingsService } from '@entities/ai-settings/ai-settings.service';
import {
  AiConnectionTestResult,
  AiPreset,
  AiReasoningEffort,
  AiSettings,
  AiSettingsUpdate,
} from '@entities/ai-settings/ai-settings.model';

type PresetGroup = 'local' | 'external' | 'custom';
type TestState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'done'; result: AiConnectionTestResult }
  | { kind: 'failed'; message: string };

const REASONING: readonly AiReasoningEffort[] = ['none', 'low', 'medium', 'high'];

/**
 * `/settings/ai` «Inteligencia artificial» (C06). Muestra el proveedor efectivo y, para admin,
 * lo cambia como una llanta: el preset precarga URL y modelos (el usuario no escribe lo que el
 * sistema ya sabe), la llave se conserva si se deja vacía y las opciones finas van plegadas.
 * Un proveedor externo saca el contenido del correo de la máquina: se avisa antes de guardar.
 */
@Component({
  selector: 'sol-ai-settings-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolInputComponent,
    SolSelectComponent,
    SolSkeletonComponent,
    SolToggleComponent,
  ],
  styleUrls: ['../page-layout.scss', './ai-settings.component.scss'],
  template: `
    <section class="pg-page">
      <header class="pg-header">
        <div class="pg-header__text">
          <h1 class="pg-title sol-display">{{ t('aiSettings.title') }}</h1>
          <p class="pg-muted">{{ t('aiSettings.subtitle') }}</p>
        </div>
      </header>

      @if (loading()) {
        <div class="pg-section" role="status" aria-live="polite" [attr.aria-label]="t('aiSettings.loading')">
          <sol-skeleton variant="card" [count]="1" />
          <sol-skeleton variant="row" [count]="4" />
        </div>
      } @else if (loadError(); as message) {
        <div class="pg-alert" role="alert">
          <span>{{ message }}</span>
          @if (canRetry()) {
            <sol-button type="button" variant="secondary" size="sm" (clicked)="load()">
              {{ t('aiSettings.retry') }}
            </sol-button>
          }
        </div>
      } @else if (settings(); as current) {
        <!-- Proveedor activo -->
        <sol-card>
          <div class="ai-active">
            <div class="ai-active__head">
              <p class="pg-small">{{ t('aiSettings.active.label') }}</p>
              <div class="pg-row ai-wrap">
                <h2 class="pg-subtitle">{{ current.preset_label }}</h2>
                <sol-badge [variant]="current.locality === 'local' ? 'success' : 'warning'" size="sm">
                  {{ t('aiSettings.locality.' + current.locality) }}
                </sol-badge>
                @if (!current.enabled) {
                  <sol-badge variant="neutral" size="sm">{{ t('aiSettings.active.disabled') }}</sol-badge>
                }
              </div>
            </div>
            <dl class="ai-facts">
              <div>
                <dt>{{ t('aiSettings.fields.chatModel') }}</dt>
                <dd class="pg-mono">{{ current.chat_model }}</dd>
              </div>
              <div>
                <dt>{{ t('aiSettings.fields.embeddingModel') }}</dt>
                <dd class="pg-mono">{{ current.embedding_model || t('aiSettings.active.noEmbeddings') }}</dd>
              </div>
              <div>
                <dt>{{ t('aiSettings.fields.apiKey') }}</dt>
                <dd>
                  @if (current.has_api_key) {
                    {{ t('aiSettings.key.stored', { last4: current.api_key_last4 ?? '····' }) }}
                  } @else {
                    {{ t('aiSettings.key.none') }}
                  }
                </dd>
              </div>
              <div>
                <dt>{{ t('aiSettings.active.source') }}</dt>
                <dd>
                  {{ t('aiSettings.source.' + current.source) }}
                  @if (current.updated_at) {
                    <span class="pg-small"> · {{ formatDate(current.updated_at) }}</span>
                  }
                </dd>
              </div>
            </dl>
          </div>
        </sol-card>

        @if (!isAdmin()) {
          <p class="ai-note" role="note">{{ t('aiSettings.readOnly') }}</p>
        } @else {
          <form class="pg-section ai-form" [formGroup]="form" (ngSubmit)="save()" novalidate>
            <!-- Selector de proveedor -->
            <sol-card>
              <h2 class="pg-subtitle">{{ t('aiSettings.presets.title') }}</h2>
              <p class="pg-muted">{{ t('aiSettings.presets.hint') }}</p>
              @for (group of groups(); track group.key) {
                <div class="ai-group">
                  <h3 class="ai-group__title">{{ t('aiSettings.presets.groups.' + group.key) }}</h3>
                  <div class="ai-presets" role="radiogroup" [attr.aria-label]="t('aiSettings.presets.groups.' + group.key)">
                    @for (preset of group.presets; track preset.key) {
                      <button
                        type="button"
                        role="radio"
                        class="ai-preset"
                        [class.ai-preset--active]="preset.key === selectedKey()"
                        [attr.aria-checked]="preset.key === selectedKey()"
                        (click)="selectPreset(preset)"
                      >
                        <span class="ai-preset__label">{{ preset.label }}</span>
                        <span class="ai-preset__meta pg-mono">{{ preset.chat_model || t('aiSettings.presets.yourModel') }}</span>
                        @if (preset.key === current.preset && current.source === 'organization') {
                          <span class="ai-preset__tag">{{ t('aiSettings.presets.saved') }}</span>
                        }
                      </button>
                    }
                  </div>
                </div>
              }
            </sol-card>

            @if (selected(); as preset) {
              @if (preset.locality === 'external') {
                <div class="ai-warning" role="alert">
                  <strong>{{ t('aiSettings.external.title') }}</strong>
                  <span>{{ t('aiSettings.external.message', { provider: preset.label }) }}</span>
                </div>
              }

              <sol-card>
                <div class="ai-fields">
                  <sol-input
                    [label]="t('aiSettings.fields.baseUrl')"
                    [placeholder]="t('aiSettings.fields.baseUrlPlaceholder')"
                    [error]="fieldError('base_url')"
                    formControlName="base_url"
                  />
                  <p class="pg-small ai-hint">
                    {{ preset.base_url_editable ? t('aiSettings.fields.baseUrlEditable.' + preset.locality) : t('aiSettings.fields.baseUrlFixed') }}
                  </p>
                  <sol-input
                    [label]="t('aiSettings.fields.chatModel')"
                    [error]="fieldError('chat_model')"
                    formControlName="chat_model"
                  />
                  <sol-input
                    [label]="t('aiSettings.fields.embeddingModel')"
                    [placeholder]="t('aiSettings.fields.embeddingPlaceholder')"
                    formControlName="embedding_model"
                  />

                  <!-- Llave: vacío = conservar -->
                  <div class="ai-key">
                    @if (removeKey()) {
                      <p class="ai-key__removed" role="status">
                        {{ t('aiSettings.key.willRemove') }}
                        <sol-button type="button" variant="ghost" size="sm" (clicked)="removeKey.set(false)">
                          {{ t('aiSettings.key.undo') }}
                        </sol-button>
                      </p>
                    } @else {
                      <sol-input
                        type="password"
                        autocomplete="off"
                        [label]="t('aiSettings.fields.apiKey')"
                        [placeholder]="keyPlaceholder()"
                        [error]="fieldError('api_key')"
                        formControlName="api_key"
                      />
                      <p class="pg-small ai-hint">{{ keyHint() }}</p>
                      @if (keyKept()) {
                        <sol-button type="button" variant="ghost" size="sm" (clicked)="removeKey.set(true)">
                          {{ t('aiSettings.key.remove') }}
                        </sol-button>
                      }
                    }
                  </div>

                  <sol-toggle [label]="t('aiSettings.fields.enabled')" formControlName="enabled" />
                </div>

                <details class="ai-advanced">
                  <summary>{{ t('aiSettings.advanced.title') }}</summary>
                  <p class="pg-small">{{ t('aiSettings.advanced.hint') }}</p>
                  <div class="ai-advanced__grid">
                    <sol-input
                      type="number"
                      [label]="t('aiSettings.advanced.timeout')"
                      [error]="fieldError('timeout_seconds')"
                      formControlName="timeout_seconds"
                    />
                    <sol-input
                      type="number"
                      [label]="t('aiSettings.advanced.maxTokens')"
                      [error]="fieldError('max_tokens')"
                      formControlName="max_tokens"
                    />
                    <sol-input
                      type="number"
                      [label]="t('aiSettings.advanced.temperature')"
                      [error]="fieldError('temperature')"
                      formControlName="temperature"
                    />
                    <sol-input
                      type="number"
                      [label]="t('aiSettings.advanced.numCtx')"
                      [placeholder]="t('aiSettings.advanced.numCtxPlaceholder')"
                      [error]="fieldError('num_ctx')"
                      formControlName="num_ctx"
                    />
                    <sol-select
                      [label]="t('aiSettings.advanced.reasoning')"
                      [options]="reasoningOptions()"
                      [searchable]="false"
                      formControlName="reasoning_effort"
                    />
                  </div>
                </details>
              </sol-card>

              <!-- Resultado de la prueba -->
              @switch (test().kind) {
                @case ('running') {
                  <p class="ai-test" role="status">{{ t('aiSettings.test.running') }}</p>
                }
                @case ('done') {
                  @if (testResult(); as result) {
                    @if (result.ok) {
                      <div class="ai-test ai-test--ok" role="status">
                        <strong>{{ t('aiSettings.test.ok') }}</strong>
                        <span>
                          {{ t('aiSettings.test.chat', { model: result.chat_model, ms: result.chat_latency_ms ?? '—' }) }}
                        </span>
                        @if (result.embedding_model) {
                          <span>
                            {{ t('aiSettings.test.embeddings', { model: result.embedding_model, ms: result.embedding_latency_ms ?? '—', dims: result.embedding_dimensions ?? '—' }) }}
                          </span>
                        } @else {
                          <span>{{ t('aiSettings.test.noEmbeddings') }}</span>
                        }
                      </div>
                    } @else {
                      <div class="ai-test ai-test--error" role="alert">
                        <strong>{{ t('aiSettings.test.failed.' + (result.error?.stage ?? 'chat')) }}</strong>
                        <span>{{ result.error?.detail }}</span>
                        <span class="pg-mono">{{ t('aiSettings.test.code', { code: result.error?.code ?? '—' }) }}</span>
                      </div>
                    }
                  }
                }
                @case ('failed') {
                  <div class="ai-test ai-test--error" role="alert">{{ testMessage() }}</div>
                }
              }

              @if (saveError(); as message) {
                <div class="pg-alert" role="alert"><span>{{ message }}</span></div>
              }

              <div class="ai-actions">
                <sol-button type="button" variant="secondary" [loading]="test().kind === 'running'" (clicked)="runTest()">
                  {{ t('aiSettings.actions.test') }}
                </sol-button>
                @if (dirty()) {
                  <sol-button type="button" variant="ghost" (clicked)="discard()">
                    {{ t('aiSettings.actions.discard') }}
                  </sol-button>
                }
                <sol-button type="submit" variant="primary" [disabled]="!canSave() || saving()" [loading]="saving()">
                  {{ t('aiSettings.actions.save') }}
                </sol-button>
              </div>
              @if (!canSave()) {
                <p class="pg-small ai-actions__hint">{{ t('aiSettings.actions.noChanges') }}</p>
              } @else if (!dirty()) {
                <p class="pg-small ai-actions__hint">{{ t('aiSettings.actions.notSavedYet') }}</p>
              }
            }
          </form>
        }
      }
    </section>
  `,
})
export class AiSettingsComponent implements OnInit {
  private readonly service = inject(AiSettingsService);
  private readonly i18n = inject(I18nService);
  private readonly alerts = inject(AlertService);
  private readonly roles = inject(ActiveRoleService);

  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly canRetry = signal(true);
  protected readonly settings = signal<AiSettings | null>(null);
  protected readonly presets = signal<AiPreset[]>([]);
  protected readonly selectedKey = signal<string>('');
  protected readonly removeKey = signal(false);
  protected readonly saving = signal(false);
  protected readonly saveError = signal<string | null>(null);
  protected readonly submitted = signal(false);
  protected readonly test = signal<TestState>({ kind: 'idle' });
  private readonly serverFieldErrors = signal<Record<string, string>>({});

  protected readonly isAdmin = this.roles.isAdmin;

  protected readonly form = new FormGroup({
    base_url: new FormControl('', { nonNullable: true }),
    chat_model: new FormControl('', { nonNullable: true }),
    embedding_model: new FormControl('', { nonNullable: true }),
    api_key: new FormControl('', { nonNullable: true }),
    enabled: new FormControl(true, { nonNullable: true }),
    timeout_seconds: new FormControl('60', { nonNullable: true }),
    max_tokens: new FormControl('1024', { nonNullable: true }),
    temperature: new FormControl('0', { nonNullable: true }),
    num_ctx: new FormControl('', { nonNullable: true }),
    reasoning_effort: new FormControl<string>('none', { nonNullable: true }),
  });
  private readonly formValue = toSignal(this.form.valueChanges, { initialValue: this.form.getRawValue() });

  protected readonly selected = computed(
    () => this.presets().find((p) => p.key === this.selectedKey()) ?? null,
  );

  protected readonly groups = computed(() => {
    const groups: { key: PresetGroup; presets: AiPreset[] }[] = [
      { key: 'local', presets: [] },
      { key: 'external', presets: [] },
      { key: 'custom', presets: [] },
    ];
    for (const preset of this.presets()) {
      const key: PresetGroup =
        preset.key === 'custom' ? 'custom' : preset.locality === 'local' ? 'local' : 'external';
      groups.find((g) => g.key === key)?.presets.push(preset);
    }
    return groups.filter((g) => g.presets.length > 0);
  });

  protected readonly reasoningOptions = computed<SolSelectOption[]>(() => {
    this.i18n.activeLang();
    return REASONING.map((value) => ({
      value,
      label: this.i18n.translate(`aiSettings.advanced.reasoningOptions.${value}`),
    }));
  });

  /** La llave guardada solo se reutiliza con el mismo preset (el backend exige la misma URL). */
  protected readonly keyKept = computed(() => {
    const current = this.settings();
    return (
      !!current?.has_api_key &&
      current.source === 'organization' &&
      current.preset === this.selectedKey() &&
      !this.removeKey()
    );
  });

  protected readonly keyPlaceholder = computed(() => {
    const current = this.settings();
    return this.keyKept()
      ? this.i18n.translate('aiSettings.key.keepPlaceholder', { last4: current?.api_key_last4 ?? '····' })
      : this.i18n.translate('aiSettings.key.placeholder');
  });

  protected readonly keyHint = computed(() => {
    const preset = this.selected();
    if (this.keyKept()) {
      return this.i18n.translate('aiSettings.key.keepHint');
    }
    return preset?.requires_api_key
      ? this.i18n.translate('aiSettings.key.requiredHint', { provider: preset.label })
      : this.i18n.translate('aiSettings.key.optionalHint');
  });

  protected readonly dirty = computed(() => {
    this.formValue();
    const current = this.settings();
    if (!current) {
      return false;
    }
    if (this.removeKey() || this.form.controls.api_key.value.trim() !== '') {
      return true;
    }
    return JSON.stringify(this.normalized()) !== JSON.stringify(this.baseline(current));
  });

  /** Sin fila propia (valor por defecto o del servidor) se puede guardar tal cual para fijarlo. */
  protected readonly canSave = computed(
    () => this.dirty() || (this.settings()?.source ?? 'organization') !== 'organization',
  );

  protected readonly testResult = computed(() => {
    const state = this.test();
    return state.kind === 'done' ? state.result : null;
  });

  protected readonly testMessage = computed(() => {
    const state = this.test();
    return state.kind === 'failed' ? state.message : '';
  });

  ngOnInit(): void {
    this.roles.ensureLoaded();
    this.load();
  }

  protected t(key: string, params?: Record<string, unknown>): string {
    return this.i18n.translate(key, params);
  }

  protected formatDate(value: string): string {
    return formatBogotaDateTime(value);
  }

  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);
    forkJoin([this.service.getSettings(), this.service.getPresets()]).subscribe({
      next: ([settings, presets]) => {
        this.presets.set(presets.data ?? []);
        this.applySettings(settings.data);
        this.loading.set(false);
      },
      error: (err) => {
        const api = readApiError(err);
        this.loading.set(false);
        this.canRetry.set(api.status !== 403);
        this.loadError.set(
          api.status === 403
            ? this.t('aiSettings.errors.forbidden')
            : api.status === 0
              ? this.t('aiSettings.errors.network')
              : this.t('aiSettings.errors.load'),
        );
      },
    });
  }

  protected selectPreset(preset: AiPreset): void {
    if (preset.key === this.selectedKey()) {
      return;
    }
    const current = this.settings();
    this.selectedKey.set(preset.key);
    this.test.set({ kind: 'idle' });
    this.saveError.set(null);
    this.serverFieldErrors.set({});
    if (current && current.preset === preset.key) {
      this.patchFrom(current);
      return;
    }
    this.form.patchValue({
      base_url: preset.base_url ?? '',
      chat_model: preset.chat_model,
      embedding_model: preset.embedding_model ?? '',
      api_key: '',
    });
    this.syncBaseUrlState(preset);
  }

  protected discard(): void {
    const current = this.settings();
    if (current) {
      this.applySettings(current);
    }
  }

  protected fieldError(field: string): string {
    const server = this.serverFieldErrors()[field];
    if (server) {
      return server;
    }
    if (!this.submitted()) {
      return '';
    }
    return this.localErrors()[field] ?? '';
  }

  protected runTest(): void {
    if (Object.keys(this.localErrors()).length > 0) {
      this.submitted.set(true);
      return;
    }
    this.test.set({ kind: 'running' });
    this.service.test(this.payload()).subscribe({
      next: (res) => this.test.set({ kind: 'done', result: res.data }),
      error: (err) => this.test.set({ kind: 'failed', message: this.describeError(err) }),
    });
  }

  protected save(): void {
    this.submitted.set(true);
    this.saveError.set(null);
    this.serverFieldErrors.set({});
    if (!this.canSave() || Object.keys(this.localErrors()).length > 0) {
      return;
    }
    this.saving.set(true);
    this.service.update(this.payload()).subscribe({
      next: (res) => {
        this.saving.set(false);
        this.applySettings(res.data);
        this.alerts.showSuccess(this.t('aiSettings.saved', { provider: res.data.preset_label }));
      },
      error: (err) => {
        this.saving.set(false);
        const api = readApiError(err);
        const message = this.describeError(err);
        if (api.code === 'AI_API_KEY_REQUIRED' || api.code === 'AI_API_KEY_UNREADABLE') {
          this.serverFieldErrors.set({ api_key: message });
        } else if (api.code === 'llm_base_url_rejected') {
          this.serverFieldErrors.set({ base_url: message });
        } else if (api.code === 'AI_CHAT_MODEL_REQUIRED') {
          this.serverFieldErrors.set({ chat_model: message });
        } else {
          this.saveError.set(message);
        }
      },
    });
  }

  private applySettings(settings: AiSettings): void {
    this.settings.set(settings);
    this.selectedKey.set(settings.preset);
    this.removeKey.set(false);
    this.submitted.set(false);
    this.saveError.set(null);
    this.serverFieldErrors.set({});
    this.patchFrom(settings);
  }

  private patchFrom(settings: AiSettings): void {
    this.form.setValue({
      base_url: settings.base_url ?? '',
      chat_model: settings.chat_model ?? '',
      embedding_model: settings.embedding_model ?? '',
      api_key: '',
      enabled: settings.enabled,
      timeout_seconds: String(settings.timeout_seconds),
      max_tokens: String(settings.max_tokens),
      temperature: String(settings.temperature),
      num_ctx: settings.num_ctx === null || settings.num_ctx === undefined ? '' : String(settings.num_ctx),
      reasoning_effort: settings.reasoning_effort ?? 'none',
    });
    const preset = this.presets().find((p) => p.key === settings.preset);
    if (preset) {
      this.syncBaseUrlState(preset);
    }
  }

  private syncBaseUrlState(preset: AiPreset): void {
    const control = this.form.controls.base_url;
    if (preset.base_url_editable) {
      control.enable({ emitEvent: false });
    } else {
      control.disable({ emitEvent: false });
    }
    this.form.updateValueAndValidity();
  }

  /** Errores de cliente (rango del esquema del backend) antes de gastar una petición. */
  private localErrors(): Record<string, string> {
    this.formValue();
    const value = this.form.getRawValue();
    const preset = this.selected();
    const errors: Record<string, string> = {};
    const number = (raw: string) => (raw.trim() === '' ? NaN : Number(raw));
    if (preset?.key === 'custom' && !value.base_url.trim()) {
      errors['base_url'] = this.t('aiSettings.errors.baseUrlRequired');
    }
    if (!value.chat_model.trim()) {
      errors['chat_model'] = this.t('aiSettings.errors.chatModelRequired');
    }
    if (preset?.requires_api_key && !this.keyKept() && !value.api_key.trim()) {
      errors['api_key'] = this.t('aiSettings.errors.keyRequired', { provider: preset.label });
    }
    const timeout = number(value.timeout_seconds);
    if (!(timeout > 0 && timeout <= 600)) {
      errors['timeout_seconds'] = this.t('aiSettings.errors.range', { min: 1, max: 600 });
    }
    const maxTokens = number(value.max_tokens);
    if (!(Number.isInteger(maxTokens) && maxTokens >= 1 && maxTokens <= 32768)) {
      errors['max_tokens'] = this.t('aiSettings.errors.range', { min: 1, max: 32768 });
    }
    const temperature = number(value.temperature);
    if (!(temperature >= 0 && temperature <= 2)) {
      errors['temperature'] = this.t('aiSettings.errors.range', { min: 0, max: 2 });
    }
    if (value.num_ctx.trim() !== '') {
      const ctx = number(value.num_ctx);
      if (!(Number.isInteger(ctx) && ctx >= 256 && ctx <= 262144)) {
        errors['num_ctx'] = this.t('aiSettings.errors.range', { min: 256, max: 262144 });
      }
    }
    return errors;
  }

  private normalized(): AiSettingsUpdate {
    const value = this.form.getRawValue();
    const preset = this.selected();
    return {
      preset: this.selectedKey(),
      base_url: preset?.base_url_editable ? value.base_url.trim() || null : null,
      chat_model: value.chat_model.trim() || null,
      embedding_model: value.embedding_model.trim() || null,
      timeout_seconds: Number(value.timeout_seconds),
      max_tokens: Number(value.max_tokens),
      temperature: Number(value.temperature),
      reasoning_effort: (value.reasoning_effort || null) as AiReasoningEffort | null,
      num_ctx: value.num_ctx.trim() === '' ? null : Number(value.num_ctx),
      enabled: value.enabled,
    };
  }

  private baseline(settings: AiSettings): AiSettingsUpdate {
    const preset = this.presets().find((p) => p.key === settings.preset);
    return {
      preset: settings.preset,
      base_url: preset?.base_url_editable ? settings.base_url || null : null,
      chat_model: settings.chat_model || null,
      embedding_model: settings.embedding_model || null,
      timeout_seconds: settings.timeout_seconds,
      max_tokens: settings.max_tokens,
      temperature: settings.temperature,
      reasoning_effort: settings.reasoning_effort ?? 'none',
      num_ctx: settings.num_ctx ?? null,
      enabled: settings.enabled,
    };
  }

  private payload(): AiSettingsUpdate {
    const body = this.normalized();
    const key = this.form.controls.api_key.value.trim();
    if (this.removeKey()) {
      return { ...body, api_key: null };
    }
    return key ? { ...body, api_key: key } : body;
  }

  private describeError(err: unknown): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.t('aiSettings.errors.network');
    }
    if (api.status === 403) {
      return this.t('aiSettings.errors.forbiddenWrite');
    }
    const detail = api.detail ?? this.t('aiSettings.errors.unknown');
    return api.code ? `${detail} (${api.code})` : detail;
  }
}
