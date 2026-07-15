/**
 * bk-rich-editor — Editor de texto enriquecido para Solercia PM
 * =============================================================
 * Basado en contenteditable, sin dependencias externas. Angular 20 standalone.
 *
 * API PÚBLICA
 * -----------
 * Inputs:
 *   label?            : string          — Etiqueta visible sobre el editor
 *   placeholder?      : string          — Texto guía cuando está vacío (default: 'Escribe aquí...')
 *   minHeight?        : string          — Altura mínima del área (default: '120px')
 *   mentionableUsers  : MentionUser[]   — {id: string, name: string}[] para autocompletado '@'
 *   linkableTasks     : LinkableTask[]  — {key: string, title: string}[] para autocompletado '#'
 *
 * Outputs:
 *   mentionsChange    : EventEmitter<string[]>  — IDs de usuarios mencionados (se emite en cada cambio)
 *   taskLinksChange   : EventEmitter<string[]>  — Keys de tareas enlazadas (ej: 'SDM-12')
 *
 * ControlValueAccessor:
 *   Emite y recibe HTML sanitizado. Compatible con [(ngModel)] y formControl/formControlName.
 *
 * Toolbar disponible:
 *   Negrita · Itálica · Lista con viñetas · Lista numerada · Enlace (con diálogo inline)
 *
 * Autocompletado:
 *   '@'  → muestra lista de mentionableUsers filtrada por nombre; inserta chip azul data-mention-id
 *   '#'  → muestra lista de linkableTasks filtrada por key/título; inserta chip verde data-task-key
 *   Navegación: flechas ↑↓, Enter para seleccionar, Escape para cerrar.
 *
 * Sanitización anti-XSS:
 *   Whitelist de tags: p, br, b, strong, i, em, ul, ol, li, a, span, div
 *   Elimina: script, style, on*, href=javascript:, href=data:
 *   Se aplica en paste y en la salida hacia onChange().
 *
 * TODO v2:
 *   - Soporte de tablas (inserción, edición de celdas)
 *   - Imágenes (upload + inserción inline)
 *   Si tablas/imágenes se vuelven requisito duro, evaluar migrar a Tiptap (licencia MIT)
 *   en lugar de extender este componente — la paridad con ProseMirror no vale la pena
 *   implementarla a mano.
 *
 * Uso básico:
 *   <bk-rich-editor
 *     label="Descripción"
 *     placeholder="Describe la tarea..."
 *     [mentionableUsers]="teamMembers"
 *     [linkableTasks]="projectTasks"
 *     (mentionsChange)="onMentions($event)"
 *     (taskLinksChange)="onTaskLinks($event)"
 *     [(ngModel)]="task.description"
 *   />
 */

import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnDestroy,
  Output,
  ViewChild,
  ViewEncapsulation,
  computed,
  forwardRef,
  signal,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

// ─── Tipos públicos ────────────────────────────────────────────────────────────

export interface MentionUser {
  id: string;
  name: string;
}

export interface LinkableTask {
  key: string;   // Ej: 'SDM-12'
  title: string;
}

// ─── Sanitizador anti-XSS ─────────────────────────────────────────────────────

const ALLOWED_TAGS = new Set([
  'P', 'BR', 'B', 'STRONG', 'I', 'EM',
  'UL', 'OL', 'LI', 'A', 'SPAN', 'DIV',
]);

const ALLOWED_ATTRS: Record<string, string[]> = {
  A:    ['href', 'target', 'rel'],
  SPAN: ['class', 'data-mention-id', 'data-task-key', 'contenteditable', 'style'],
};

function _sanitizeNode(node: Node): void {
  const children = Array.from(node.childNodes);
  for (const child of children) {
    if (child.nodeType === Node.TEXT_NODE) continue;

    if (child.nodeType === Node.ELEMENT_NODE) {
      const el = child as Element;

      if (!ALLOWED_TAGS.has(el.tagName)) {
        // Reemplazar con contenido de texto plano (sin tags hijos)
        node.replaceChild(document.createTextNode(el.textContent ?? ''), el);
        continue;
      }

      // Eliminar atributos no permitidos
      const allowed = ALLOWED_ATTRS[el.tagName] ?? [];
      const toRemove: string[] = [];
      for (let i = 0; i < el.attributes.length; i++) {
        const attr = el.attributes[i];
        if (!allowed.includes(attr.name)) toRemove.push(attr.name);
      }
      toRemove.forEach(a => el.removeAttribute(a));

      // Validar href
      if (el.tagName === 'A') {
        const href = el.getAttribute('href') ?? '';
        if (/^javascript:/i.test(href) || /^data:/i.test(href)) {
          el.removeAttribute('href');
        }
      }

      _sanitizeNode(el);
    } else {
      // Eliminar nodos que no sean texto ni elemento (comments, etc.)
      node.removeChild(child);
    }
  }
}

