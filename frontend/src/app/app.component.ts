import { ChangeDetectionStrategy, Component, effect, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ThemeService } from '@solercia/ui';
import {
  STUDIO_LOADER_ANIMATIONS,
  STUDIO_LOADER_PRESENTATIONS,
  STUDIO_TABLE_STYLES,
  type ThemeMetaExtras,
} from '@features/theme/theme-meta-extras';
import { SolAlertCenterComponent } from '@widgets/alert-center';

/**
 * Theme extras the shell applies on its own DOCUMENT (the library does not
 * resolve them; `meta.favicon` and `meta.fonts` are handled by ThemeService):
 *
 *  - `meta.tableStyle` → `data-sol-table` on <html> (styles.scss paints sol-data-table)
 *  - `meta.loader`     → `--sol-loader-image`, `--sol-loader-animation-name` and
 *                        `data-sol-loader` on <html> (styles.scss: .sol-loader__spinner)
 *
 * Everything is validated against the model lists: a persisted theme is never
 * applied blindly. Safe URL: http(s) or absolute path, without quotes,
 * parentheses or spaces that would break the CSS `url(...)`.
 */
const SAFE_IMAGE_URL = /^(https?:\/\/|\/)[^\s"')]+$/;
const LOADER_IMAGE_MAX_LENGTH = 500;

function applyTableStyle(tableStyle: ThemeMetaExtras['tableStyle']): void {
  const root = document.documentElement;
  if (tableStyle && STUDIO_TABLE_STYLES.includes(tableStyle)) {
    root.setAttribute('data-sol-table', tableStyle);
  } else {
    root.removeAttribute('data-sol-table');
  }
}

function applyLoader(loader: ThemeMetaExtras['loader']): void {
  const root = document.documentElement;
  root.style.removeProperty('--sol-loader-image');
  root.style.removeProperty('--sol-loader-animation-name');
  if (!loader) {
    root.removeAttribute('data-sol-loader');
    return;
  }
  const image = loader.image?.trim() ?? '';
  if (image && image.length <= LOADER_IMAGE_MAX_LENGTH && SAFE_IMAGE_URL.test(image)) {
    root.style.setProperty('--sol-loader-image', `url("${image}")`);
  }
  if (STUDIO_LOADER_ANIMATIONS.includes(loader.animation)) {
    root.style.setProperty(
      '--sol-loader-animation-name',
      loader.animation === 'none' ? 'none' : `sol-loader-${loader.animation}`,
    );
  }
  root.setAttribute(
    'data-sol-loader',
    STUDIO_LOADER_PRESENTATIONS.includes(loader.presentation) ? loader.presentation : 'current',
  );
}

/**
 * Application root: the routed content plus the app-wide alert center. The
 * authenticated layout (header, sidebar, session actions) lives in the shell
 * page (`pages/shell`), mounted as the parent route of every authenticated
 * view; login and the error pages render bare.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, SolAlertCenterComponent],
  template: `
    <router-outlet />

    <!-- Transient feedback (alerts) for the whole app; pages only call AlertService. -->
    <sol-alert-center />
  `,
})
export class AppComponent {
  private readonly theme = inject(ThemeService);

  constructor() {
    // Theme extras the library does not resolve (table preset, page loader).
    effect(() => {
      const active = this.theme.activeTheme();
      if (!active) return;

      const extras = active.meta as typeof active.meta & ThemeMetaExtras;
      applyTableStyle(extras.tableStyle);
      applyLoader(extras.loader);
    });
  }
}
