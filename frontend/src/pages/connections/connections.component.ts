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
import {
  SolBadgeComponent,
  SolButtonComponent,
  SolCardComponent,
  SolDrawerComponent,
  SolEmptyStateComponent,
  SolFileUploadComponent,
  SolIconComponent,
  SolInputComponent,
  SolSelectComponent,
  SolSpinnerComponent,
} from '@shared/ui';
import { I18nService } from '@shared/i18n';
import { AuthService } from '@features/auth/auth.service';
import { ConnectorsService } from '@entities/connector/connectors.service';
import {
  ConnectedAccount,
  Connector,
  ConnectorCreatePayload,
  JiraImportResult,
  PROVIDER_CATALOG,
  providerIcon,
  providerLabel,
} from '@entities/connector/connector.model';

/** Aviso superior tras volver del flujo OAuth o tras una acción local. */
interface Banner {
  kind: 'success' | 'error';
  text: string;
}

/**
 * Página "Conexiones": administra los conectores de la organización
 * (Outlook/M365, Gmail/Google, Jira, GLPI, MCP y el proveedor demo).
 *
 * Flujo OAuth: "Conectar cuenta" navega (página completa) al authorize del
 * backend con `redirect_to=<origin>/connections`; el callback devuelve al
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
    SolDrawerComponent,
    SolEmptyStateComponent,
    SolFileUploadComponent,
    SolIconComponent,
    SolInputComponent,
    SolSelectComponent,
    SolSpinnerComponent,
  ],
  template: `
    <section class="flex flex-col gap-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold text-text">{{ text.title() }}</h1>
          <p class="text-sm text-muted">{{ text.subtitle() }}</p>
        </div>
        <sol-button type="button" variant="primary" (click)="openCreate()">
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
        <div class="flex items-center gap-3 py-8">
          <sol-spinner size="sm" />
          <p class="text-sm text-muted">{{ text.loading() }}</p>
        </div>
      } @else if (loadError()) {
        <div
          role="alert"
          class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {{ loadError() }}
        </div>
      } @else if (connectors().length === 0) {
        <sol-empty-state
          icon="arrows-right-left"
          titleKey="connectors.empty.title"
          descriptionKey="connectors.empty.subtitle"
        />
      } @else {
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          @for (connector of connectors(); track connector.id) {
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
                      class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted
                             hover:bg-danger/10 hover:text-danger focus:outline-none
                             focus-visible:ring-2 focus-visible:ring-danger/50"
                      [attr.aria-label]="deleteAria(connector)"
                      (click)="deleteConnector(connector)"
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

                <div class="flex flex-wrap items-center gap-2">
                  @if (connector.credential_kind === 'oauth') {
                    <sol-button
                      type="button"
                      variant="primary"
                      [attr.aria-label]="connectAria(connector)"
                      (click)="connect(connector)"
                    >
                      {{ text.connect() }}
                    </sol-button>
                  }
                  @if (connector.credential_kind === 'api_token' && connector.provider !== 'mcp') {
                    <sol-button
                      type="button"
                      variant="secondary"
                      [attr.aria-label]="credentialsAria(connector)"
                      (click)="openCredentials(connector)"
                    >
                      {{ text.credentialsOpen() }}
                    </sol-button>
                  }
                  @if (connector.provider === 'jira') {
                    <sol-button
                      type="button"
                      variant="ghost"
                      [attr.aria-label]="jiraImportAria(connector)"
                      (click)="openJiraImport(connector)"
                    >
                      {{ text.jiraImportOpen() }}
                    </sol-button>
                  }
                </div>
              </div>
            </sol-card>
          }
        </div>
      }
    </section>

    <!-- Drawer: crear conector -->
    <sol-drawer
      [open]="createOpen()"
      [title]="text.createTitle()"
      (closed)="createOpen.set(false)"
    >
      <div class="flex flex-col gap-4">
        <sol-select
          [label]="text.createProviderLabel()"
          [placeholder]="text.createProviderPlaceholder()"
          [options]="providerOptions"
          [formControl]="providerControl"
        ></sol-select>
        @if (createProviderRequired()) {
          <p class="text-xs text-danger">{{ text.createProviderRequired() }}</p>
        }

        @if (providerControl.value === 'mcp') {
          <sol-input
            [label]="text.mcpBaseUrlLabel()"
            [placeholder]="text.mcpBaseUrlPlaceholder()"
            [formControl]="mcpBaseUrlControl"
          ></sol-input>
          @if (mcpBaseUrlRequired()) {
            <p class="text-xs text-danger">{{ text.mcpBaseUrlRequired() }}</p>
          }
          <sol-input
            [label]="text.mcpTokenLabel()"
            [placeholder]="text.mcpTokenPlaceholder()"
            type="password"
            [formControl]="mcpTokenControl"
          ></sol-input>
        }

        @if (createError()) {
          <div
            role="alert"
            class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
          >
            {{ createError() }}
          </div>
        }

        <div class="flex items-center gap-2">
          <sol-button
            type="button"
            variant="primary"
            [disabled]="creating()"
            (click)="submitCreate()"
          >
            {{ creating() ? text.createSubmitting() : text.createSubmit() }}
          </sol-button>
          <sol-button type="button" variant="ghost" (click)="createOpen.set(false)">
            {{ text.createCancel() }}
          </sol-button>
        </div>
      </div>
    </sol-drawer>

    <!-- Drawer: credenciales api_token (GLPI / Jira) -->
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
            [disabled]="credentialsSubmitting()"
            (click)="submitCredentials()"
          >
            {{
              credentialsSubmitting()
                ? text.credentialsSubmitting()
                : text.credentialsSubmit()
            }}
          </sol-button>
          <sol-button type="button" variant="ghost" (click)="closeCredentials()">
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
        <sol-file-upload
          accept=".csv,.xlsx"
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
            (click)="submitJiraImport()"
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
  `,
})
export class ConnectionsComponent implements OnInit {
  private readonly connectorsService = inject(ConnectorsService);
  private readonly auth = inject(AuthService);
  private readonly i18n = inject(I18nService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  /** Textos estáticos de la vista resueltos por i18n (reactivos al idioma). */
  protected readonly text = {
    title: this.i18n.t('connectors.title'),
    subtitle: this.i18n.t('connectors.subtitle'),
    loading: this.i18n.t('connectors.loading'),
    bannerClose: this.i18n.t('shared.drawer.closeAria'),
    connect: this.i18n.t('connectors.connect'),
    accountsHeading: this.i18n.t('connectors.accounts.heading'),
    accountsEmpty: this.i18n.t('connectors.accounts.empty'),
    accountsRevoke: this.i18n.t('connectors.accounts.revoke'),
    accountsLoadError: this.i18n.t('connectors.accounts.loadError'),
    createOpen: this.i18n.t('connectors.create.open'),
    createTitle: this.i18n.t('connectors.create.title'),
    createProviderLabel: this.i18n.t('connectors.create.providerLabel'),
    createProviderPlaceholder: this.i18n.t('connectors.create.providerPlaceholder'),
    createProviderRequired: this.i18n.t('connectors.create.providerRequired'),
    createSubmit: this.i18n.t('connectors.create.submit'),
    createSubmitting: this.i18n.t('connectors.create.submitting'),
    createCancel: this.i18n.t('connectors.create.cancel'),
    mcpBaseUrlLabel: this.i18n.t('connectors.create.mcpBaseUrlLabel'),
    mcpBaseUrlPlaceholder: this.i18n.t('connectors.create.mcpBaseUrlPlaceholder'),
    mcpBaseUrlRequired: this.i18n.t('connectors.create.mcpBaseUrlRequired'),
    mcpTokenLabel: this.i18n.t('connectors.create.mcpTokenLabel'),
    mcpTokenPlaceholder: this.i18n.t('connectors.create.mcpTokenPlaceholder'),
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

  /** Cuentas conectadas por id de conector. */
  protected readonly accounts = signal<Map<string, ConnectedAccount[]>>(new Map());
  /** Ids de conector cuyas cuentas no se pudieron cargar. */
  protected readonly accountsError = signal<Set<string>>(new Set());

  protected readonly banner = signal<Banner | null>(null);

  // -- crear conector --------------------------------------------------------
  protected readonly createOpen = signal(false);
  protected readonly creating = signal(false);
  protected readonly createError = signal<string | null>(null);
  protected readonly createProviderRequired = signal(false);
  protected readonly mcpBaseUrlRequired = signal(false);

  protected readonly providerControl = new FormControl<string>('', {
    nonNullable: true,
    validators: [Validators.required],
  });
  protected readonly mcpBaseUrlControl = new FormControl<string>('', {
    nonNullable: true,
  });
  protected readonly mcpTokenControl = new FormControl<string>('', {
    nonNullable: true,
  });

  protected readonly providerOptions = PROVIDER_CATALOG.map((meta) => ({
    value: meta.provider,
    label: meta.label,
  }));

  // -- credenciales api_token -------------------------------------------------
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
    const target = this.credentialsFor();
    return target
      ? this.i18n.translate('connectors.credentials.title', {
          provider: providerLabel(target.provider),
        })
      : '';
  });

  // -- import de archivo Jira ---------------------------------------------------
  protected readonly jiraImportFor = signal<Connector | null>(null);
  protected readonly jiraFile = signal<File | null>(null);
  protected readonly jiraImporting = signal(false);
  protected readonly jiraImportError = signal<string | null>(null);
  protected readonly jiraImportResult = signal<JiraImportResult | null>(null);

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

  // -- flujo OAuth -----------------------------------------------------------

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

  protected connect(connector: Connector): void {
    const token = this.auth.token();
    if (!token) {
      this.banner.set({
        kind: 'error',
        text: this.i18n.translate('connectors.errors.session'),
      });
      return;
    }
    const url = this.connectorsService.authorizeUrl(
      connector.id,
      `${window.location.origin}/connections`,
      token,
    );
    window.location.assign(url);
  }

  // -- listado / cuentas -------------------------------------------------------

  private load(): void {
    this.loading.set(true);
    this.loadError.set(null);

    this.connectorsService.list().subscribe({
      next: (res) => {
        const list = res.data ?? [];
        this.connectors.set(list);
        this.loading.set(false);
        for (const connector of list) {
          this.loadAccounts(connector.id);
        }
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.status === 0
            ? this.i18n.translate('connectors.errors.network')
            : this.i18n.translate('connectors.errors.load'),
        );
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
        this.banner.set({
          kind: 'success',
          text: this.i18n.translate('connectors.accounts.revoked'),
        });
        this.loadAccounts(connector.id);
      },
      error: () => {
        this.banner.set({
          kind: 'error',
          text: this.i18n.translate('connectors.accounts.revokeError'),
        });
      },
    });
  }

  protected deleteConnector(connector: Connector): void {
    this.connectorsService.delete(connector.id).subscribe({
      next: () => {
        this.banner.set({
          kind: 'success',
          text: this.i18n.translate('connectors.delete.success'),
        });
        this.load();
      },
      error: () => {
        this.banner.set({
          kind: 'error',
          text: this.i18n.translate('connectors.delete.error'),
        });
      },
    });
  }

  // -- crear conector ------------------------------------------------------------

  protected openCreate(): void {
    this.providerControl.setValue('');
    this.mcpBaseUrlControl.setValue('');
    this.mcpTokenControl.setValue('');
    this.createError.set(null);
    this.createProviderRequired.set(false);
    this.mcpBaseUrlRequired.set(false);
    this.createOpen.set(true);
  }

  protected submitCreate(): void {
    const provider = this.providerControl.value;
    if (!provider) {
      this.createProviderRequired.set(true);
      return;
    }
    this.createProviderRequired.set(false);

    const meta = PROVIDER_CATALOG.find((p) => p.provider === provider);
    if (!meta) {
      return;
    }

    const payload: ConnectorCreatePayload = {
      provider: meta.provider,
      credential_kind: meta.credentialKind,
    };

    if (provider === 'mcp') {
      const baseUrl = this.mcpBaseUrlControl.value.trim();
      if (!baseUrl) {
        this.mcpBaseUrlRequired.set(true);
        return;
      }
      this.mcpBaseUrlRequired.set(false);
      payload.settings = { mcp: { base_url: baseUrl } };
      const token = this.mcpTokenControl.value.trim();
      if (token) {
        payload.token = token;
      } else {
        payload.credential_kind = 'none';
      }
    }

    this.createError.set(null);
    this.creating.set(true);
    this.connectorsService.create(payload).subscribe({
      next: () => {
        this.creating.set(false);
        this.createOpen.set(false);
        this.banner.set({
          kind: 'success',
          text: this.i18n.translate('connectors.create.success'),
        });
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.creating.set(false);
        this.createError.set(this.apiErrorMessage(err, 'connectors.errors.create'));
      },
    });
  }

  // -- credenciales api_token -------------------------------------------------

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
        this.banner.set({
          kind: 'success',
          text: this.i18n.translate('connectors.credentials.success'),
        });
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

  // -- import de archivo Jira ---------------------------------------------------

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
    if (err.status === 0) {
      return this.i18n.translate('connectors.errors.network');
    }
    const detail = err.error?.detail;
    if (typeof detail === 'string' && detail.length > 0) {
      return detail;
    }
    return this.i18n.translate(fallbackKey);
  }
}