function sanitizeHtml(html: string): string {
  if (!html?.trim()) return '';
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  _sanitizeNode(doc.body);
  return doc.body.innerHTML;
}

// ─── Extractores de metadata ───────────────────────────────────────────────────

function extractMentionIds(html: string): string[] {
  if (!html) return [];
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return Array.from(doc.querySelectorAll('[data-mention-id]'))
    .map(el => el.getAttribute('data-mention-id')!)
    .filter(Boolean);
}

function extractTaskKeys(html: string): string[] {
  if (!html) return [];
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return Array.from(doc.querySelectorAll('[data-task-key]'))
    .map(el => el.getAttribute('data-task-key')!)
    .filter(Boolean);
}

// ─── Componente ───────────────────────────────────────────────────────────────

@Component({
  selector: 'bk-rich-editor',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  // ViewEncapsulation.None para que los estilos de chips apliquen a nodos
  // insertados imperativamente (execCommand / Range API).
  encapsulation: ViewEncapsulation.None,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => RichEditorComponent),
      multi: true,
    },
  ],
  styles: [`
    /* Estilos de chips: se aplican a nodos insertados dinámicamente */
    .bk-mention-chip {
      display: inline-flex;
      align-items: center;
      padding: 1px 6px;
      border-radius: 4px;
      background-color: rgb(var(--sp-brand) / 0.12);
      color: rgb(var(--sp-brand));
      font-size: 0.875rem;
      font-weight: 500;
      cursor: default;
      user-select: none;
      line-height: 1.5;
    }
    .bk-task-chip {
      display: inline-flex;
      align-items: center;
      padding: 1px 6px;
      border-radius: 4px;
      background-color: rgb(var(--sp-success) / 0.12);
      color: rgb(var(--sp-success));
      font-size: 0.875rem;
      font-weight: 600;
      cursor: default;
      user-select: none;
      font-family: ui-monospace, monospace;
      line-height: 1.5;
    }
    /* Estilos del contenido del editor */
    .bk-rich-editor-content {
      line-height: 1.6;
      outline: none;
    }
    .bk-rich-editor-content:empty::before {
      content: attr(data-placeholder);
      color: rgb(var(--sp-muted));
      pointer-events: none;
    }
    .bk-rich-editor-content a {
      color: rgb(var(--sp-brand));
      text-decoration: underline;
      cursor: pointer;
    }
    .bk-rich-editor-content ul {
      list-style: disc;
      padding-left: 1.5rem;
      margin: 0.25rem 0;
    }
    .bk-rich-editor-content ol {
      list-style: decimal;
      padding-left: 1.5rem;
      margin: 0.25rem 0;
    }
    .bk-rich-editor-content li {
      margin: 0.1rem 0;
    }
    .bk-rich-editor-content p {
      margin: 0.25rem 0;
    }
    /* Deshabilitar cuando está en modo readonly */
    .bk-rich-editor-content[contenteditable="false"] {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `],
  template: `
    <div>
      @if (label) {
        <span class="mb-1.5 block text-sm font-medium text-text">{{ label }}</span>
      }

      <!-- Contenedor con foco visual (el popover se posiciona relativo a este div) -->
      <div
        class="relative rounded-lg border border-border bg-surface transition-colors
               focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/40"
      >
        <!-- ── Toolbar ──────────────────────────────────────────────────── -->
        <div
          class="flex items-center gap-0.5 border-b border-border px-2 py-1.5"
          role="toolbar"
          aria-label="Herramientas de formato"
        >
          <!-- Negrita -->
          <button
            type="button"
            (mousedown)="execFormat($event, 'bold')"
            [class]="toolbarBtnClass(isBold())"
            aria-label="Negrita"
            title="Negrita (Ctrl+B)"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M15.6 10.79c.97-.67 1.65-1.77 1.65-2.79 0-2.26-1.75-4-4-4H7v14h7.04c2.09 0 3.71-1.7 3.71-3.79 0-1.52-.86-2.82-2.15-3.42zM10 6.5h3c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-3v-3zm3.5 9H10v-3h3.5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5z"/>
            </svg>
          </button>

          <!-- Itálica -->
          <button
            type="button"
            (mousedown)="execFormat($event, 'italic')"
            [class]="toolbarBtnClass(isItalic())"
            aria-label="Itálica"
            title="Itálica (Ctrl+I)"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M10 4v3h2.21l-3.42 8H6v3h8v-3h-2.21l3.42-8H18V4h-8z"/>
            </svg>
          </button>

          <div class="mx-1 h-4 w-px bg-border" role="separator" aria-hidden="true"></div>

          <!-- Lista con viñetas -->
          <button
            type="button"
            (mousedown)="execFormat($event, 'insertUnorderedList')"
            [class]="toolbarBtnClass(false)"
            aria-label="Lista con viñetas"
            title="Lista con viñetas"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M4 10.5c-.83 0-1.5.67-1.5 1.5s.67 1.5 1.5 1.5 1.5-.67 1.5-1.5-.67-1.5-1.5-1.5zm0-6c-.83 0-1.5.67-1.5 1.5S3.17 7.5 4 7.5 5.5 6.83 5.5 6 4.83 4.5 4 4.5zm0 12c-.83 0-1.5.68-1.5 1.5s.68 1.5 1.5 1.5 1.5-.68 1.5-1.5-.67-1.5-1.5-1.5zM7 19h14v-2H7v2zm0-6h14v-2H7v2zm0-8v2h14V5H7z"/>
            </svg>
          </button>

          <!-- Lista numerada -->
          <button
            type="button"
            (mousedown)="execFormat($event, 'insertOrderedList')"
            [class]="toolbarBtnClass(false)"
            aria-label="Lista numerada"
            title="Lista numerada"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M2 17h2v.5H3v1h1v.5H2v1h3v-4H2v1zm1-9h1V4H2v1h1v3zm-1 3h1.8L2 13.1v.9h3v-1H3.2L5 10.9V10H2v1zm5-6v2h14V5H7zm0 14h14v-2H7v2zm0-6h14v-2H7v2z"/>
            </svg>
          </button>

          <div class="mx-1 h-4 w-px bg-border" role="separator" aria-hidden="true"></div>

          <!-- Enlace -->
          <button
            type="button"
            (mousedown)="openLinkDialog($event)"
            [class]="toolbarBtnClass(showLinkDialog())"
            aria-label="Insertar enlace"
            title="Insertar enlace"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/>
            </svg>
          </button>
        </div>

        <!-- ── Área de edición ──────────────────────────────────────────── -->
        <div
          #editor
          contenteditable="true"
          [attr.data-placeholder]="placeholder"
          [style.min-height]="minHeight"
          (input)="onEditorInput()"
          (keydown)="onKeyDown($event)"
          (paste)="onPaste($event)"
          (blur)="onBlur()"
          (mouseup)="onSelectionChange()"
          (keyup)="onSelectionChange()"
          class="bk-rich-editor-content px-3 py-2.5 text-sm text-text"
          role="textbox"
          aria-multiline="true"
          [attr.aria-label]="label || placeholder"
          [attr.aria-disabled]="disabled()"
        ></div>

        <!-- ── Popover de menciones (@) ────────────────────────────────── -->
        @if (showMentionPopover() && filteredUsers().length > 0) {
          <div
            class="absolute z-50 min-w-48 overflow-hidden rounded-lg border border-border
                   bg-surface shadow-lg"
            [style.top.px]="popoverTop()"
            [style.left.px]="popoverLeft()"
            role="listbox"
            aria-label="Mencionar usuario"
          >
            @for (user of filteredUsers(); track user.id; let i = $index) {
              <button
                type="button"
                (mousedown)="selectMention($event, i)"
                [class]="popoverItemClass(i === activeIndex())"
                role="option"
                [attr.aria-selected]="i === activeIndex()"
              >
                <span
                  class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full
                         bg-brand/20 text-xs font-semibold text-brand"
                  aria-hidden="true"
                >
                  {{ user.name.charAt(0).toUpperCase() }}
                </span>
                <span>{{ user.name }}</span>
              </button>
            }
          </div>
        }

        <!-- ── Popover de tareas (#) ───────────────────────────────────── -->
        @if (showTaskPopover() && filteredTasks().length > 0) {
          <div
            class="absolute z-50 min-w-64 overflow-hidden rounded-lg border border-border
                   bg-surface shadow-lg"
            [style.top.px]="popoverTop()"
            [style.left.px]="popoverLeft()"
            role="listbox"
            aria-label="Enlazar tarea"
          >
            @for (task of filteredTasks(); track task.key; let i = $index) {
              <button
                type="button"
                (mousedown)="selectTask($event, i)"
                [class]="popoverItemClass(i === activeIndex())"
                role="option"
                [attr.aria-selected]="i === activeIndex()"
              >
                <span
                  class="shrink-0 rounded px-1 py-0.5 font-mono text-xs font-semibold
                         bg-success/10 text-success"
                >
                  {{ task.key }}
                </span>
                <span class="truncate text-sm">{{ task.title }}</span>
              </button>
            }
          </div>
        }

        <!-- ── Diálogo inline de enlace ────────────────────────────────── -->
        @if (showLinkDialog()) {
          <div
            class="absolute inset-x-0 bottom-0 z-50 flex items-center gap-2
                   rounded-b-lg border-t border-border bg-surface px-3 py-2"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"
                 class="shrink-0 text-muted" aria-hidden="true">
              <path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/>
            </svg>
            <input
              #linkInput
              type="url"
              [value]="linkUrl()"
              (input)="linkUrl.set($any($event.target).value)"
              (keydown.enter)="confirmLink()"
              (keydown.escape)="cancelLink()"
              placeholder="https://..."
              class="flex-1 rounded border border-border bg-page px-2 py-1 text-sm text-text
                     placeholder:text-muted outline-none
                     focus:border-brand focus:ring-1 focus:ring-brand/40"
              aria-label="URL del enlace"
            />
            <button
              type="button"
              (click)="confirmLink()"
              class="rounded px-3 py-1 text-xs font-medium bg-brand text-brand-fg
                     hover:bg-brand/90 transition-colors"
            >
              Insertar
            </button>
            <button
              type="button"
              (click)="cancelLink()"
              class="rounded px-3 py-1 text-xs font-medium text-muted
                     hover:text-text transition-colors"
            >
              Cancelar
            </button>
          </div>
        }
      </div>
    </div>
  `,
})
export class RichEditorComponent implements ControlValueAccessor, AfterViewInit, OnDestroy {
  @ViewChild('editor') private readonly editorEl!: ElementRef<HTMLDivElement>;
  @ViewChild('linkInput') private readonly linkInputEl?: ElementRef<HTMLInputElement>;

