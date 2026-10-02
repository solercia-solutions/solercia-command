import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { SolButtonComponent } from '@solercia/ui';
import { AuthService } from '@features/auth/auth.service';
import { ActiveOrgStore } from '@features/organizations/active-org.store';
import { I18nService } from '@shared/i18n';
import { MAX_ENCODED_SOURCE, MAX_PREVIEW_BYTES, MAX_REVIEW_BODY_BYTES, OptionCollection, OptionItem, PreviewIssue, PreviewRow, ReviewData, ReviewRequest, TaskImportPreview, previewFormat } from '@entities/task-import/task-import.model';
import { OptionsState, ROW_PAGE_SIZE, RowDraft, decisionFor, emptyOptions, newDrafts, reviewDecisions, rowId, validQuery, visibleOptions, withinReviewLimits } from './task-import-review-state';
import { TaskImportService } from '@entities/task-import/task-import.service';

const ERROR_CODES: Record<string, number> = {
  preview_disabled: 404, busy: 503, cleanup_failed: 503,
  timeout: 504, upload_timeout: 408, input_limit: 413, response_limit: 413,
  unsupported_options: 422, unsupported_media_type: 415,
  cancelled: 499, client_disconnected: 499, preview_failed: 502,
  options_failed: 502, organization_unavailable: 403, validation_error: 422,
  facts_limit: 422, facts_failed: 502, review_failed: 502, invalid_base64: 422, internal_error: 500,
};
const ISSUE_CODES = new Set([
  'unsafe_locator', 'locator_collision', 'unsupported_format', 'unavailable',
  'source_error', 'empty_source', 'encoding_error', 'parse_error', 'limit_exceeded',
  'missing_sheet', 'other_sheets', 'unsupported_structure', 'external_link',
  'duplicate_header', 'unknown_header', 'missing_header', 'invalid_id',
  'duplicate_id', 'invalid_date', 'formula', 'cell_error',
]);

