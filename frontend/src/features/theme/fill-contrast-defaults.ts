import type { ThemeFile, ThemeMode } from '@shared/ui';

const MODES: readonly ThemeMode[] = ['light', 'dark'];

/**
 * Fills the `*Contrast` semantic colors an organization theme leaves out with
 * the bundled default's value for the same mode.
 *
 * Without it, @solercia/ui emits its library fallback (`#1E293B`, dark text)
 * for a missing `secondaryContrast`, which reads poorly on the default violet
 * secondary of the light mode. Values the organization did set are kept; the
 * input is never mutated.
 */
export function fillContrastDefaults(file: ThemeFile, defaults: ThemeFile): ThemeFile {
  let modes = file.modes;
  for (const mode of MODES) {
    const own = file.modes[mode]?.semantic?.color as Record<string, string> | undefined;
    const base = defaults.modes[mode]?.semantic?.color as Record<string, string> | undefined;
    if (!own || !base) {
      continue;
    }
    const missing = Object.entries(base).filter(
      ([key]) => key.endsWith('Contrast') && !(key in own),
    );
    if (missing.length === 0) {
      continue;
    }
    const config = file.modes[mode];
    modes = {
      ...modes,
      [mode]: {
        ...config,
        semantic: {
          ...config.semantic,
          color: { ...own, ...Object.fromEntries(missing) },
        },
      },
    };
  }
  return modes === file.modes ? file : { ...file, modes };
}