  // ── Inputs ──────────────────────────────────────────────────────────────────

  @Input() label?: string;
  @Input() placeholder = 'Escribe aquí...';
  @Input() minHeight = '120px';

  @Input()
  set mentionableUsers(v: MentionUser[]) {
    this._mentionableUsers.set(v ?? []);
  }

  @Input()
  set linkableTasks(v: LinkableTask[]) {
    this._linkableTasks.set(v ?? []);
  }

  // ── Outputs ─────────────────────────────────────────────────────────────────

  @Output() readonly mentionsChange = new EventEmitter<string[]>();
  @Output() readonly taskLinksChange = new EventEmitter<string[]>();

  // ── Estado interno ───────────────────────────────────────────────────────────

  private readonly _mentionableUsers = signal<MentionUser[]>([]);
  private readonly _linkableTasks    = signal<LinkableTask[]>([]);

  protected readonly disabled   = signal(false);
  protected readonly isBold     = signal(false);
  protected readonly isItalic   = signal(false);

  // Popover
  protected readonly showMentionPopover = signal(false);
  protected readonly showTaskPopover    = signal(false);
  protected readonly mentionQuery       = signal('');
  protected readonly taskQuery          = signal('');
  protected readonly activeIndex        = signal(0);
  protected readonly popoverTop         = signal(0);
  protected readonly popoverLeft        = signal(0);

