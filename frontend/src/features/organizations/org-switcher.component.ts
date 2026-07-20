import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { OrganizationsService } from '@entities/organization/organizations.service';
import { OrganizationMembership } from '@entities/organization/organization.model';
import { I18nService } from '@shared/i18n';
import { ActiveOrgStore } from './active-org.store';

/**
 * Selector de empresa activa proyectado en `[header-actions]` (app.component).
 *
 * Lista las empresas del usuario (`GET /organizations/mine`) y resalta la
 * activa. Con una sola empresa se muestra como texto simple, sin obligar a
 * elegir (frontend-org-switcher, "Usuario con una sola empresa"). Al elegir
 * una distinta, primero VERIFICA el acceso con `GET /organizations/{id}`
 * (independiente del header activo — cualquier miembro puede leerla) antes
 * de persistir y recargar; si la verificación falla (red o 403/404), se
 * muestra un error y el layout conserva el contexto de la empresa anterior
 * sin invocar el cambio (Scenario "Falla al cambiar de empresa conserva el
 * contexto anterior").
 */
@Component({
  selector: 'sol-org-switcher',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading()) {
      <span class="text-xs text-muted">{{ text.loading() }}</span>
    } @else if (memberships().length === 0) {
      <span class="text-xs text-muted">{{ text.empty() }}</span>
    } @else if (memberships().length === 1) {
      <span
        class="inline-flex h-9 items-center gap-2 rounded-lg border border-border
               bg-surface px-3 text-sm font-medium text-text"
      >
        {{ memberships()[0].organization.name }}
      </span>
    } @else {
      <div class="relative">
        <button
          type="button"
          (click)="toggleOpen()"
          [attr.aria-expanded]="open()"
          [attr.aria-label]="text.triggerAria()"
          class="inline-flex h-9 items-center gap-2 rounded-lg border border-border
                 bg-surface px-3 text-sm font-medium text-text transition-colors
                 hover:bg-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
        >
          <span>{{ activeName() }}</span>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        @if (open()) {
          <div
            class="absolute right-0 top-full z-40 mt-2 w-64 rounded-lg border border-border
                   bg-surface p-1 shadow-lg"
            role="listbox"
            [attr.aria-label]="text.toggle()"
          >
            @for (membership of memberships(); track membership.organization.id) {
              <button
                type="button"
                role="option"
                [attr.aria-selected]="membership.organization.id === activeOrgId()"
                (click)="selectOrganization(membership)"
                [disabled]="switching()"
                class="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2
                       text-left text-sm text-text transition-colors hover:bg-sunken
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/55"
              >
                <span class="truncate">{{ membership.organization.name }}</span>
                <span class="shrink-0 text-xs text-muted">{{ roleLabel(membership.role) }}</span>
              </button>
            }
          </div>
        }
      </div>
    }

    @if (error()) {
      <p role="alert" class="mt-1 text-xs text-danger">{{ error() }}</p>
    }
  `,
})
export class OrgSwitcherComponent implements OnInit {
  private readonly service = inject(OrganizationsService);
  private readonly activeOrgStore = inject(ActiveOrgStore);
  private readonly i18n = inject(I18nService);

  protected readonly text = {
    loading: this.i18n.t('orgSwitcher.loading'),
    empty: this.i18n.t('orgSwitcher.empty'),
    triggerAria: this.i18n.t('orgSwitcher.triggerAria'),
    toggle: this.i18n.t('orgSwitcher.toggle'),
  } as const;

  protected readonly loading = signal(true);
  protected readonly open = signal(false);
  protected readonly switching = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly memberships = signal<OrganizationMembership[]>([]);

  /** Empresa activa: la explícitamente elegida o, en su defecto, la primera
   * de la lista (proxy visual del fallback del backend, nunca escrita). */
  protected readonly activeOrgId = computed<string | null>(
    () =>
      this.activeOrgStore.activeOrgId() ??
      this.memberships()[0]?.organization.id ??
      null,
  );

  protected readonly activeName = computed<string>(() => {
    const id = this.activeOrgId();
    const found = this.memberships().find(
      (membership) => membership.organization.id === id,
    );
    return found?.organization.name ?? '';
  });

  ngOnInit(): void {
    this.load();
  }

  protected toggleOpen(): void {
    this.open.update((value) => !value);
  }

  protected roleLabel(role: OrganizationMembership['role']): string {
    return this.i18n.translate(`orgSwitcher.roles.${role}`);
  }

  protected selectOrganization(membership: OrganizationMembership): void {
    this.open.set(false);
    if (membership.organization.id === this.activeOrgId()) {
      return;
    }

    this.error.set(null);
    this.switching.set(true);

    // Verifica el acceso ANTES de persistir/recargar: GET /organizations/{id}
    // solo exige membresía (no depende del header activo), así que una
    // falla aquí es una señal real de red o de acceso perdido — nunca del
    // header vigente.
    this.service.get(membership.organization.id).subscribe({
      next: () => {
        this.switching.set(false);
        this.activeOrgStore.setActiveOrg(membership.organization.id);
      },
      error: (err: HttpErrorResponse) => {
        this.switching.set(false);
        this.error.set(this.messageFor(err));
      },
    });
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.mine().subscribe({
      next: (res) => {
        this.memberships.set(res.data ?? []);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(this.messageFor(err, 'orgSwitcher.errors.load'));
      },
    });
  }

  private messageFor(
    err: HttpErrorResponse,
    fallbackKey = 'orgSwitcher.errors.switchFailed',
  ): string {
    if (err.status === 0) {
      return this.i18n.translate('orgSwitcher.errors.network');
    }
    return this.i18n.translate(fallbackKey);
  }
}
