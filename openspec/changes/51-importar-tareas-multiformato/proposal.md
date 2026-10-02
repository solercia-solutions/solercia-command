# Propuesta: 51 · Importación web multiformato

**Estado:** aprobación pendiente; no acredita implementación ni autoriza apply.

## Intención

Incorporar trabajo mediante carga web, validación determinista, sugerencias editables y confirmación explícita.

[Evidencia vigente](exploration-web-local-ai.md), §§2–11: cinco SHA-256 y decisiones confirmadas. Investigación no seleccionada.

## Alcance

- Checklist CSV/XLSX, PSPI/PTR DOCX y PAI 2026: `13. Plan de accion Institucional 2026 Consolidado dependencias - CORREGIDO.xlsx`.
- Checklist: seleccionar responsable válido individualmente/en bloque; nunca inferir Solicitante/importador.
- PAI: seleccionar actividades filtrando responsable administrativo/política; ni 108 ni 11 automáticamente.
- Clasificación ligera local/servidor propio; proyectos existentes autorizados, sugerencias editables; Generales predeterminado para todas las organizaciones, COMPLETADA última; incompatibilidades visibles.
- Plan/actividad/tarea distintos; actividades importables sin enlaces ni conversión automática a tareas.

### Exclusiones

IA externa, creación automática de usuarios/proyectos, fusiones/consolidación, enlaces automáticos, traslado completo, seguimiento 2025 inferido, PTEP, cumplimiento Security, Connect/49/52/53. JSON genérico, CLI y `routing.yaml` explícitamente diferidos: muestras insuficientes.

## Capacidades

Nuevas: `multiformat-task-import` (checklist), `institutional-plan-import` (selección/perfiles), `local-project-suggestions` (clasificación privada).

Modificadas: ninguna publicada; cumplir `tasks`/aislamiento. `institutional-plans` pertenece al 45a pendiente; no duplicarla.

## Dependencias y entregas propuestas

1. Checklist web tras [50 mínimo](../50-proyecto-generales-y-mover-tarea/exploration.md): Generales/estados, no movimiento completo.
2. Planes web tras [45a reconciliado](../45a-planes-modelo-api/specs/institutional-plans/spec.md): código PAI y responsable+código no únicos; resolver identidad/versiones y Alembic sin reservas.
3. Clasificador evaluado contra reglas en diseño/tareas: modelo, precisión, latencia y recursos todavía desconocidos.

Dependencias conceptuales, ninguna acreditada lista; STATUS conserva relaciones vacías. Auto-chain/800 líneas, topología diferida; entregas con pruebas/reversa.

[44](../44-importar-checklist-xlsx/proposal.md): reemplazar importación CLI/CSV por web; conservar deuda roll-up/contexto, PANDORA, completado histórico e insignia. No cancelar/archivar; [deuda vigente](../../specs/data-maintenance/spec.md).

## Áreas y enfoque propuestos

Nuevas: `backend/app/modules/task_import/`, `frontend/src/pages/task-import/`, `frontend/src/entities/task-import/`.

Integración: `backend/app/modules/{tasks,plans}/`, `backend/app/ai/`, `backend/alembic/`, `backend/tests/`.

Router→servicio→puertos→adaptadores locales; transacción del caso de uso, UoW multi-repositorio. Retirar commits internos con caracterización; no savepoints encubridores.

## Riesgos y éxito

El sistema DEBE demostrar:

- Confirmación revalidada contra permisos, tenant autenticado, fuente, selección y ediciones; preview sin escrituras de negocio.
- Atomicidad/idempotencia concurrente; CSV/XLSX equivalentes sin duplicados. Hash/ancla no identifican negocio entre versiones; sin sobrescritura/fusión implícita.
- Sin truncamiento/fórmulas ejecutadas; excluir separadores, riesgos y solapamientos PTR; `null ≠ 0`.
- Límites conservadores propuestos para lectura/descompresión/tiempo; egreso cerrado, sin descargas ni documentos en logs.
- Fallo IA con ruta manual; cinco estados accesibles y selecciones conservadas; pruebas con fakes/PostgreSQL/fixtures sintéticos.

## Rollback

Activación gradual por tenant propuesta; desactivar entradas/clasificador, revertir código compatible. Conservar datos/auditoría; ninguna eliminación predeterminada. Migraciones pobladas: respaldo y reparación segura, no downgrade destructivo.

**Siguiente:** revisión humana; después specs (DEBE, Dado/Cuando/Entonces), diseño y tareas antes de implementar.
