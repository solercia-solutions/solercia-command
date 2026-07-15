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
import { I18nService } from '@shared/i18n';
import { CardComponent } from '@shared/ui/card.component';
import { TextInputComponent } from '@shared/ui/text-input.component';

@Component({
  selector: 'bk-login',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    SolButtonComponent,
    CardComponent,
    TextInputComponent,
  ],
  template: `
    <div class="flex min-h-[70vh] items-center justify-center">
      <div class="w-full max-w-sm">
        <bk-card>
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
              <bk-text-input
                [label]="text.emailLabel()"
                type="email"
                [placeholder]="text.emailPlaceholder()"
                autocomplete="email"
                formControlName="email"
              ></bk-text-input>
              @if (showError('email')) {
                <p class="mt-1 text-xs text-danger">
                  {{ emailError() }}
                </p>
              }
            </div>

            <div>
              <bk-text-input
                [label]="text.passwordLabel()"
                type="password"
                [placeholder]="text.passwordPlaceholder()"
                autocomplete="current-password"
                formControlName="password"
              ></bk-text-input>
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

          <p
            class="mt-5 rounded-lg border border-border bg-page px-3 py-2 text-center text-xs text-muted"
          >
            {{ text.demoLabel() }}
            <span class="font-medium text-text">admin&#64;solercia.com</span>
            /
            <span class="font-medium text-text">Admin123*</span>
          </p>
        </bk-card>
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
