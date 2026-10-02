import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { SolButtonComponent } from '@solercia/ui';
import { AuthService } from '@features/auth/auth.service';
import { apiBase } from '@shared/api/api.config';
import { I18nService } from '@shared/i18n';
import { SolCardComponent } from '@shared/ui';
import { SolInputComponent } from '@shared/ui';

@Component({
  selector: 'sol-login',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    SolCardComponent,
    SolInputComponent,
  ],
  template: `
    <!-- Rendered outside the authenticated shell: the page owns its full-height
         centering and its side padding. -->
    <div class="flex min-h-dvh items-center justify-center px-4 py-6">
      <div class="w-full max-w-sm">
        <sol-card>
          <div class="mb-6 text-center">
            <div
              class="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-xl bg-brand text-brand-fg text-lg font-bold"
              aria-hidden="true"
            >
              S
            </div>
            <h1 class="text-xl font-semibold text-text">{{ text.title() }}</h1>
            <p class="mt-1 text-sm text-muted">
              {{ text.subtitle() }}
            </p>
          </div>

          <form
            [formGroup]="form"
            (ngSubmit)="onSubmit()"
            class="flex flex-col gap-4"
            novalidate
          >
            <div>
              <sol-input
                [label]="text.emailLabel()"
                type="email"
                [placeholder]="text.emailPlaceholder()"
                autocomplete="email"
                formControlName="email"
              ></sol-input>
              @if (showError('email')) {
                <p class="mt-1 text-xs text-danger">
                  {{ emailError() }}
                </p>
              }
            </div>

            <div>
              <sol-input
                [label]="text.passwordLabel()"
                type="password"
                [placeholder]="text.passwordPlaceholder()"
                autocomplete="current-password"
                formControlName="password"
              ></sol-input>
              @if (showError('password')) {
                <p class="mt-1 text-xs text-danger">
                  {{ text.passwordRequired() }}
                </p>
              }
            </div>

            @if (errorMessage()) {
              <div
                role="alert"
                class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
              >
                {{ errorMessage() }}
              </div>
            }

            <sol-button
              class="w-full"
              type="submit"
              variant="primary"
              [disabled]="loading()"
              [loading]="loading()"
            >
              {{ loading() ? text.submitting() : text.submit() }}
            </sol-button>
          </form>

          <div class="my-4 flex items-center gap-3" aria-hidden="true">
            <span class="h-px flex-1 bg-border"></span>
            <span class="text-xs text-muted">{{ text.ssoDivider() }}</span>
            <span class="h-px flex-1 bg-border"></span>
          </div>

          <sol-button
            class="w-full"
            type="button"
            variant="secondary"
            (clicked)="onSsoLogin()"
          >
            {{ text.ssoButton() }}
          </sol-button>

          <p
            class="mt-5 rounded-lg border border-border bg-page px-3 py-2 text-center text-xs text-muted"
          >
            {{ text.demoLabel() }}
            <span class="font-medium text-text">admin&#64;solercia.com</span>
            /
            <span class="font-medium text-text">Admin123*</span>
          </p>
        </sol-card>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  /** Textos de la vista resueltos por i18n (reactivos al cambio de idioma). */
  protected readonly text = {
    title: this.i18n.t('auth.login.title'),
    subtitle: this.i18n.t('auth.login.subtitle'),
    emailLabel: this.i18n.t('auth.login.emailLabel'),
    emailPlaceholder: this.i18n.t('auth.login.emailPlaceholder'),
    passwordLabel: this.i18n.t('auth.login.passwordLabel'),
    passwordPlaceholder: this.i18n.t('auth.login.passwordPlaceholder'),
    passwordRequired: this.i18n.t('auth.login.errors.passwordRequired'),
    ssoButton: this.i18n.t('auth.login.ssoButton'),
    ssoDivider: this.i18n.t('auth.login.ssoDivider'),
    submit: this.i18n.t('auth.login.submit'),
    submitting: this.i18n.t('auth.login.submitting'),
    demoLabel: this.i18n.t('auth.login.demoLabel'),
  } as const;

  protected readonly loading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);

  protected readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });

  protected showError(control: 'email' | 'password'): boolean {
    const c = this.form.controls[control];
    return c.invalid && (c.touched || c.dirty);
  }

  protected emailError(): string {
    const c = this.form.controls.email;
    if (c.hasError('required')) {
      return this.i18n.translate('auth.login.errors.emailRequired');
    }
    if (c.hasError('email')) {
      return this.i18n.translate('auth.login.errors.emailInvalid');
    }
    return '';
  }

  /**
   * Redirects the browser (full navigation, NOT an `HttpClient` call) to
   * the backend's SSO login route. The backend handles the whole OIDC
   * Authorization Code + PKCE handshake and lands back on
   * `/auth/callback` (design.md D5).
   */
  protected onSsoLogin(): void {
    window.location.href = `${apiBase}/auth/sso/keycloak/login`;
  }

  protected onSubmit(): void {
    this.errorMessage.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const { email, password } = this.form.getRawValue();
    this.loading.set(true);

    this.auth.login(email, password).subscribe({
      next: () => {
        this.loading.set(false);
        void this.router.navigate(['/projects']);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        if (err.status === 401) {
          this.errorMessage.set(
            this.i18n.translate('auth.login.errors.invalidCredentials'),
          );
        } else if (err.status === 0) {
          this.errorMessage.set(
            this.i18n.translate('auth.login.errors.network'),
          );
        } else {
          this.errorMessage.set(
            this.i18n.translate('auth.login.errors.generic'),
          );
        }
      },
    });
  }
}