  // Diálogo de enlace
  protected readonly showLinkDialog = signal(false);
  protected readonly linkUrl        = signal('');

  // Listas filtradas (computed)
  protected readonly filteredUsers = computed(() => {
    const q = this.mentionQuery().toLowerCase();
    return this._mentionableUsers()
      .filter(u => !q || u.name.toLowerCase().includes(q))
      .slice(0, 8);
  });

  protected readonly filteredTasks = computed(() => {
    const q = this.taskQuery().toLowerCase();
    return this._linkableTasks()
      .filter(t => !q || t.key.toLowerCase().includes(q) || t.title.toLowerCase().includes(q))
      .slice(0, 8);
  });

  // ── Estado privado ───────────────────────────────────────────────────────────

  private onChange: (value: string) => void = () => {};
  protected onTouched: () => void           = () => {};

  /** Rango del trigger + query actual (@xxx o #xxx) para reemplazar al insertar el chip */
  private triggerRange: Range | null = null;

  /** Selección guardada antes de abrir el diálogo de enlace */
  private savedRange: Range | null = null;

  /** Valor pendiente cuando writeValue se llama antes de ngAfterViewInit */
  private pendingValue: string | null = null;

  /** Evita reentrada en writeValue causada por nuestro propio onChange */
  private isEmitting = false;