@Component({
  selector: 'sp-task-import-preview',
  standalone: true,
  imports: [SolButtonComponent, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="mx-auto max-w-5xl space-y-4 p-4 sm:p-6" [attr.aria-busy]="loading() || reviewLoading()">
      <h1 class="text-2xl font-semibold text-text">{{ t('title') }}</h1>
      <p class="text-muted">{{ t('scope') }}</p>
      <div class="space-y-3 rounded-lg border border-border bg-surface p-4">
        <p class="font-medium text-text">{{ t('profile') }}</p>
        <p class="text-sm text-muted">{{ t('requirements') }}</p>
        <label for="preview-file" class="block font-medium text-text">{{ t('file') }}</label>
        <input #fileInput id="preview-file" type="file" accept=".csv,.xlsx"
          aria-describedby="preview-help preview-selection" (change)="selectFile($event)"
          class="block min-h-11 w-full rounded border border-border p-2 text-text focus-visible:ring-2 focus-visible:ring-ring" />
        <p id="preview-help" class="text-sm text-muted">{{ t('help') }}</p>
        <p id="preview-selection" class="break-words text-sm text-text">
          @if (file(); as selected) { {{ selected.name }} · {{ selected.size }} {{ t('bytes') }} }
          @else { {{ t('initial') }} }
        </p>
        @if (!auth.isAuthenticated()) { <p role="alert">{{ t('errors.auth') }}</p> }
        <sol-button size="touch" [disabled]="!canSubmit()" [loading]="loading()" (clicked)="submit()">
          {{ t('review') }}
        </sol-button>
      </div>
      @if (loading()) { <p role="status">{{ t('loading') }}</p> }
      @if (error(); as errorKey) { <p role="alert" class="rounded-lg border border-danger p-4 text-danger">{{ t('errors.' + errorKey) }}</p> }
      @if (preview(); as result) {
        <div class="space-y-4 rounded-lg border border-border bg-surface p-4">
          <h2 class="text-lg font-semibold text-text" role="status">{{ t(result.complete ? 'success' : 'incomplete') }}</h2>
          <p class="text-sm text-muted">{{ t('projection') }}</p>
          @if (result.counts; as counts) {
            <dl class="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div><dt>{{ t('candidate') }}</dt><dd class="font-semibold">{{ counts.candidate }}</dd></div>
              <div><dt>{{ t('rejected') }}</dt><dd class="font-semibold">{{ counts.rejected }}</dd></div>
              <div><dt>{{ t('blank_skipped') }}</dt><dd class="font-semibold">{{ counts.blank_skipped }}</dd></div>
              <div><dt>{{ t('total') }}</dt><dd class="font-semibold">{{ counts.total }}</dd></div>
            </dl>
          } @else { <p>{{ t('noCounts') }}</p> }
          @for (issue of result.issues.slice(0, 25); track $index) { <p class="text-sm">{{ issueText(issue) }}</p> }
          @if (result.issues.length > 25) { <p class="text-sm">{{ result.issues.length }} {{ t('draft.issueSummary') }}</p> }
          @if (result.complete && result.rows.length === 0) { <p>{{ t('empty') }}</p> }
          @if (result.complete && result.rows.length) {
            <button type="button" class="control" (click)="editing.set(!editing())">
              {{ t(editing() ? 'draft.back' : 'draft.open') }}
            </button>
            <p class="text-sm text-muted">{{ t('draft.memory') }}</p>
          }
          @if (editing()) {
            <section class="space-y-4" aria-labelledby="draft-heading">
              <h2 id="draft-heading" class="text-lg font-semibold">{{ t('draft.heading') }}</h2>
              <p>{{ t('draft.instructions') }}</p>
              <div class="grid gap-4 sm:grid-cols-2">
                @for (collection of collections; track collection) {
                  @let state = options()[collection];
                  <fieldset class="min-w-0 space-y-2 rounded border border-border p-3">
                    <legend>{{ t('draft.' + collection) }}</legend>
                    <label [for]="collection + '-query'" class="block">{{ t('draft.search') }}</label>
                    <input [id]="collection + '-query'" type="search" class="control w-full" maxlength="200"
                      [value]="queries()[collection]" (input)="setQuery(collection, $event)"
                      [attr.aria-describedby]="collection + '-help'" (keydown.enter)="loadOptions(collection, 1)" />
                    <p [id]="collection + '-help'" class="text-sm">{{ t('draft.queryHelp') }}</p>
                    <button type="button" class="control" [disabled]="!queryValid(collection)" (click)="loadOptions(collection, 1)">{{ t('draft.search') }}</button>
                    @if (!queryValid(collection)) { <p role="status">{{ t('draft.queryInvalid') }}</p> }
                    @switch (state.status) {
                      @case ('loading') { <p role="status">{{ t('draft.optionsLoading') }}</p> }
                      @case ('empty') { <p role="status">{{ t('draft.optionsEmpty') }}</p> }
                      @case ('filteredEmpty') { <p role="status">{{ t('draft.filteredEmpty') }}</p> }
                      @case ('error') {
                        <p role="alert">{{ t('errors.' + state.error) }}</p>
                        <button type="button" class="control" (click)="loadOptions(collection, state.page.meta.page)">{{ t('draft.retry') }}</button>
                      }
                      @case ('success') { <p role="status">{{ state.page.meta.total }} {{ t('draft.optionsFound') }}</p> }
                    }
                    @if (state.query) { <button type="button" class="control" (click)="clearQuery(collection)">{{ t('draft.clearSearch') }}</button> }
                    <div class="flex flex-wrap items-center gap-2">
                      <button type="button" class="control" [disabled]="state.status === 'loading' || state.page.meta.page <= 1" (click)="pageOptions(collection, -1)">{{ t('draft.previous') }}</button>
                      <span>{{ t('draft.page') }} {{ state.page.meta.page }}</span>
                      <button type="button" class="control" [disabled]="state.status === 'loading' || state.page.meta.page >= 1000 || state.page.meta.page * state.page.meta.size >= state.page.meta.total" (click)="pageOptions(collection, 1)">{{ t('draft.next') }}</button>
                    </div>
                    <label [for]="collection + '-bulk'" class="block">{{ t('draft.bulkChoice') }}</label>
                    <select [id]="collection + '-bulk'" class="control w-full" [ngModel]="bulk()[collection]?.id ?? ''" (change)="selectBulk(collection, $event)">
                      <option value="">{{ t(collection === 'projects' ? 'draft.noProject' : 'draft.unassigned') }}</option>
                      @for (option of optionItems(collection, bulk()[collection]); track option.id) { <option [value]="option.id">{{ option.label }}</option> }
                    </select>
                    <p class="text-sm">{{ t('draft.bulkWarning') }}</p>
                    <button type="button" class="control" (click)="applyBulk(collection)">{{ t('draft.applyBulk') }}</button>
                  </fieldset>
                }
              </div>
              @if (bulkNotice(); as notice) { <p role="status">{{ t('draft.bulkApplied') }} {{ notice }}</p> }
              <p>{{ t('draft.accounting') }} {{ completeDecisions() }} / {{ requiredDecisions() }}</p>
              <p class="text-sm">{{ t('draft.unresolvedHelp') }}</p>
              @if (!canReview()) { <p class="text-sm">{{ t(needsPreview() ? 'draft.refreshNeeded' : 'draft.reviewHelp') }}</p> }
              <sol-button size="touch" [disabled]="!canReview()" [loading]="reviewLoading()" (clicked)="validateDraft()">{{ t('draft.validate') }}</sol-button>
              @if (reviewError(); as key) { <p role="alert">{{ t('errors.' + key) }}</p> }
              @if (reviewResult(); as reviewed) {
                <div class="space-y-2 rounded border border-border p-3" role="status">
                  <h3 class="font-semibold">{{ t('draft.' + reviewed.status) }}</h3>
                  <p>{{ t('draft.noTasks') }}</p>
                  <p>{{ t('draft.included') }}: {{ reviewCounts().include }} · {{ t('draft.excluded') }}: {{ reviewCounts().exclude }} · {{ t('draft.unresolved') }}: {{ reviewCounts().unresolved }} · {{ t('blank_skipped') }}: {{ reviewCounts().blank_skipped }}</p>
                  @for (code of reviewed.issues; track $index) { <p>{{ reviewIssue(code) }}</p> }
                </div>
              }
            </section>
          }
          <div class="flex flex-wrap items-center gap-2">
            <button type="button" class="control" [disabled]="rowPage() === 1" (click)="rowPage.set(rowPage() - 1)">{{ t('draft.previous') }}</button>
            <span role="status">{{ t('draft.page') }} {{ rowPage() }} / {{ rowPages() }} · {{ result.rows.length }} {{ t('draft.sourceRows') }}</span>
            <button type="button" class="control" [disabled]="rowPage() >= rowPages()" (click)="rowPage.set(rowPage() + 1)">{{ t('draft.next') }}</button>
          </div>
          @for (row of visibleRows(); track rowId(row.key)) {
            <details class="rounded border border-border p-3">
              <summary class="min-h-11 cursor-pointer break-words text-text focus-visible:ring-2 focus-visible:ring-ring">
                {{ t('row') }} {{ row.number }} · {{ t(row.disposition) }}
                @if (row.issues.length) { · {{ t('issuesLabel') }}: {{ row.issues.length }} }
                @if (editing() && draftFor(row); as draft) {
                  · {{ t(draft.action === 'exclude' ? 'draft.exclude' : 'draft.include') }}
                  @if (!rowReady(row)) { · {{ t('draft.unresolved') }} }
                  @if (rowReviewIssues(row).length) { · {{ t('issuesLabel') }}: {{ rowReviewIssues(row).length }} }
                }
              </summary>
              <p class="font-medium">{{ t('draft.original') }}</p>
              <dl class="space-y-2 break-words">
                @for (field of row.fields; track $index) {
                  <div><dt class="font-medium">{{ field.name }}</dt><dd class="whitespace-pre-wrap">{{ field.value ?? '—' }}</dd></div>
                }
                <div><dt class="font-medium">{{ t('dueDate') }}</dt><dd>{{ row.due_date ?? '—' }}</dd></div>
              </dl>
              @for (issue of row.issues; track $index) { <p class="mt-2 text-sm">{{ issueText(issue) }}</p> }
              @if (editing()) {
                @if (draftFor(row); as draft) {
                  <fieldset class="mt-4 space-y-3 border-t border-border pt-3">
                    <legend class="font-medium">{{ t('draft.correction') }}</legend>
                    <label class="block">{{ t('draft.action') }}
                      <select class="control w-full" [ngModel]="draft.action" (change)="changeAction(row, $event)">
                        <option value="include">{{ t('draft.include') }}</option><option value="exclude">{{ t('draft.exclude') }}</option>
                      </select>
                    </label>
                    @if (draft.action === 'exclude') {
                      <label class="block">{{ t('draft.reason') }}
                        <textarea class="control w-full" maxlength="512" [value]="draft.reason" (input)="patchRow(row, { reason: eventValue($event) })"></textarea>
                      </label>
                    } @else {
                      <div class="grid gap-3 sm:grid-cols-2">
                        @for (collection of collections; track collection) {
                          @let selected = collection === 'projects' ? draft.project : draft.member;
                          <label class="block">{{ t('draft.' + collection) }}
                            <select class="control w-full" [ngModel]="selected?.id ?? ''" (change)="selectRow(row, collection, $event)">
                              <option value="">{{ t(collection === 'projects' ? 'draft.noProject' : 'draft.unassigned') }}</option>
                              @for (option of optionItems(collection, selected); track option.id) { <option [value]="option.id">{{ option.label }}</option> }
                            </select>
                          </label>
                        }
                      </div>
                      <label class="block">{{ t('draft.dateMode') }}
                        <select class="control w-full" [ngModel]="draft.dateMode" (change)="changeDateMode(row, $event)">
                          <option value="unchanged">{{ t('draft.unchanged') }}</option>
                          <option value="date">{{ t('draft.correctDate') }}</option>
                          <option value="none">{{ t('draft.noDate') }}</option>
                        </select>
                      </label>
                      @if (draft.dateMode === 'date') {
                        <label class="block">{{ t('draft.correctDate') }}<input class="control w-full" type="date" min="0001-01-01" max="9999-12-31" [value]="draft.date" (input)="patchRow(row, { date: eventValue($event) })" /></label>
                      }
                    }
                    @if (!rowReady(row)) { <p class="text-sm">{{ t(draft.action === 'exclude' ? 'draft.reasonRequired' : 'draft.assignmentRequired') }}</p> }
                    @for (code of rowReviewIssues(row); track $index) { <p class="text-sm">{{ reviewIssue(code) }}</p> }
                  </fieldset>
                }
              }
            </details>
          }
        </div>
      }
    </section>
  `,
  styles: [`
    .control { min-height: 44px; padding: .5rem .75rem; border: 1px solid var(--sol-border-color-default); border-radius: var(--sol-border-radius-sm); color: var(--sol-color-text-primary); background: var(--sol-bg-surface); max-width: 100%; }
    .control:focus-visible { outline: 2px solid var(--sol-color-primary); outline-offset: 2px; }
    .control:disabled { opacity: .5; cursor: not-allowed; }
    select.control option { background: var(--sol-bg-surface); color: var(--sol-color-text-primary); }
  `],
})
export class TaskImportPreviewComponent {
  protected readonly auth = inject(AuthService);
  private readonly org = inject(ActiveOrgStore);
  private readonly api = inject(TaskImportService);
  private readonly i18n = inject(I18nService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');
  private request?: Subscription;
  private reviewRequest?: Subscription;
  private reader?: FileReader;
  private generation = 0;
  private reviewGeneration = 0;
  private optionRequests: Partial<Record<OptionCollection, Subscription>> = {};
  private optionGenerations = { projects: 0, members: 0 };
  private defaultProject: OptionItem | null = null;
  private defaultLoaded = false;
  protected readonly collections: OptionCollection[] = ['projects', 'members'];
  protected readonly rowId = rowId;
  protected readonly editing = signal(false);
  protected readonly drafts = signal<Record<string, RowDraft>>({});
  protected readonly options = signal<Record<OptionCollection, OptionsState>>({ projects: emptyOptions(), members: emptyOptions() });
  protected readonly queries = signal({ projects: '', members: '' });
  protected readonly bulk = signal<Record<OptionCollection, OptionItem | null>>({ projects: null, members: null });
  protected readonly bulkNotice = signal('');
  protected readonly rowPage = signal(1);
  protected readonly rowPages = computed(() => Math.max(1, Math.ceil((this.preview()?.rows.length ?? 0) / ROW_PAGE_SIZE)));
  protected readonly visibleRows = computed(() => this.preview()?.rows.slice((this.rowPage() - 1) * ROW_PAGE_SIZE, this.rowPage() * ROW_PAGE_SIZE) ?? []);
  protected readonly reviewLoading = signal(false);
  protected readonly reviewError = signal<string | null>(null);
  protected readonly reviewResult = signal<ReviewData | null>(null);
  protected readonly needsPreview = signal(false);
  protected readonly requiredDecisions = computed(() => this.preview()?.rows.filter(row => row.disposition !== 'blank_skipped').length ?? 0);
  protected readonly completeDecisions = computed(() => {
    const preview = this.preview();
    return preview ? reviewDecisions(preview, this.drafts()).length : 0;
  });
  protected readonly canReview = computed(() => {
    const preview = this.preview();
    return !!preview?.complete && !!this.file() && this.auth.isAuthenticated() && !this.loading() &&
      !this.reviewLoading() && !this.needsPreview() && withinReviewLimits(preview, reviewDecisions(preview, this.drafts()));
  });
  protected readonly reviewCounts = computed(() => {
    const counts = { include: 0, exclude: 0, unresolved: 0, blank_skipped: 0 };
    for (const row of this.reviewResult()?.rows ?? []) counts[row.action]++;
    return counts;
  });
  private readonly reviewedRows = computed(() => new Map((this.reviewResult()?.rows ?? []).map(row => [rowId(row.key), row.issues])));
  private readonly context = computed(() => JSON.stringify([
    this.auth.isAuthenticated(), this.auth.user()?.id, this.auth.user()?.organization_id,
    this.org.activeOrgId(),
  ]));
  private readonly resultContext = signal<string | null>(null);
  private readonly result = signal<TaskImportPreview | null>(null);
  protected readonly preview = computed(() => this.resultContext() === this.context() ? this.result() : null);
  protected readonly file = signal<File | null>(null);
  private readonly fileContext = signal<string | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly canSubmit = computed(() => {
    const file = this.file();
    return this.auth.isAuthenticated() && this.fileContext() === this.context() && !this.loading() && !!file &&
      !!previewFormat(file.name) && file.size > 0 && file.size <= MAX_PREVIEW_BYTES;
  });

  constructor() {
    this.destroyRef.onDestroy(() => this.reset());
    let previous = this.context();
    effect(() => {
      const current = this.context();
      if (current !== previous) {
        previous = current;
        this.reset();
        this.file.set(null);
        const input = this.fileInput();
        if (input) input.nativeElement.value = '';
      }
    });
  }

  protected t(key: string): string {
    this.i18n.activeLang();
    return this.i18n.translate('taskImport.' + key);
  }

  protected issueText(issue: PreviewIssue): string {
    const code = ISSUE_CODES.has(issue.code) ? issue.code : 'unknown';
    return [this.t('severity.' + issue.severity), this.t('issues.' + code),
      issue.row === null ? '' : `${this.t('row')} ${issue.row}`,
      issue.column === null ? '' : `${this.t('column')} ${issue.column}`,
    ].filter(Boolean).join(' · ');
  }

  protected selectFile(event: Event): void {
    this.reset();
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    this.file.set(file);
    this.fileContext.set(file ? this.context() : null);
    if (file) {
      if (!previewFormat(file.name)) this.error.set('format');
      else if (file.size === 0) this.error.set('empty');
      else if (file.size > MAX_PREVIEW_BYTES) this.error.set('input_limit');
    }
  }

  protected submit(): void {
    const file = this.file();
    const format = file && previewFormat(file.name);
    if (!this.canSubmit() || !file || !format) return;
    this.request?.unsubscribe();
    const generation = ++this.generation;
    this.invalidateReview();
    this.error.set(null);
    const context = this.context();
    this.loading.set(true);
    this.request = this.api.preview(file, format).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        if (context !== this.context() || generation !== this.generation) return;
        this.loading.set(false);
        const previous = this.result();
        if (!previous || previous.source_hash !== response.data.source_hash || previous.profile_version !== response.data.profile_version) {
          this.drafts.set(newDrafts(response.data, this.defaultProject));
          this.rowPage.set(1);
        }
        this.resultContext.set(context);
        this.result.set(response.data);
        this.needsPreview.set(false);
        if (!this.defaultLoaded) {
          this.loadOptions('projects', 1);
          this.loadOptions('members', 1);
        }
      },
      error: (error: unknown) => {
        if (context !== this.context() || generation !== this.generation) return;
        this.loading.set(false);
        this.error.set(this.errorKey(error));
      },
    });
  }

  private reset(): void {
    ++this.generation;
    this.invalidateReview();
    for (const collection of this.collections) {
      this.optionRequests[collection]?.unsubscribe();
      ++this.optionGenerations[collection];
    }
    this.defaultProject = null;
    this.defaultLoaded = false;
    this.drafts.set({});
    this.options.set({ projects: emptyOptions(), members: emptyOptions() });
    this.queries.set({ projects: '', members: '' });
    this.bulk.set({ projects: null, members: null });
    this.bulkNotice.set('');
    this.editing.set(false);
    this.rowPage.set(1);
    this.needsPreview.set(false);
    this.request?.unsubscribe();
    this.request = undefined;
    this.loading.set(false);
    this.result.set(null);
    this.resultContext.set(null);
    this.error.set(null);
  }

  protected eventValue(event: Event): string { return (event.target as HTMLInputElement).value; }
  protected setQuery(collection: OptionCollection, event: Event): void {
    this.queries.update(value => ({ ...value, [collection]: this.eventValue(event) }));
  }
  protected queryValid(collection: OptionCollection): boolean { return validQuery(this.queries()[collection]); }
  protected clearQuery(collection: OptionCollection): void {
    this.queries.update(value => ({ ...value, [collection]: '' }));
    this.loadOptions(collection, 1);
  }
  protected pageOptions(collection: OptionCollection, delta: number): void {
    // Page the applied query, not an unsubmitted search draft.
    this.queries.update(value => ({ ...value, [collection]: this.options()[collection].query }));
    this.loadOptions(collection, this.options()[collection].page.meta.page + delta);
  }
  protected loadOptions(collection: OptionCollection, page: number): void {
    const query = this.queries()[collection].trim();
    if (!this.preview() || !this.auth.isAuthenticated() || !validQuery(query) || page < 1 || page > 1000) return;
    this.optionRequests[collection]?.unsubscribe();
    const generation = ++this.optionGenerations[collection];
    const context = this.context();
    this.options.update(value => ({ ...value, [collection]: {
      status: 'loading', query, error: null,
      page: { items: [], meta: { ...value[collection].page.meta, page } },
    } }));
    this.optionRequests[collection] = this.api.options(collection, page, query).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: response => {
        if (context !== this.context() || generation !== this.optionGenerations[collection]) return;
        const data = response.data[collection];
        this.options.update(value => ({ ...value, [collection]: {
          status: data.items.length ? 'success' : query ? 'filteredEmpty' : 'empty', page: data, query, error: null,
        } }));
        if (collection === 'projects' && !this.defaultLoaded) {
          this.defaultLoaded = true;
          this.defaultProject = response.data.default_project;
          this.bulk.update(value => ({ ...value, projects: this.defaultProject }));
          if (this.defaultProject) {
            this.invalidateReview();
            this.drafts.update(value => Object.fromEntries(Object.entries(value).map(([key, draft]) =>
              [key, draft.projectTouched ? draft : { ...draft, project: this.defaultProject }])));
          }
        }
      },
      error: error => {
        if (context !== this.context() || generation !== this.optionGenerations[collection]) return;
        this.options.update(value => ({ ...value, [collection]: { ...value[collection], status: 'error', error: this.errorKey(error) } }));
      },
    });
  }
  protected optionItems(collection: OptionCollection, selected: OptionItem | null): OptionItem[] {
    const state = this.options()[collection];
    return visibleOptions(state.status === 'success' ? state.page : { ...state.page, items: [] }, selected);
  }
  private selectedOption(collection: OptionCollection, event: Event, previous: OptionItem | null): OptionItem | null {
    return this.optionItems(collection, previous).find(item => item.id === this.eventValue(event)) ?? null;
  }
  protected selectBulk(collection: OptionCollection, event: Event): void {
    const option = this.selectedOption(collection, event, this.bulk()[collection]);
    this.bulk.update(value => ({ ...value, [collection]: option }));
    this.bulkNotice.set('');
  }
  protected applyBulk(collection: OptionCollection): void {
    if (!this.preview()) return;
    this.invalidateReview();
    let count = 0;
    this.drafts.update(value => Object.fromEntries(Object.entries(value).map(([key, draft]) => {
      if (draft.action === 'exclude') return [key, draft];
      count++;
      return [key, collection === 'projects'
        ? { ...draft, project: this.bulk().projects, projectTouched: true }
        : { ...draft, member: this.bulk().members }];
    })));
    this.bulkNotice.set(`${this.t('draft.' + collection)}: ${count}`);
  }
  protected draftFor(row: PreviewRow): RowDraft | undefined { return this.drafts()[rowId(row.key)]; }
  protected patchRow(row: PreviewRow, change: Partial<RowDraft>): void {
    if (!this.preview()) return;
    const id = rowId(row.key);
    const draft = this.drafts()[id];
    if (!draft) return;
    this.invalidateReview();
    this.bulkNotice.set('');
    this.drafts.update(value => ({ ...value, [id]: { ...draft, ...change } }));
  }
  protected selectRow(row: PreviewRow, collection: OptionCollection, event: Event): void {
    const draft = this.draftFor(row);
    if (!draft) return;
    const option = this.selectedOption(collection, event, collection === 'projects' ? draft.project : draft.member);
    this.patchRow(row, collection === 'projects' ? { project: option, projectTouched: true } : { member: option });
  }
  protected changeAction(row: PreviewRow, event: Event): void {
    this.patchRow(row, { action: this.eventValue(event) === 'exclude' ? 'exclude' : 'include' });
  }
  protected changeDateMode(row: PreviewRow, event: Event): void {
    const mode = this.eventValue(event);
    if (mode === 'unchanged' || mode === 'date' || mode === 'none') this.patchRow(row, { dateMode: mode });
  }
  protected rowReady(row: PreviewRow): boolean { return !!decisionFor(row, this.draftFor(row)); }
  protected rowReviewIssues(row: PreviewRow): string[] { return this.reviewedRows().get(rowId(row.key)) ?? []; }
  protected reviewIssue(code: string): string {
    if (ISSUE_CODES.has(code)) return this.t('issues.' + code);
    const key = 'reviewIssues.' + code;
    const text = this.t(key);
    return text === 'taskImport.' + key ? this.t('issues.unknown') : text;
  }
  private invalidateReview(): void {
    ++this.reviewGeneration;
    this.reviewRequest?.unsubscribe();
    this.reviewRequest = undefined;
    if (this.reader?.readyState === FileReader.LOADING) this.reader.abort();
    this.reader = undefined;
    this.reviewLoading.set(false);
    this.reviewResult.set(null);
    this.reviewError.set(null);
  }
  protected validateDraft(): void {
    const preview = this.preview();
    const file = this.file();
    const format = file && previewFormat(file.name);
    if (!this.canReview() || !preview || !file || !format || file.size > MAX_PREVIEW_BYTES) return;
    this.invalidateReview();
    const generation = this.reviewGeneration;
    const context = this.context();
    const decisions = reviewDecisions(preview, this.drafts());
    const current = () => generation === this.reviewGeneration && context === this.context() && file === this.file();
    this.reviewLoading.set(true);
    // One bounded read/encoding per explicit review; never persist the encoded source.
    const reader = new FileReader();
    this.reader = reader;
    reader.onerror = () => {
      if (!current()) return;
      this.reader = undefined;
      this.reviewLoading.set(false);
      this.reviewError.set('source_read');
    };
    reader.onload = () => {
      if (!current()) return;
      this.reader = undefined;
      const encoded = typeof reader.result === 'string' ? reader.result.split(',', 2)[1] : undefined;
      if (!encoded || encoded.length > MAX_ENCODED_SOURCE) {
        this.reviewLoading.set(false);
        this.reviewError.set('input_limit');
        return;
      }
      const body: ReviewRequest = {
        format, profile: 'checklist', source_base64: encoded,
        source_hash: preview.source_hash, profile_version: preview.profile_version, decisions,
      };
      if (new TextEncoder().encode(JSON.stringify(body)).byteLength > MAX_REVIEW_BODY_BYTES) {
        this.reviewLoading.set(false);
        this.reviewError.set('metadata_limit');
        return;
      }
      this.reviewRequest = this.api.review(body).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: response => {
          if (!current()) return;
          this.reviewLoading.set(false);
          const data = response.data;
          if (data.source_hash !== preview.source_hash || data.profile_version !== preview.profile_version ||
              data.issues.includes('source_hash_mismatch') || data.issues.includes('profile_version_mismatch')) {
            this.needsPreview.set(true);
            this.reviewError.set('source_changed');
            return;
          }
          this.reviewResult.set(data);
        },
        error: error => {
          if (!current()) return;
          this.reviewLoading.set(false);
          this.reviewError.set(this.errorKey(error));
        },
      });
    };
    reader.readAsDataURL(file);
  }

  private errorKey(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) return 'unknown';
    const body: unknown = error.error;
    if (body && typeof body === 'object' && 'code' in body && 'status' in body &&
        typeof body.code === 'string' && Object.hasOwn(ERROR_CODES, body.code) &&
        ERROR_CODES[body.code] === error.status && body.status === error.status) return body.code;
    if (error.status === 0) return 'network';
    if (error.status === 401) return 'auth';
    if (error.status === 403) return 'forbidden';
    return 'unknown';
  }
}
