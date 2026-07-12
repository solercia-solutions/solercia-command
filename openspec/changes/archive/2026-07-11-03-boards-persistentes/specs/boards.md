# Boards — Especificación (nueva)

Persistir el tablero por proyecto (`Board` + `BoardColumn`) sembrado desde `strategy.default_columns()`, habilitar el movimiento de tareas entre columnas, aplicar límites WIP y exponer una API de configuración de columnas en runtime que hace usable la metodología `custom`.

## Requirements (synopsis)

- **R1**: Siembra del board al crear el proyecto (Board 1:1, BoardColumn 1:N desde default_columns)
- **R2**: Estructura BoardColumn (name, status_key, order, wip_limit nullable)
- **R3**: Bloqueo de custom sin columnas (rechazo creación/movimiento 422)
- **R4**: Config runtime columnas (rename/reorder/add/remove)
- **R5**: Reglas de eliminación (vacía OK, con tareas exige destino, última→422)
- **R6**: Límite WIP (count activas vs wip_limit, 409 si excede)

Ver openspec/specs/boards/spec.md para el spec completo con todos los escenarios.