  /** Handler de click fuera del componente (captura) */
  private readonly outsideClickHandler = (event: MouseEvent): void => {
    if (!this.hostRef.nativeElement.contains(event.target as Node)) {
      this.closePopovers();
    }
  };

  constructor(private readonly hostRef: ElementRef<HTMLElement>) {}

  // ── Lifecycle ────────────────────────────────────────────────────────────────

  ngAfterViewInit(): void {
    if (this.pendingValue !== null) {
      this.editorEl.nativeElement.innerHTML = this.pendingValue;
      this.pendingValue = null;
    }
    document.addEventListener('click', this.outsideClickHandler, true);
  }

  ngOnDestroy(): void {
    document.removeEventListener('click', this.outsideClickHandler, true);
  }

  // ── ControlValueAccessor ─────────────────────────────────────────────────────

  writeValue(value: string | null): void {
    if (this.isEmitting) return;
    const html = sanitizeHtml(value ?? '');
    if (this.editorEl) {
      if (this.editorEl.nativeElement.innerHTML !== html) {
        this.editorEl.nativeElement.innerHTML = html;
      }
    } else {
      this.pendingValue = html;
    }
  }

  registerOnChange(fn: (value: string) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
    if (this.editorEl) {
      this.editorEl.nativeElement.contentEditable = isDisabled ? 'false' : 'true';
    }
  }

  // ── Eventos del editor ───────────────────────────────────────────────────────

  protected onEditorInput(): void {
    this.detectAutocomplete();
    this.emitChange();
  }

  protected onBlur(): void {
    this.onTouched();
    // No cerramos popovers aquí: el mousedown del item llega antes que blur,
    // y al hacer preventDefault() en mousedown el editor no pierde el foco.
  }

  protected onSelectionChange(): void {
    // queryCommandState está deprecado pero sigue siendo el único mecanismo
    // nativo para detectar el estado de formato en contenteditable.
    this.isBold.set(document.queryCommandState('bold'));
    this.isItalic.set(document.queryCommandState('italic'));
  }

  protected onKeyDown(event: KeyboardEvent): void {
    const popoverOpen = this.showMentionPopover() || this.showTaskPopover();

    if (popoverOpen) {
      const listLen = this.showMentionPopover()
        ? this.filteredUsers().length
        : this.filteredTasks().length;

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          this.activeIndex.update(i => Math.min(i + 1, listLen - 1));
          break;
        case 'ArrowUp':
          event.preventDefault();
          this.activeIndex.update(i => Math.max(i - 1, 0));
          break;
        case 'Enter':
          event.preventDefault();
          if (this.showMentionPopover()) {
            this.selectMention(null, this.activeIndex());
          } else {
            this.selectTask(null, this.activeIndex());
          }
          break;
        case 'Escape':
          event.preventDefault();
          this.closePopovers();
          break;
      }
      return;
    }

