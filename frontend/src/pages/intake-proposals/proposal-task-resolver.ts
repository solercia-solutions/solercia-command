import { Injectable, inject, signal } from '@angular/core';
import { catchError, forkJoin, map, of } from 'rxjs';
import { TaskDetailService } from '@entities/task/task-detail.service';
import { IntakeProposal } from '@entities/intake-proposal/intake-proposal.model';

/** Lo que la bandeja necesita de una tarea: clave navegable (`/task/:key`), título y estado. */
export interface ProposalTaskRef {
  id: string;
  /** Clave `CODIGO-N` del proyecto; `null` si la tarea no la tiene o no se pudo leer. */
  key: string | null;
  /** Referencia que vio el clasificador (`T-7`, clave externa del checklist). */
  ref: string | null;
  title: string;
  status: string | null;
  projectId: string | null;
}

/**
 * El API de propuestas trae `task_id` y las candidatas (`ref` + título), pero no la clave del
 * proyecto que usa `/task/:key`. Este resolvedor pide `GET /tasks/{id}` una vez por tarea única
 * y cachea el resultado; si falla, queda la referencia de la candidata (sin enlace).
 */
@Injectable()
export class ProposalTaskResolver {
  private readonly tasks = inject(TaskDetailService);
  private readonly cache = signal<ReadonlyMap<string, ProposalTaskRef>>(new Map());
  private readonly pending = new Set<string>();

  readonly refs = this.cache.asReadonly();

  /** Tarea mostrada para la propuesta: la creada desde el hilo o la propuesta. */
  static taskIdOf(proposal: IntakeProposal): string | null {
    return proposal.created_task_id ?? proposal.task_id;
  }

  refFor(proposal: IntakeProposal): ProposalTaskRef | null {
    const id = ProposalTaskResolver.taskIdOf(proposal);
    if (!id) {
      return null;
    }
    const known = this.cache().get(id);
    if (known) {
      return known;
    }
    const candidate = proposal.candidates.find((c) => c.task_id === id);
    return {
      id,
      key: null,
      ref: candidate?.ref ?? proposal.result?.task_ref ?? null,
      title: candidate?.title ?? '',
      status: null,
      projectId: null,
    };
  }

  resolve(proposals: IntakeProposal[]): void {
    const ids = new Map<string, IntakeProposal>();
    for (const proposal of proposals) {
      const id = ProposalTaskResolver.taskIdOf(proposal);
      if (id && !this.cache().has(id) && !this.pending.has(id)) {
        ids.set(id, proposal);
      }
    }
    if (ids.size === 0) {
      return;
    }
    const calls = [...ids.entries()].map(([id, proposal]) => {
      this.pending.add(id);
      const fallback = this.refFor(proposal);
      return this.tasks.getTask(id).pipe(
        map(
          (res): ProposalTaskRef => ({
            id,
            key: res.data.task_key ?? null,
            ref: fallback?.ref ?? null,
            title: res.data.title,
            status: res.data.status ?? null,
            projectId: res.data.project_id ?? null,
          }),
        ),
        catchError(() => of(fallback)),
      );
    });
    forkJoin(calls).subscribe((refs) => {
      const next = new Map(this.cache());
      for (const ref of refs) {
        if (ref) {
          next.set(ref.id, ref);
          this.pending.delete(ref.id);
        }
      }
      this.cache.set(next);
    });
  }

  /** Olvida una tarea (p. ej. tras aceptar con cambio de estado) para releerla. */
  forget(id: string | null): void {
    if (!id) {
      return;
    }
    const next = new Map(this.cache());
    next.delete(id);
    this.cache.set(next);
  }
}
