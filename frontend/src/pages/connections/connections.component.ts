import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolChipComponent,
  SolDrawerComponent,
  SolEmptyStateComponent,
  SolFileUploadComponent,
  SolIconComponent,
  SolInputComponent,
  SolModalComponent,
  SolSkeletonComponent,
  SolToggleComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AlertService } from '@shared/lib/alerts';
import { readApiError } from '@shared/lib/api-error';
import { ConnectorsService } from '@entities/connector/connectors.service';
import {
  ConnectedAccount,
  Connector,
  JiraImportResult,
  SOLERCIA_CONNECT_TARGETS,
  SolerciaConnectTarget,
  providerIcon,
  providerLabel,
  solerciaConnectSettingsOf,
} from '@entities/connector/connector.model';
import { SolerciaConnectCardComponent } from '@widgets/solercia-connect-card/solercia-connect-card.component';

/** Aviso superior tras volver del flujo OAuth (durable, no transitorio). */
interface Banner {
  kind: 'success' | 'error';
  text: string;
}

const SOLERCIA_CONNECT = 'solercia_connect';

/**
 * Página "Conexiones": una sola opción creable — Solercia Connect · Microsoft
 * 365 — con su ciclo de vida completo en `sol-solercia-connect-card` (estado,
 * inicio de sesión supervisado, sincronización, eliminación). Los conectores de
 * otros proveedores que ya existan en la base (Jira, Google…) siguen pintándose
 * con su tarjeta heredada y su botón de eliminar; solo salieron del catálogo.
 *
 * Flujo OAuth heredado: "Conectar cuenta" navega (página completa) al authorize
 * del backend con `redirect_to=<origin>/connections`; el callback devuelve al
 * navegador aquí con `?connected=1` o `?error=<código>` y esta página lo
 * traduce a un banner + refresco de cuentas.
 */