    if (this.showLinkDialog() && event.key === 'Escape') {
      event.preventDefault();
      this.cancelLink();
    }
  }

  protected onPaste(event: ClipboardEvent): void {
    event.preventDefault();
    const html  = event.clipboardData?.getData('text/html') ?? '';
    const plain = event.clipboardData?.getData('text/plain') ?? '';
    const toInsert = html
      ? sanitizeHtml(html)
      : plain
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/\n/g, '<br>');

    // execCommand insertHTML es la única forma de insertar preservando la posición del cursor
    document.execCommand('insertHTML', false, toInsert);
    this.emitChange();
  }

  // ── Toolbar ──────────────────────────────────────────────────────────────────

  /** Aplica un comando de formato nativo. Usa mousedown para no robar el foco. */
  protected execFormat(event: MouseEvent, command: string): void {
    event.preventDefault();
    document.execCommand(command, false);
    this.onSelectionChange();
    this.emitChange();
  }

  // ── Diálogo de enlace ────────────────────────────────────────────────────────

  protected openLinkDialog(event: MouseEvent): void {
    event.preventDefault();
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0) {
      this.savedRange = sel.getRangeAt(0).cloneRange();
    }
    this.linkUrl.set('');
    this.showLinkDialog.set(true);
    // Dar tiempo al DOM para renderizar el input antes de enfocarlo
    setTimeout(() => this.linkInputEl?.nativeElement.focus(), 0);
  }

  protected confirmLink(): void {
    const raw = this.linkUrl().trim();
    if (!raw) {
      this.showLinkDialog.set(false);
      return;
    }
    // Normalizar URL — añadir https:// si no tiene protocolo
    const url = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;

    // Restaurar selección guardada antes de aplicar el enlace
    if (this.savedRange) {
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(this.savedRange);
    }

    document.execCommand('createLink', false, url);

    // Asegurar que todos los enlaces abran en nueva pestaña de forma segura
    this.editorEl.nativeElement.querySelectorAll<HTMLAnchorElement>('a').forEach(a => {
      a.target = '_blank';
      a.rel    = 'noopener noreferrer';
    });

    this.showLinkDialog.set(false);
    this.savedRange = null;
    this.emitChange();
  }

  protected cancelLink(): void {
    this.showLinkDialog.set(false);
    this.savedRange = null;
    this.editorEl?.nativeElement.focus();
  }

  // ── Autocompletado ────────────────────────────────────────────────────────────

  private detectAutocomplete(): void {
    const result = this.getQueryBeforeCursor();

    if (!result) {
      this.closePopovers();
      return;
    }

    const { trigger, query, range } = result;
    this.triggerRange = range;

    const pos = this.getCaretPositionInContainer();
    this.popoverTop.set(pos.bottom + 4);
    this.popoverLeft.set(pos.left);
    this.activeIndex.set(0);

    if (trigger === '@') {
      this.mentionQuery.set(query);
      this.showMentionPopover.set(true);
      this.showTaskPopover.set(false);
    } else {
      this.taskQuery.set(query);
      this.showTaskPopover.set(true);
      this.showMentionPopover.set(false);
    }
  }

  /**
   * Analiza el texto antes del cursor para detectar un trigger activo.
   * Retorna null si el cursor no está después de un '@' o '#' activo.
   */
  private getQueryBeforeCursor(): { trigger: '@' | '#'; query: string; range: Range } | null {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return null;

    const range = sel.getRangeAt(0);
    if (!range.collapsed) return null;

    const container = range.startContainer;
    if (container.nodeType !== Node.TEXT_NODE) return null;

    const text       = container.textContent ?? '';
    const offset     = range.startOffset;
    const textBefore = text.slice(0, offset);

    let triggerIdx: number  = -1;
    let trigger: '@' | '#' | null = null;

    // Buscar el último trigger desde la posición del cursor hacia atrás
    for (let i = textBefore.length - 1; i >= 0; i--) {
      const ch = textBefore[i];
      if (ch === '@' || ch === '#') {
        // El trigger es válido si está al inicio o precedido por un espacio
        if (i === 0 || /\s/.test(textBefore[i - 1])) {
          triggerIdx = i;
          trigger    = ch as '@' | '#';
        }
        break;
      }
      // Si encontramos un espacio antes de encontrar el trigger, no hay match
      if (/\s/.test(ch)) break;
    }

    if (triggerIdx === -1 || !trigger) return null;

    const query = textBefore.slice(triggerIdx + 1);
    if (query.length > 30) return null; // Seguridad: query demasiado larga

    // Rango que abarca desde el trigger hasta la posición actual del cursor
    const triggerRange = document.createRange();
    triggerRange.setStart(container, triggerIdx);
    triggerRange.setEnd(container, offset);

    return { trigger, query, range: triggerRange };
  }

  /**
   * Calcula la posición del caret relativa al contenedor con position:relative.
   */
  private getCaretPositionInContainer(): { bottom: number; left: number } {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return { bottom: 44, left: 12 };

    const r         = sel.getRangeAt(0).cloneRange();
    r.collapse(true);
    const caretRect = r.getBoundingClientRect();

    // El contenedor "relative" es el padre del editor
    const container = this.editorEl.nativeElement.parentElement!;
    const contRect  = container.getBoundingClientRect();

    return {
      bottom: caretRect.bottom - contRect.top,
      left:   Math.max(0, Math.min(caretRect.left - contRect.left, contRect.width - 208)),
    };
  }

  private closePopovers(): void {
    this.showMentionPopover.set(false);
    this.showTaskPopover.set(false);
    this.triggerRange = null;
  }

  // ── Selección de item en popover ─────────────────────────────────────────────

  protected selectMention(event: MouseEvent | null, index: number): void {
    event?.preventDefault();
    const user = this.filteredUsers()[index];
    if (!user) return;

    this.insertChip('@', `@${user.name}`, { 'data-mention-id': user.id });
    this.closePopovers();
    this.emitChange();
  }

  protected selectTask(event: MouseEvent | null, index: number): void {
    event?.preventDefault();
    const task = this.filteredTasks()[index];
    if (!task) return;

    this.insertChip('#', task.key, { 'data-task-key': task.key });
    this.closePopovers();
    this.emitChange();
  }

  /**
   * Reemplaza el texto del trigger+query por un chip span no editable.
   * Mueve el cursor después del chip e inserta un espacio para continuar escribiendo.
   */
  private insertChip(
    trigger: '@' | '#',
    label: string,
    attrs: Record<string, string>,
  ): void {
    if (!this.triggerRange) return;

    const sel = window.getSelection();
    if (!sel) return;

    // Seleccionar desde el trigger hasta la posición actual
    sel.removeAllRanges();
    sel.addRange(this.triggerRange);

    // Crear el chip
    const chip = document.createElement('span');
    chip.className       = trigger === '@' ? 'bk-mention-chip' : 'bk-task-chip';
    chip.contentEditable = 'false';
    chip.textContent     = label;
    for (const [k, v] of Object.entries(attrs)) {
      chip.setAttribute(k, v);
    }

    // Eliminar el texto del trigger+query e insertar el chip
    this.triggerRange.deleteContents();
    this.triggerRange.insertNode(chip);

    // Mover el cursor al final del chip
    const after = document.createRange();
    after.setStartAfter(chip);
    after.collapse(true);
    sel.removeAllRanges();
    sel.addRange(after);

    // Insertar un espacio para que el cursor pueda seguir escribiendo fuera del chip
    document.execCommand('insertText', false, ' ');
  }

  // ── Helpers de clases ─────────────────────────────────────────────────────────

  protected toolbarBtnClass(active: boolean): string {
    const base =
      'flex h-7 w-7 items-center justify-center rounded transition-colors ' +
      'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50';
    return active
      ? `${base} bg-brand/10 text-brand`
      : `${base} text-muted hover:bg-muted/10 hover:text-text`;
  }

  protected popoverItemClass(active: boolean): string {
    const base =
      'flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-sm text-text ' +
      'transition-colors text-left focus:outline-none';
    return active ? `${base} bg-brand/10` : `${base} hover:bg-muted/10`;
  }

  // ── Emisión de cambios ───────────────────────────────────────────────────────

  private emitChange(): void {
    if (!this.editorEl) return;
    this.isEmitting = true;
    const html = sanitizeHtml(this.editorEl.nativeElement.innerHTML);
    this.onChange(html);
    this.mentionsChange.emit(extractMentionIds(html));
    this.taskLinksChange.emit(extractTaskKeys(html));
    // Liberar el guard en el siguiente microtask (después de que Angular Forms
    // haya procesado el onChange y potencialmente llamado writeValue de vuelta)
    Promise.resolve().then(() => { this.isEmitting = false; });
  }
}
