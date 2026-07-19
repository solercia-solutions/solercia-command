import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '@features/auth/auth.service';
import { I18nService } from '@shared/i18n';
import { SolCardComponent } from '@shared/ui';

/**
 * Landing page the backend's SSO callback redirects to after setting the
 * httpOnly refresh cookie (design.md D5, R7). The access token NEVER
 * travels in this URL: this page exchanges the cookie for one by calling
 * `refresh()` (POST /auth/refresh, withCredentials) and then `me()` — the
 * same exchange the auth interceptor performs on a 401, just triggered
 * from a different entry point (SSO instead of local credentials).
 */
@Component({
  selector: 'sol-auth-callback',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [SolCardComponent],
  template: `
    <div class="flex min-h-[70vh] items-center justify-center">
      <div class="w-full max-w-sm">
        <sol-card>
          <div class="flex flex-col items-center gap-3 py-4 text-center">
            @if (errorMessage()) {
              <p role="alert" class="text-sm text-danger">
                {{ errorMessage() }}
              </p>
            } @else {
              <p class="text-sm text-muted">{{ text.completing() }}</p>
            }
          </div>
        </sol-card>
      </div>
    </div>
  `,
})
export class AuthCallbackComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);

  protected readonly text = {
    completing: this.i18n.t('auth.callback.completing'),
  } as const;

  protected readonly errorMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.auth.refresh().subscribe({
      next: () => {
        this.auth.me().subscribe({
          next: () => void this.router.navigate(['/projects']),
          error: () => this.showError(),
        });
      },
      error: () => this.showError(),
    });
  }

  private showError(): void {
    this.errorMessage.set(this.i18n.translate('auth.callback.error'));
    setTimeout(() => void this.router.navigate(['/login']), 2500);
  }
}