@Component({
  selector: 'sol-connections',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolBadgeComponent,
    SolButtonComponent,
    SolCardComponent,
    SolChipComponent,
    SolDrawerComponent,
    SolEmptyStateComponent,
    SolFileUploadComponent,
    SolIconComponent,
    SolInputComponent,
    SolModalComponent,
    SolSkeletonComponent,
    SolToggleComponent,
    SolerciaConnectCardComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold text-text">{{ text.title() }}</h1>
          <p class="text-sm text-muted">{{ text.subtitle() }}</p>
        </div>
        <sol-button type="button" variant="primary" size="touch" (clicked)="openCreate()">
          {{ text.createOpen() }}
        </sol-button>
      </div>

      @if (banner(); as note) {
        <div
          role="alert"
          class="flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm"
          [class.border-success/40]="note.kind === 'success'"
          [class.bg-success/10]="note.kind === 'success'"
          [class.text-success]="note.kind === 'success'"
          [class.border-danger/40]="note.kind === 'error'"
          [class.bg-danger/10]="note.kind === 'error'"
          [class.text-danger]="note.kind === 'error'"
        >
          <span>{{ note.text }}</span>
          <button
            type="button"
            class="shrink-0 opacity-70 hover:opacity-100"
            [attr.aria-label]="text.bannerClose()"
            (click)="banner.set(null)"
          >
            <sol-icon name="x-mark" size="sm" />
          </button>
        </div>
      }

      @if (loading()) {
        <!-- Cargando: esqueleto de dos tarjetas -->
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2" aria-busy="true">
          <sol-skeleton variant="card" />
          <sol-skeleton variant="card" />
        </div>
      } @else if (loadError(); as message) {
        <!-- Error de carga: detalle del backend + reintentar (nunca el estado vacío) -->
        <div
          role="alert"
          class="flex flex-col gap-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger sm:flex-row sm:items-center sm:justify-between"
        >
          <span>{{ message }}</span>
          <sol-button type="button" variant="secondary" size="touch" (clicked)="load()">
            {{ text.retry() }}
          </sol-button>
        </div>
      } @else if (connectors().length === 0) {
        <!-- Vacío legítimo -->
        <sol-empty-state
          icon="plug"
          titleKey="connectors.empty.title"
          descriptionKey="connectors.empty.subtitle"
        >
          <sol-button type="button" variant="primary" size="touch" (clicked)="openCreate()">
            {{ text.createOpen() }}
          </sol-button>
        </sol-empty-state>
      } @else {
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          @for (connector of connectors(); track connector.id) {
            @if (connector.provider === solerciaConnect) {
              <sol-solercia-connect-card
                [connector]="connector"
                (deleteRequested)="askDelete($event)"
              />
            } @else {
              <!-- Tarjeta heredada para proveedores que ya no se crean desde aquí -->
              <sol-card>
                <div class="flex flex-col gap-4">
                  <div class="flex items-start justify-between gap-2">
                    <div class="flex items-center gap-3">
                      <span
                        class="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand/10 text-brand"
                        aria-hidden="true"
                      >
                        <sol-icon [name]="icon(connector)" />
                      </span>
                      <div>
                        <h2 class="text-base font-semibold text-text">
                          {{ label(connector) }}
                        </h2>
                        <p class="text-xs text-muted">
                          {{ kindLabel(connector.credential_kind) }}
                        </p>
                      </div>
                    </div>
                    <div class="flex shrink-0 items-center gap-2">
                      <sol-badge [variant]="statusVariant(connector.status)" size="sm">
                        {{ statusLabel(connector.status) }}
                      </sol-badge>
                      <button
                        type="button"
                        class="inline-flex h-11 w-11 items-center justify-center rounded-md text-muted
                               hover:bg-danger/10 hover:text-danger focus:outline-none
                               focus-visible:ring-2 focus-visible:ring-danger/50"
                        [attr.aria-label]="deleteAria(connector)"
                        (click)="askDelete(connector)"
                      >
                        <sol-icon name="trash" size="sm" />
                      </button>
                    </div>
                  </div>

                  <div>
                    <h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
                      {{ text.accountsHeading() }}
                    </h3>
                    @if (accountsError().has(connector.id)) {
                      <p class="text-sm text-danger">{{ text.accountsLoadError() }}</p>
                    } @else if (accountsOf(connector.id).length === 0) {
                      <p class="text-sm text-muted">{{ text.accountsEmpty() }}</p>
                    } @else {
                      <ul class="flex flex-col gap-1">
                        @for (account of accountsOf(connector.id); track account.id) {
                          <li
                            class="flex items-center justify-between gap-2 rounded-md bg-sunken px-3 py-1.5 text-sm text-text"
                          >
                            <span class="flex min-w-0 items-center gap-2">
                              <sol-icon name="user" size="sm" class="shrink-0 text-muted" />
                              <span class="truncate">
                                {{ account.display_name || account.external_account_id }}
                              </span>
                              @if (account.status !== 'active') {
                                <sol-badge variant="neutral" size="sm">
                                  {{ statusLabel(account.status) }}
                                </sol-badge>
                              }
                            </span>
                            <button
                              type="button"
                              class="shrink-0 text-xs font-medium text-danger hover:underline
                                     focus:outline-none focus-visible:ring-2 focus-visible:ring-danger/50"
                              [attr.aria-label]="revokeAria(account)"
                              (click)="revokeAccount(connector, account)"
                            >
                              {{ text.accountsRevoke() }}
                            </button>
                          </li>
                        }
                      </ul>
                    }
                  </div>

                  <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                    @if (connector.credential_kind === 'oauth') {
                      <sol-button
                        type="button"
                        variant="primary"
                        size="touch"
                        [attr.aria-label]="connectAria(connector)"
                        (clicked)="connect(connector)"
                      >
                        {{ text.connect() }}
                      </sol-button>
                    }
                    @if (connector.credential_kind === 'api_token' && connector.provider !== 'mcp') {
                      <sol-button
                        type="button"
                        variant="secondary"
                        size="touch"
                        [attr.aria-label]="credentialsAria(connector)"
                        (clicked)="openCredentials(connector)"
                      >
                        {{ text.credentialsOpen() }}
                      </sol-button>
                    }
                    @if (connector.provider === 'jira') {
                      <sol-button
                        type="button"
                        variant="ghost"
                        size="touch"
                        [attr.aria-label]="jiraImportAria(connector)"
                        (clicked)="openJiraImport(connector)"
                      >
                        {{ text.jiraImportOpen() }}
                      </sol-button>
                    }
                  </div>
                </div>
              </sol-card>
            }
          }
        </div>
      }
    </section>

    <!-- Drawer: conectar Solercia Connect (3 decisiones, dos ya resueltas) -->
    <sol-drawer [open]="createOpen()" [title]="text.createTitle()" (closed)="closeCreate()">
      <form class="flex flex-col gap-5" novalidate (submit)="onCreateSubmit($event)">
        <div class="flex flex-col gap-1">
          <!-- El bloqueo mientras se envía lo hace el FormControl (disable/enable), no el input. -->
          <sol-input
            type="email"
            autocomplete="email"
            [label]="text.accountLabel()"
            [placeholder]="text.accountPlaceholder()"
            [error]="accountError()"
            [formControl]="accountControl"
          ></sol-input>
          @if (!accountError()) {
            <p class="text-xs text-muted">{{ text.accountHint() }}</p>
          }
        </div>

        <fieldset class="flex flex-col gap-2 border-0 p-0" [disabled]="creating()">
          <legend class="mb-2 text-sm font-medium text-text">{{ text.targetLabel() }}</legend>
          <div role="radiogroup" class="flex flex-wrap gap-2" [attr.aria-label]="text.targetLabel()">
            @for (option of targets; track option) {
              <sol-chip
                [role]="'radio'"
                [value]="option"
                [label]="targetLabel(option)"
                [selected]="target() === option"
                [disabled]="creating()"
                (toggled)="target.set(option)"
              />
            }
          </div>
        </fieldset>

        <div class="flex flex-col gap-1">
          <sol-toggle
            [label]="text.browserFallbackLabel()"
            [formControl]="browserFallbackControl"
          ></sol-toggle>
          <p class="text-xs text-muted">{{ text.browserFallbackHelp() }}</p>
        </div>

        @if (createError(); as message) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ message }}
          </div>
        }

        <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
          <sol-button
            type="button"
            variant="primary"
            size="touch"
            [loading]="creating()"
            (clicked)="submitCreate()"
          >
            {{ creating() ? text.createSubmitting() : text.createSubmit() }}
          </sol-button>
          <sol-button type="button" variant="ghost" size="touch" (clicked)="closeCreate()">
            {{ text.createCancel() }}
          </sol-button>
        </div>
      </form>
    </sol-drawer>

    <!-- Drawer: credenciales api_token (GLPI / Jira heredados) -->
    <sol-drawer
      [open]="credentialsFor() !== null"
      [title]="credentialsTitle()"
      (closed)="closeCredentials()"
    >
      <div class="flex flex-col gap-4">
        <sol-input
          [label]="text.fieldBaseUrl()"
          [placeholder]="text.fieldBaseUrlPlaceholder()"
          [formControl]="baseUrlControl"
        ></sol-input>

        @if (credentialsFor()?.provider === 'glpi') {
          <sol-input
            [label]="text.fieldGlpiAppToken()"
            type="password"
            [formControl]="glpiAppTokenControl"
          ></sol-input>
          <sol-input
            [label]="text.fieldGlpiUserToken()"
            type="password"
            [formControl]="glpiUserTokenControl"
          ></sol-input>
        }
        @if (credentialsFor()?.provider === 'jira') {
          <sol-input
            [label]="text.fieldEmail()"
            [placeholder]="text.fieldEmailPlaceholder()"
            type="email"
            [formControl]="jiraEmailControl"
          ></sol-input>
          <sol-input
            [label]="text.fieldJiraApiToken()"
            type="password"
            [formControl]="jiraApiTokenControl"
          ></sol-input>
        }

        @if (credentialsRequired()) {
          <p class="text-xs text-danger">{{ text.credentialsRequired() }}</p>
        }
        @if (credentialsError()) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ credentialsError() }}
          </div>
        }

        <div class="flex items-center gap-2">
          <sol-button
            type="button"
            variant="primary"
            [loading]="credentialsSubmitting()"
            (clicked)="submitCredentials()"
          >
            {{
              credentialsSubmitting()
                ? text.credentialsSubmitting()
                : text.credentialsSubmit()
            }}
          </sol-button>
          <sol-button type="button" variant="ghost" (clicked)="closeCredentials()">
            {{ text.credentialsCancel() }}
          </sol-button>
        </div>
      </div>
    </sol-drawer>

    <!-- Drawer: importar archivo de Jira (preview, sin persistir) -->
    <sol-drawer
      [open]="jiraImportFor() !== null"
      [title]="text.jiraImportTitle()"
      size="lg"
      (closed)="closeJiraImport()"
    >
      <div class="flex flex-col gap-4">
        <!--
          sol-file-upload valida contra el MIME exacto del archivo (no la
          extensión), así que accept lista los MIME de CSV y XLSX; algunos
          navegadores reportan los CSV como application/vnd.ms-excel.
        -->
        <sol-file-upload
          accept="text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          [label]="text.jiraImportFileLabel()"
          [hint]="text.jiraImportFileHint()"
          (fileSelected)="jiraFile.set($event)"
          (fileRemoved)="jiraFile.set(null)"
        ></sol-file-upload>

        @if (jiraImportError()) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ jiraImportError() }}
          </div>
        }

        <div>
          <sol-button
            type="button"
            variant="primary"
            [disabled]="jiraImporting() || !jiraFile()"
            (clicked)="submitJiraImport()"
          >
            {{ jiraImporting() ? text.jiraImportSubmitting() : text.jiraImportSubmit() }}
          </sol-button>
        </div>

        @if (jiraImportResult(); as result) {
          <div class="flex flex-col gap-2">
            <p class="text-sm text-muted">{{ jiraPreviewSummary(result) }}</p>
            <div class="overflow-x-auto rounded-lg border border-border">
              <table class="w-full min-w-[560px] text-left text-sm">
                <thead class="bg-sunken text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th class="px-3 py-2">{{ text.jiraColKey() }}</th>
                    <th class="px-3 py-2">{{ text.jiraColTitle() }}</th>
                    <th class="px-3 py-2">{{ text.jiraColType() }}</th>
                    <th class="px-3 py-2">{{ text.jiraColStatus() }}</th>
                    <th class="px-3 py-2">{{ text.jiraColPriority() }}</th>
                    <th class="px-3 py-2">{{ text.jiraColPoints() }}</th>
                    <th class="px-3 py-2">{{ text.jiraColAssignee() }}</th>
                  </tr>
                </thead>
                <tbody>
                  @for (issue of result.issues; track issue.key) {
                    <tr class="border-t border-border text-text">
                      <td class="px-3 py-2 font-medium">{{ issue.key }}</td>
                      <td class="max-w-[220px] truncate px-3 py-2">{{ issue.title }}</td>
                      <td class="px-3 py-2">{{ issue.issue_type }}</td>
                      <td class="px-3 py-2">{{ issue.status_bucket }}</td>
                      <td class="px-3 py-2">{{ issue.priority }}</td>
                      <td class="px-3 py-2">{{ issue.story_points ?? '—' }}</td>
                      <td class="max-w-[160px] truncate px-3 py-2">
                        {{ issue.assignee_raw || '—' }}
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        }
      </div>
    </sol-drawer>

    <!-- Modal: confirmar eliminación (nunca confirm() nativo) -->
    @if (deleting(); as target) {
      <sol-modal [open]="true" size="sm" [title]="deleteTitle()" (closed)="cancelDelete()">
        <p class="text-sm text-muted">{{ text.deleteBody() }}</p>
        @if (deleteError(); as message) {
          <div
            role="alert"
            class="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ message }}
          </div>
        }
        <div class="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <sol-button type="button" variant="ghost" size="touch" (clicked)="cancelDelete()">
            {{ text.deleteCancel() }}
          </sol-button>
          <sol-button
            type="button"
            variant="danger"
            size="touch"
            [loading]="deleteSubmitting()"
            [attr.aria-label]="deleteAria(target)"
            (clicked)="confirmDelete()"
          >
            {{ deleteSubmitting() ? text.deleteDeleting() : text.deleteConfirm() }}
          </sol-button>
        </div>
      </sol-modal>
    }
  `,
})
export class ConnectionsComponent implements OnInit {
  private readonly connectorsService = inject(ConnectorsService);
  private readonly i18n = inject(I18nService);
  private readonly alert = inject(AlertService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly solerciaConnect = SOLERCIA_CONNECT;
  protected readonly targets = SOLERCIA_CONNECT_TARGETS;

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('connectors.title'),
    subtitle: this.i18n.t('connectors.subtitle'),
    retry: this.i18n.t('connectors.errors.retry'),
    bannerClose: this.i18n.t('shared.drawer.closeAria'),
    connect: this.i18n.t('connectors.connect'),
    accountsHeading: this.i18n.t('connectors.accounts.heading'),
    accountsEmpty: this.i18n.t('connectors.accounts.empty'),
    accountsRevoke: this.i18n.t('connectors.accounts.revoke'),
    accountsLoadError: this.i18n.t('connectors.accounts.loadError'),
    createOpen: this.i18n.t('connectors.create.open'),
    createTitle: this.i18n.t('connectors.create.title'),
    createSubmit: this.i18n.t('connectors.create.submit'),
    createSubmitting: this.i18n.t('connectors.create.submitting'),
    createCancel: this.i18n.t('connectors.create.cancel'),
    accountLabel: this.i18n.t('connectors.create.accountLabel'),
    accountPlaceholder: this.i18n.t('connectors.create.accountPlaceholder'),
    accountHint: this.i18n.t('connectors.create.accountHint'),
    targetLabel: this.i18n.t('connectors.create.targetLabel'),
    browserFallbackLabel: this.i18n.t('connectors.create.browserFallbackLabel'),
    browserFallbackHelp: this.i18n.t('connectors.create.browserFallbackHelp'),
    deleteBody: this.i18n.t('connectors.delete.confirmBody'),
    deleteCancel: this.i18n.t('connectors.delete.cancel'),
    deleteConfirm: this.i18n.t('connectors.delete.confirm'),
    deleteDeleting: this.i18n.t('connectors.delete.deleting'),
    credentialsOpen: this.i18n.t('connectors.credentials.open'),
    credentialsRequired: this.i18n.t('connectors.credentials.required'),
    credentialsSubmit: this.i18n.t('connectors.credentials.submit'),
    credentialsSubmitting: this.i18n.t('connectors.credentials.submitting'),
    credentialsCancel: this.i18n.t('connectors.credentials.cancel'),
    fieldBaseUrl: this.i18n.t('connectors.credentials.fields.baseUrl'),
    fieldBaseUrlPlaceholder: this.i18n.t('connectors.credentials.fields.baseUrlPlaceholder'),
    fieldEmail: this.i18n.t('connectors.credentials.fields.email'),
    fieldEmailPlaceholder: this.i18n.t('connectors.credentials.fields.emailPlaceholder'),
    fieldGlpiAppToken: this.i18n.t('connectors.credentials.fields.glpiAppToken'),
    fieldGlpiUserToken: this.i18n.t('connectors.credentials.fields.glpiUserToken'),
    fieldJiraApiToken: this.i18n.t('connectors.credentials.fields.jiraApiToken'),
    jiraImportOpen: this.i18n.t('connectors.jiraImport.open'),
    jiraImportTitle: this.i18n.t('connectors.jiraImport.title'),
    jiraImportFileLabel: this.i18n.t('connectors.jiraImport.fileLabel'),
    jiraImportFileHint: this.i18n.t('connectors.jiraImport.fileHint'),
    jiraImportSubmit: this.i18n.t('connectors.jiraImport.submit'),
    jiraImportSubmitting: this.i18n.t('connectors.jiraImport.submitting'),
    jiraColKey: this.i18n.t('connectors.jiraImport.columns.key'),
    jiraColTitle: this.i18n.t('connectors.jiraImport.columns.title'),
    jiraColType: this.i18n.t('connectors.jiraImport.columns.type'),
    jiraColStatus: this.i18n.t('connectors.jiraImport.columns.status'),
    jiraColPriority: this.i18n.t('connectors.jiraImport.columns.priority'),
    jiraColPoints: this.i18n.t('connectors.jiraImport.columns.points'),
    jiraColAssignee: this.i18n.t('connectors.jiraImport.columns.assignee'),
  } as const;

  // -- listado -------------------------------------------------------------
  protected readonly connectors = signal<Connector[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);

  /** Cuentas conectadas por id de conector (solo proveedores heredados). */
  protected readonly accounts = signal<Map<string, ConnectedAccount[]>>(new Map());
  /** Ids de conector cuyas cuentas no se pudieron cargar. */
  protected readonly accountsError = signal<Set<string>>(new Set());

  protected readonly banner = signal<Banner | null>(null);

  // -- conectar Solercia Connect ---------------------------------------------------
  protected readonly createOpen = signal(false);
  protected readonly creating = signal(false);
  protected readonly createError = signal<string | null>(null);
  protected readonly accountError = signal('');
  protected readonly target = signal<SolerciaConnectTarget>('outlook');

  protected readonly accountControl = new FormControl<string>('', {
    nonNullable: true,
    validators: [Validators.required, Validators.email],
  });
  protected readonly browserFallbackControl = new FormControl<boolean>(true, {
    nonNullable: true,
  });

  // -- eliminar (cualquier proveedor) ----------------------------------------------
  protected readonly deleting = signal<Connector | null>(null);
  protected readonly deleteSubmitting = signal(false);
  protected readonly deleteError = signal<string | null>(null);

  protected readonly deleteTitle = computed(() => {
    this.i18n.activeLang();
    const target = this.deleting();
    return target
      ? this.i18n.translate('connectors.delete.confirmTitle', {
          provider: providerLabel(target.provider),
        })
      : '';
  });

  // -- credenciales api_token (heredado) ------------------------------------------
  protected readonly credentialsFor = signal<Connector | null>(null);
  protected readonly credentialsSubmitting = signal(false);
  protected readonly credentialsError = signal<string | null>(null);
  protected readonly credentialsRequired = signal(false);

  protected readonly baseUrlControl = new FormControl<string>('', { nonNullable: true });
  protected readonly glpiAppTokenControl = new FormControl<string>('', { nonNullable: true });
  protected readonly glpiUserTokenControl = new FormControl<string>('', { nonNullable: true });
  protected readonly jiraEmailControl = new FormControl<string>('', { nonNullable: true });
  protected readonly jiraApiTokenControl = new FormControl<string>('', { nonNullable: true });

  protected readonly credentialsTitle = computed(() => {
    this.i18n.activeLang();
    const target = this.credentialsFor();
    return target
      ? this.i18n.translate('connectors.credentials.title', {
          provider: providerLabel(target.provider),
        })
      : '';
  });

  // -- import de archivo Jira (heredado) -------------------------------------------
  protected readonly jiraImportFor = signal<Connector | null>(null);
  protected readonly jiraFile = signal<File | null>(null);
  protected readonly jiraImporting = signal(false);
  protected readonly jiraImportError = signal<string | null>(null);
  protected readonly jiraImportResult = signal<JiraImportResult | null>(null);

  constructor() {
    // Validación al vuelo del correo: el error se pinta junto al campo en
    // cuanto la persona lo toca o escribe, nunca antes.
    this.accountControl.events
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.accountError.set(this.computeAccountError()));
  }

  ngOnInit(): void {
    this.consumeOAuthReturn();
    this.load();
  }

  // -- helpers de presentación ---------------------------------------------

  protected label(connector: Connector): string {
    return providerLabel(connector.provider);
  }

  protected icon(connector: Connector): string {
    return providerIcon(connector.provider);
  }

  protected kindLabel(kind: string): string {
    return this.i18n.translate(`connectors.kind.${kind}`);
  }

  protected statusLabel(status: string): string {
    return this.i18n.translate(`connectors.status.${status}`);
  }

  protected statusVariant(status: string): 'success' | 'danger' | 'neutral' {
    if (status === 'active') {
      return 'success';
    }
    return status === 'error' ? 'danger' : 'neutral';
  }

  protected targetLabel(target: SolerciaConnectTarget): string {
    return this.i18n.translate(`connectors.create.targets.${target}`);
  }

  protected accountsOf(connectorId: string): ConnectedAccount[] {
    return this.accounts().get(connectorId) ?? [];
  }

  protected connectAria(connector: Connector): string {
    return this.i18n.translate('connectors.connectAria', {
      provider: this.label(connector),
    });
  }

  protected credentialsAria(connector: Connector): string {
    return this.i18n.translate('connectors.credentials.openAria', {
      provider: this.label(connector),
    });
  }

  protected jiraImportAria(connector: Connector): string {
    return this.i18n.translate('connectors.jiraImport.openAria', {
      provider: this.label(connector),
    });
  }

  protected deleteAria(connector: Connector): string {
    return this.i18n.translate('connectors.delete.ariaLabel', {
      provider: this.label(connector),
    });
  }

  protected revokeAria(account: ConnectedAccount): string {
    return this.i18n.translate('connectors.accounts.revokeAria', {
      name: account.display_name || account.external_account_id,
    });
  }

  protected jiraPreviewSummary(result: JiraImportResult): string {
    return this.i18n.translate('connectors.jiraImport.preview', {
      normalized: String(result.report.normalized),
      total: String(result.report.total),
    });
  }

  // -- flujo OAuth (heredado) --------------------------------------------------

  /** Traduce `?connected=1` / `?error=` del callback a un banner y limpia la URL. */
  private consumeOAuthReturn(): void {
    const params = this.route.snapshot.queryParamMap;
    const connected = params.get('connected');
    const errorCode = params.get('error');
    if (connected === '1') {
      this.banner.set({
        kind: 'success',
        text: this.i18n.translate('connectors.banner.connected'),
      });
    } else if (errorCode) {
      this.banner.set({
        kind: 'error',
        text: this.i18n.translate('connectors.banner.error', { code: errorCode }),
      });
    }
    if (connected || errorCode) {
      void this.router.navigate([], {
        relativeTo: this.route,
        queryParams: {},
        replaceUrl: true,
      });
    }
  }

  /**
   * Pide por XHR un ticket efímero de un solo uso y navega al authorize
   * con él — el JWT nunca aparece en la URL (CWE-598).
   */
  protected connect(connector: Connector): void {
    this.connectorsService.createAuthorizeTicket(connector.id).subscribe({
      next: (res) => {
        const url = this.connectorsService.authorizeUrl(
          connector.id,
          `${window.location.origin}/connections`,
          res.data.ticket,
        );
        window.location.assign(url);
      },
      error: (err: HttpErrorResponse) => {
        this.alert.showError(
          err.status === 401
            ? this.i18n.translate('connectors.errors.session')
            : this.apiErrorMessage(err, 'connectors.errors.connectStart'),
        );
      },
    });
  }

  // -- listado / cuentas -------------------------------------------------------

  protected load(): void {
    this.loading.set(true);
    this.loadError.set(null);

    this.connectorsService.list().subscribe({
      next: (res) => {
        const list = res.data ?? [];
        this.connectors.set(list);
        this.loading.set(false);
        for (const connector of list) {
          // La tarjeta de Solercia Connect consulta su propio estado.
          if (connector.provider !== SOLERCIA_CONNECT) {
            this.loadAccounts(connector.id);
          }
        }
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(this.apiErrorMessage(err, 'connectors.errors.load'));
      },
    });
  }

  private loadAccounts(connectorId: string): void {
    this.connectorsService.accounts(connectorId).subscribe({
      next: (res) => {
        const next = new Map(this.accounts());
        next.set(connectorId, res.data ?? []);
        this.accounts.set(next);
        this.accountsError.update((ids) => {
          if (!ids.has(connectorId)) {
            return ids;
          }
          const copy = new Set(ids);
          copy.delete(connectorId);
          return copy;
        });
      },
      error: () => {
        this.accountsError.update((ids) => new Set(ids).add(connectorId));
      },
    });
  }

  protected revokeAccount(connector: Connector, account: ConnectedAccount): void {
    this.connectorsService.revokeAccount(account.id).subscribe({
      next: () => {
        this.alert.showSuccess(this.i18n.translate('connectors.accounts.revoked'));
        this.loadAccounts(connector.id);
      },
      error: (err: HttpErrorResponse) => {
        this.alert.showError(this.apiErrorMessage(err, 'connectors.accounts.revokeError'));
      },
    });
  }

  // -- eliminar ------------------------------------------------------------------

  protected askDelete(connector: Connector): void {
    this.deleteError.set(null);
    this.deleting.set(connector);
  }

  protected cancelDelete(): void {
    if (this.deleteSubmitting()) {
      return;
    }
    this.deleting.set(null);
  }

  protected confirmDelete(): void {
    const target = this.deleting();
    if (!target || this.deleteSubmitting()) {
      return;
    }
    this.deleteSubmitting.set(true);
    this.deleteError.set(null);
    this.connectorsService.delete(target.id).subscribe({
      next: () => {
        this.deleteSubmitting.set(false);
        this.deleting.set(null);
        this.alert.showSuccess(this.i18n.translate('connectors.delete.success'));
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.deleteSubmitting.set(false);
        this.deleteError.set(this.apiErrorMessage(err, 'connectors.delete.error'));
      },
    });
  }

  // -- conectar Solercia Connect ---------------------------------------------------

  /**
   * Abre el drawer con valores probables ya puestos: Outlook y navegador
   * activado; si la organización ya registró Solercia Connect, precarga su
   * configuración para que re-registrar sea un solo clic.
   */
  protected openCreate(): void {
    const existing = this.connectors().find((c) => c.provider === SOLERCIA_CONNECT);
    const settings = existing ? solerciaConnectSettingsOf(existing) : null;
    this.setCreateFormEnabled(true);
    this.accountControl.reset(settings?.account ?? '');
    this.target.set(settings?.target ?? 'outlook');
    this.browserFallbackControl.setValue(settings?.allow_browser_fallback ?? true);
    this.accountError.set('');
    this.createError.set(null);
    this.createOpen.set(true);
  }

  /**
   * Bloquea/desbloquea los campos del drawer mientras se envía, a través del
   * FormControl (CVA `setDisabledState`) — nunca con `[disabled]` sobre un
   * host que ya lleva `[formControl]`, que Angular advierte y puede desincronizar.
   */
  private setCreateFormEnabled(enabled: boolean): void {
    if (enabled) {
      this.accountControl.enable({ emitEvent: false });
      this.browserFallbackControl.enable({ emitEvent: false });
    } else {
      this.accountControl.disable({ emitEvent: false });
      this.browserFallbackControl.disable({ emitEvent: false });
    }
  }

  protected closeCreate(): void {
    this.createOpen.set(false);
  }

  /** Enter dentro del correo envía el formulario sin recargar la página. */
  protected onCreateSubmit(event: Event): void {
    event.preventDefault();
    this.submitCreate();
  }

  protected submitCreate(): void {
    if (this.creating()) {
      return;
    }
    this.accountControl.markAsTouched();
    this.accountError.set(this.computeAccountError());
    if (this.accountControl.invalid) {
      return;
    }

    const payload = {
      account: this.accountControl.value.trim().toLowerCase(),
      target: this.target(),
      allow_browser_fallback: this.browserFallbackControl.value,
    };
    this.createError.set(null);
    this.creating.set(true);
    this.setCreateFormEnabled(false);
    this.connectorsService.createSolerciaConnect(payload).subscribe({
      next: () => {
        this.creating.set(false);
        this.setCreateFormEnabled(true);
        this.createOpen.set(false);
        this.alert.showSuccess(this.i18n.translate('connectors.create.success'));
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        // El drawer sigue abierto con lo escrito: nunca se pierde el dato.
        this.creating.set(false);
        this.setCreateFormEnabled(true);
        this.createError.set(this.createErrorMessage(err));
      },
    });
  }

  private computeAccountError(): string {
    const control = this.accountControl;
    if (control.disabled || !(control.touched || control.dirty) || control.valid) {
      return '';
    }
    return control.hasError('required')
      ? this.i18n.translate('connectors.create.accountRequired')
      : this.i18n.translate('connectors.create.accountInvalid');
  }

  /** Mapa de errores del alta (UX spec): códigos específicos antes que el detalle. */
  private createErrorMessage(err: HttpErrorResponse): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.i18n.translate('connectors.errors.network');
    }
    if (api.status === 503 || api.code === 'solercia_connect_unavailable') {
      return this.i18n.translate('connectors.create.errors.unavailable');
    }
    if (api.code === 'solercia_connect_not_configured') {
      return this.i18n.translate('connectors.create.errors.notConfigured');
    }
    if (api.status === 403) {
      return this.i18n.translate('connectors.create.errors.forbidden');
    }
    return api.detail ?? this.i18n.translate('connectors.errors.create');
  }

  // -- credenciales api_token (heredado) --------------------------------------------

  protected openCredentials(connector: Connector): void {
    this.baseUrlControl.setValue('');
    this.glpiAppTokenControl.setValue('');
    this.glpiUserTokenControl.setValue('');
    this.jiraEmailControl.setValue('');
    this.jiraApiTokenControl.setValue('');
    this.credentialsError.set(null);
    this.credentialsRequired.set(false);
    this.credentialsFor.set(connector);
  }

  protected closeCredentials(): void {
    this.credentialsFor.set(null);
  }

  protected submitCredentials(): void {
    const target = this.credentialsFor();
    if (!target) {
      return;
    }

    const payload = this.credentialsPayload(target.provider);
    if (!payload) {
      this.credentialsRequired.set(true);
      return;
    }
    this.credentialsRequired.set(false);
    this.credentialsError.set(null);
    this.credentialsSubmitting.set(true);

    this.connectorsService.registerCredentials(target.id, payload).subscribe({
      next: () => {
        this.credentialsSubmitting.set(false);
        this.credentialsFor.set(null);
        // Los secretos no deben sobrevivir en memoria del formulario tras
        // el envío exitoso (revisión 4R, S1) — no solo al reabrir el drawer.
        this.glpiAppTokenControl.setValue('');
        this.glpiUserTokenControl.setValue('');
        this.jiraApiTokenControl.setValue('');
        this.alert.showSuccess(this.i18n.translate('connectors.credentials.success'));
        this.loadAccounts(target.id);
      },
      error: (err: HttpErrorResponse) => {
        this.credentialsSubmitting.set(false);
        this.credentialsError.set(
          this.apiErrorMessage(err, 'connectors.credentials.error'),
        );
      },
    });
  }

  /**
   * Payload por proveedor con los nombres EXACTOS que valida el handshake
   * del backend (`glpi/adapter.py`: base_url + app_token + user_token;
   * `jira/adapter.py`: base_url + email + api_token). `null` si falta algo.
   */
  private credentialsPayload(provider: string): Record<string, string> | null {
    const baseUrl = this.baseUrlControl.value.trim();
    if (!baseUrl) {
      return null;
    }
    if (provider === 'glpi') {
      const appToken = this.glpiAppTokenControl.value.trim();
      const userToken = this.glpiUserTokenControl.value.trim();
      if (!appToken || !userToken) {
        return null;
      }
      return { base_url: baseUrl, app_token: appToken, user_token: userToken };
    }
    if (provider === 'jira') {
      const email = this.jiraEmailControl.value.trim();
      const apiToken = this.jiraApiTokenControl.value.trim();
      if (!email || !apiToken) {
        return null;
      }
      return { base_url: baseUrl, email, api_token: apiToken };
    }
    return null;
  }

  // -- import de archivo Jira (heredado) ---------------------------------------------

  protected openJiraImport(connector: Connector): void {
    this.jiraFile.set(null);
    this.jiraImportError.set(null);
    this.jiraImportResult.set(null);
    this.jiraImportFor.set(connector);
  }

  protected closeJiraImport(): void {
    this.jiraImportFor.set(null);
  }

  protected submitJiraImport(): void {
    const target = this.jiraImportFor();
    const file = this.jiraFile();
    if (!target || !file) {
      return;
    }
    this.jiraImportError.set(null);
    this.jiraImporting.set(true);

    this.connectorsService.importJiraFile(target.id, file).subscribe({
      next: (res) => {
        this.jiraImporting.set(false);
        this.jiraImportResult.set(res.data);
      },
      error: (err: HttpErrorResponse) => {
        this.jiraImporting.set(false);
        this.jiraImportError.set(
          this.apiErrorMessage(err, 'connectors.jiraImport.error'),
        );
      },
    });
  }

  // -- errores ------------------------------------------------------------------

  /** Mensaje del backend si viene (`detail`), o el fallback i18n indicado. */
  private apiErrorMessage(err: HttpErrorResponse, fallbackKey: string): string {
    const api = readApiError(err);
    if (api.status === 0) {
      return this.i18n.translate('connectors.errors.network');
    }
    return api.detail ?? this.i18n.translate(fallbackKey);
  }
}
