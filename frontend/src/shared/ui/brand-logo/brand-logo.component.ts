import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import type { ThemeLogo } from '@solercia/ui';

/**
 * Prefixes of the app's OWN Boki logo assets. A theme pointing at one of these
 * gets the inline, theme-aware SVG below; any other URL is a tenant-supplied
 * image and is rendered untouched with `<img>`.
 */
const BOKI_LOGO_ASSET = '/assets/logos/boki-logo';

/**
 * Brand logo.
 *
 * The packaged Boki logo used to be a flat `<img>` pointing at an SVG file with
 * hardcoded brand colors (blue face, lime eyes, blue wordmark). An `<img>` is an
 * isolated document, so CSS custom properties never reached it and the logo kept
 * its blue on every tenant palette — jarring next to, say, a pink sidebar.
 *
 * Rendering that same artwork INLINE lets it consume the theme like any other
 * `sol-*` component:
 *
 * - face      → `--sol-color-primary` (the tenant's brand color)
 * - eyes/smile→ `--sol-bg-surface` (always readable on top of the primary)
 * - wordmark  → `currentColor`, so it inherits the exact color of the surrounding
 *               text, and `--sol-font-display` so it matches the theme typography
 *
 * Tenants with their own logo keep the plain `<img>` path — their artwork is not
 * ours to recolor.
 */
@Component({
  selector: 'sol-brand-logo',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (isPackagedLogo()) {
      <svg
        class="sol-brand-logo__svg"
        viewBox="0 0 150 40"
        role="img"
        [attr.aria-label]="altText()"
        [style.--sol-brand-logo-width]="widthPx()"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect x="2" y="2" width="36" height="36" rx="12" fill="var(--sol-color-primary)" />
        <circle cx="14" cy="18" r="3" fill="var(--sol-bg-surface)" />
        <circle cx="26" cy="18" r="3" fill="var(--sol-bg-surface)" />
        <path
          d="M12 26 Q 20 32 28 26"
          stroke="var(--sol-bg-surface)"
          stroke-width="2.5"
          fill="none"
          stroke-linecap="round"
        />
        <text
          class="sol-brand-logo__wordmark"
          x="48"
          y="27"
          font-size="22"
          letter-spacing="-0.5"
          fill="currentColor"
        >
          Boki
        </text>
      </svg>
    } @else {
      <img
        class="sol-brand-logo__img"
        [src]="url()"
        [alt]="altText()"
        [style.--sol-brand-logo-width]="widthPx()"
      />
    }
  `,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      /* Same contrast as the surrounding copy — the wordmark rides on
         currentColor, so the host decides how loud the brand reads. */
      color: var(--sol-color-text-primary);
    }

    .sol-brand-logo__svg,
    .sol-brand-logo__img {
      display: block;
      /* The CONTAINER (header, preview, ...) sets the available HEIGHT via its
         own CSS on the host (e.g. .sol-header__logo { height: 32px }); width
         is always DERIVED, never forced to an exact value. --sol-brand-logo-
         width is the Theme Studio slider value (60-200px); --sol-brand-logo-
         max-width is an optional responsive ceiling the container can impose
         from outside (e.g. the header on mobile) — the SMALLER of the two
         wins. Because the other axis stays auto, the browser derives it from
         the artwork's own ratio: never deformed, and the host — which sizes to
         its content — never measures more than the artwork actually draws (no
         ghost box). object-fit is a safety net for the rare case both axes
         end up fixed at once. */
      width: auto;
      height: 100%;
      max-width: min(var(--sol-brand-logo-width, 120px), var(--sol-brand-logo-max-width, 9999px));
      object-fit: contain;
    }

    .sol-brand-logo__wordmark {
      font-family: var(--sol-font-display, var(--sol-font-family));
      font-weight: var(--sol-display-weight, var(--sol-font-weight-bold, 700));
      letter-spacing: var(--sol-display-tracking, -0.5px);
    }
  `,
})
export class SolBrandLogoComponent {
  /** Effective theme logo (already mode-resolved and sanitized by ThemeService). */
  readonly logo = input.required<ThemeLogo>();

  protected readonly url = computed(() => this.logo().url);
  protected readonly altText = computed(() => this.logo().altText);
  protected readonly width = computed(() => this.logo().width ?? 120);
  /** `width()` as a CSS length, written into `--sol-brand-logo-width` (see the stylesheet). */
  protected readonly widthPx = computed(() => `${this.width()}px`);

  /** True when the theme points at the app's own Boki artwork, which we may recolor. */
  protected readonly isPackagedLogo = computed(() => this.url().includes(BOKI_LOGO_ASSET));
}
