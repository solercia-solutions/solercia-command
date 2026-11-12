import type { SolIconName } from '@shared/ui';

/**
 * Translates the dynamic-menu icon vocabulary (`menus.icon`, backend) into
 * the `@solercia/ui` icon-registry name consumed by `<sol-icon>`.
 *
 * Ported from boki-front (`widgets/sidebar/ui/sidebar-icons.ts`). Aliases are
 * declared only where the backend vocabulary differs from the registry; any
 * key without an alias passes through unchanged and, if it is not in
 * `ICON_REGISTRY`, falls back to `sol-icon`'s native generic glyph.
 *
 * Host-specific aliases: the seeded menu icons in this project (lucide-style
 * names) are mapped to their closest registry equivalent. `bar-chart-3` and
 * `trending-up` intentionally share the `bar-chart` glyph (two chart-flavored
 * items, one visual) — same precedent as boki's `question`/`help-circle`.
 */
const NAV_ICON_ALIASES: Readonly<Record<string, SolIconName>> = {
  question: 'help-circle',
  'folder-kanban': 'view-columns',
  'bar-chart-3': 'bar-chart',
  'trending-up': 'bar-chart',
  shield: 'lock-closed',
  'list-tree': 'layers',
  'building-2': 'building',
  plug: 'arrows-right-left',
  'ellipsis-horizontal': 'ellipsis-vertical',
  palette: 'sparkles',
  'clipboard-list': 'clipboard',
};

/**
 * Returns the registry icon name for a menu icon key. Nullish keys resolve
 * to the empty string so `sol-icon` renders its generic fallback glyph.
 */
export function getNavIconName(icon: string | null | undefined): string {
  if (!icon) {
    return '';
  }
  return NAV_ICON_ALIASES[icon] ?? icon;
}
