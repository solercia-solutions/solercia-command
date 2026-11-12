# Importación del checklist y planes institucionales 2026

**Primero el checklist CSV/XLSX; después, actividades institucionales elegidas por la persona.** Este es un contrato de planificación, no una importación realizada. [Volver a la ruta P1](command-personal-daily-mvp.md).

## Fuentes, autoridad y límites

Carpeta autoritativa de tareas indicada por el usuario: `/Users/camilocalderont/Library/CloudStorage/OneDrive-SecretariaDistritalDeLaMujer/2026/VARIOS/TAREAS`. Se registra como localizador, sin leerla ni manipularla en esta revisión. Incluye el contexto de hojas y carpetas/archivos por tarea; conservar su estructura existente. Toda la fuente 2026, incluidos todos los archivos originales, debe permanecer intacta: sin movimientos, eliminaciones ni sobrescrituras. La preservación es integral aunque solo algunas filas o actividades se seleccionen para importar.

| Fuente | Uso previsto | Salvaguarda |
|---|---|---|
| Checklist 2026, CSV/XLSX | Tareas operativas personales | Equivalencia entre formatos; responsable explícito y organización/proyecto confirmados. |
| PSPI/PTR seleccionados | Compromisos y actividades institucionales | Conservar referencias y diferencias; no convertir todo automáticamente en tareas. |
| PAI 2026 corregido | Fuente autorizada para seleccionar actividades PAI | Usar `13. Plan de accion Institucional 2026 Consolidado dependencias - CORREGIDO.xlsx`, identificado en la propuesta 51. Ninguna selección automática de 108, 11 u otra cantidad. |

La cifra **139** corresponde al inventario histórico del checklist; no es el conteo actual, una meta de importación ni un criterio de aceptación. No se abrieron fuentes personales ni se verificaron sus cantidades en esta revisión.

**El estado final deseado es reemplazar Excel: la base de datos de Command será la fuente de verdad operativa.** Hasta el corte explícito, las hojas siguen siendo confiables y coexisten transitoriamente. Importar no autoriza el corte: exige conciliación completa, respaldo restaurable, responsables definidos y aprobación humana. En ese momento los originales se preservan respaldados y en solo lectura; cesa la escritura operativa en Excel. No habrá doble escritura indefinida ni cambios de fuente resueltos silenciosamente.

### Copia e inventario antes de importar

Trabajar sobre copias verificadas: inventariar rutas relativas, tamaños y hashes de todos los archivos de origen y conciliar cada copia con su entrada. Registrar explícitamente archivos inaccesibles, no disponibles localmente, omitidos, cambiados durante la copia o con hash distinto; ningún fallo puede convertirse en éxito ni quedar oculto en los totales. Repetir sin sobrescribir originales y no declarar copia completa hasta resolver o aceptar expresamente las excepciones. Este requisito no autoriza ejecutar la copia en esta actualización documental.

La curación/anonimización se aplica solo a copias de salida, nunca al inventario original ni a los archivos fuente. Para BYOK/agentes rige la [compuerta de política de P1](command-personal-daily-mvp.md): evidencia parcial, sin autorización de datos reales hacia servicios externos; el desarrollo local con fakes y datos sintéticos puede continuar. Preservar hashes/versiones diferenciados de original, copia de trabajo y copia de salida.

## Checkpoint ODD actual

El [registro ODD resumible](../../odd/tasks/command-daily-mvp.md) distingue implementación actual del inventario documental histórico que sigue. Generales para organizaciones nuevas ya tiene creación atómica (236 offline + 13 PG); requiere migración 0026 futura, sin backfill/startup operativo.

Parser/manifiesto, preview API/UI, hechos confiables (277 offline + 1 PG), opciones/revisión API (378 offline independientes) y borrador UI están verificados según recibos. La UI corrigió discrepancia ngModel DOM/modelo y contempla destino canónico, responsable/fecha/exclusión explícitos, paginación y cancelación por organización. La brecha de opciones SQL quedó cerrada: 6 PG passed en 2.47 s, con consultas de repositorio alcanzadas. Recibo separado diario/claves: 1 PG passed en 0.58 s. Consolidado offline: 33 selecciones, 561 passed, 1 warning, 11.41 s, exit real 0, sin reintento de subconjunto. Harness shell fake y sintaxis individual de tres scripts pasaron. Último CID `98075ae62042` retirado por el padre con identidad exacta y ausencia comprobada. Los 7 casos PG tienen dos alcances distintos; no sumarlos con offline ni con cortes históricos, ni afirmar suite completa/producción.

Inventario real recibido: **830 archivos, 198 directorios, 645357465 bytes; CSV: 185 filas, 180 candidatas y 5 fechas prosa/sentinela sin resolver**. Sustituye el conteo histórico, no acredita copia ni importación. No se leyeron originales en este checkpoint. No se copiaron fuentes ni cargaron tareas reales; flags siguen apagados y contenedores PG propios retirados.

**T05f continúa pendiente:** retención aprobada de fuente e identidad de negocio entre CSV/XLSX y versiones, además de las cinco fechas, bloquean confirmación/persistencia. No hay backend final S3/local seleccionado ni permiso para fusión/eliminación automática. Historial PATCH/movimiento/soft delete no completa CREATE/reorder/justificación/procedencia IA ni expediente versionado. Véanse [P1](command-personal-daily-mvp.md) y [privacidad IA](command-ai-privacy-controls.md): toda IA real actual, incluso HTTP local, está temporalmente bloqueada; fakes no autorizan tratamiento real.

## Inventario documental histórico (no estado de entrega ODD)

- [44](../../openspec/changes/44-importar-checklist-xlsx/state.yaml): planificación completa, aplicación pendiente; depende del 43. No equivale a importador disponible.
- [45a](../../openspec/changes/45a-planes-modelo-api/state.yaml): modelo/API de planes planificados, aplicación pendiente; la auditoría suministrada no encontró router de planes implementado. No aplicar sin reconciliar identidad/versiones.
- [50](../../openspec/changes/50-proyecto-generales-y-mover-tarea/exploration.md): exploración de Generales y movimiento de tareas. Solo el mínimo de Generales/estados es prerrequisito del checklist web.
- [51](../../openspec/changes/51-importar-tareas-multiformato/proposal.md): propuesta pendiente de aprobación; no hay diseño/tareas acreditados. Contempla carga web, sugerencias privadas editables y selección institucional.
- [Plan anterior](2026-09-05-importacion-tareas-y-conciliacion-correo.md): se conserva como antecedente, no como autorización de ejecución.

### Conflictos explícitos con el plan anterior

| Antecedente | Requisito de esta planificación |
|---|---|
| D5: Command sustituye la hoja tras importar | Destino confirmado: base de datos como fuente de verdad, pero solo tras corte conciliado y aprobado; Excel original respaldado y en solo lectura. |
| Responsable omitido → importador | Selección explícita de miembro válido; nunca inferirlo del solicitante o importador. |
| Upsert, fusiones o enlaces implícitos | No fusionar ni sobrescribir silenciosamente. Cada cambio requiere comparación y decisión explícita. |
| Aplicar 45a sin cambios | Reconciliar identidad de actividad y versiones con el PAI corregido; código o responsable+código no garantizan unicidad. |
| JSON/CLI/routing.yaml como primera entrega | La propuesta 51 los difiere; prioridad web CSV/XLSX y perfiles de fuentes demostradas. |
| 139 filas como corrida inicial fija | Contar y conciliar el lote efectivamente seleccionado, sin trasladar cifras históricas. |

Estos documentos no modifican decisiones normativas ni estados SDD. Cualquier ajuste de artefactos se decidirá en un trabajo posterior autorizado; no se declara 44 cancelado ni 45a terminado.

## Modelo funcional sin duplicar trabajo

- **Organización**: frontera de pertenencia y acceso. **Proyecto**: lugar de gestión y metodología. No son intercambiables.
- Una tarea pertenece a **un proyecto**. Puede aportar a varias actividades de planes mediante relaciones explícitas, sin copiar la misma tarea a cada plan.
- Plan, actividad, tarea y evidencia son conceptos distintos. Una actividad puede existir sin tarea asociada; importar un plan no crea trabajo operativo automáticamente.
- Distinguir avance calculado desde tareas y avance reportado por período. Ausencia de evidencia o período no es cero; no sustituir un dato por otro.
- Enlaces actividad–actividad y tarea–actividad preservan fuente, motivo y resolución humana. Los conflictos permanecen visibles y no cuentan como concordancias confirmadas.
- Command registra trabajo y autorreporte de primera línea. No sustituye validación independiente, cumplimiento o cierre de evidencia propios de Security.

## Flujo mínimo de importación segura

1. **Seleccionar:** organización autorizada, fuente/perfil, archivo y filas/actividades. Mostrar el ámbito antes de continuar; en PAI filtrar por responsable administrativo/política y confirmar la selección, sin asumir «todas» o «las mías».
2. **Leer sin ejecutar:** límites de tamaño, descompresión y tiempo; no ejecutar fórmulas, macros ni contenido documental. Conservar texto relevante sin truncarlo; errores de estructura deben explicar qué corregir.
3. **Validar determinísticamente:** identidad de fuente, encabezados, tipos, fechas, estados, referencias, permisos y responsable. Distinguir vacío, cero y no aplicable. No crear usuarios/proyectos para resolver ambigüedades.
4. **Sugerir y revisar:** IA local puede clasificar y validar coherencia con apoyo total/parcial/no es posible, razón y evidencia. Toda sugerencia es editable; permisos, identidad e idempotencia siguen siendo controles deterministas. Mantener ruta manual completa.
5. **Previsualizar:** mostrar creadas propuestas, coincidencias, diferencias, omitidas, errores, proyecto y responsable por fila. La vista previa no escribe datos de negocio. No fusionar ni enlazar implícitamente.
6. **Confirmar:** la persona aprueba el lote concreto. Revalidar archivo, selección, ediciones, membresía, permisos y versiones antes de persistir. Cualquier cambio relevante invalida la confirmación.
7. **Aplicar e informar:** atomicidad del lote acordado, con idempotencia ante concurrencia y reintentos. Entregar informe de conciliación y mantener la fuente intacta.

### Identidad, repetición y conciliación

La identidad de negocio debe incluir ámbito organizacional y procedencia estable; el formato CSV/XLSX no debe crear dos tareas equivalentes. El hash del archivo permite reconocer un archivo idéntico, pero no identifica por sí solo una actividad entre versiones.

Una repetición del mismo lote confirmado no duplica ni reenvía efectos. Un archivo revisado presenta diferencias para decisión; no sobrescribe trabajo posterior de Command, no fusiona tareas por parecido y no elimina registros ausentes. Conflictos de identidad o simultaneidad bloquean la operación afectada con salida recuperable, nunca con asignación arbitraria.

El informe conserva versión/hash de fuente, hoja/fila o sección, identificador de origen, organización/proyecto, responsable, selección, cambios aprobados, actor y fecha. Cada mutación dentro de Command registra antes/después, justificación disponible y procedencia humana/IA/clasificador; quien propone, quien ejecuta y quien aprueba son identidades diferenciadas según evidencia observada. La auditoría universal cubre los cambios dentro de Command; los eventos externos fuera de línea solo se registran como hechos cuando existe evidencia que los respalde. Concilia leídas = aceptadas + omitidas + rechazadas según categorías excluyentes, además de creadas/actualizadas/sin cambios y conflictos; los totales deben explicarse sin ocultar filas. Incluir enlaces a los registros resultantes y divergencias con la fuente.

### Archivos y espacio de trabajo de la tarea

Reutilizar los adjuntos locales y el historial existentes, identificados en la [matriz de P1](command-personal-daily-mvp.md). El espacio de trabajo gestionado, versionado y retorno de agentes externos son propuestas, no capacidades acreditadas. Decidir entre copias administradas y enlaces controlados antes de implementar; conservar carpetas originales sin mover ni borrar. Respaldar datos y archivos de manera coherente. Almacenamiento compatible con S3 en Docker: opción en evaluación, no seleccionada; no instalarlo ni trasladar archivos por inferencia.

Por archivo: tarea/entidad autorizadas, origen, versión/hash, actor observado de importación/aprobación y relación con la evidencia previa. Separar ese actor de la autoría externa declarada y del agente/modelo declarado, conservando evidencia y estado «verificado», «no verificado» o «desconocido». Importar o aprobar un artefacto no prueba su autoría externa ni el modelo utilizado; nunca fabricar atribuciones ni presentar declaraciones no verificadas como hechos. El agente externo recibe solo archivos expresamente habilitados y devuelve artefactos/diferencias para validación y aceptación auditada. No obtiene acceso global a OneDrive ni modifica la base directamente. Adjuntar un resultado no equivale a cumplir el compromiso, cerrar la tarea o aprobar un envío.

### Respaldo y reversa

Antes del primer lote real, comprobar respaldo y restauración aislada. Registrar el lote para revertir únicamente sus efectos autorizados, preservando auditoría y modificaciones posteriores. Definir desactivación/reparación segura; no borrar por omisión ni usar un downgrade destructivo como reversa predeterminada. El procedimiento exacto se diseña antes de implementar.

## Entregas y aceptación

| Orden | Entrega | Evidencia necesaria |
|---|---|---|
| 1 | Reconciliar contratos 44/50/51 y fuentes | Identidad, estados y responsable sin decisiones implícitas. |
| 2 | Checklist web y ruta manual | CSV/XLSX equivalentes, vista previa, confirmación y repetición sin duplicados. |
| 3 | Piloto pequeño autorizado | Conciliación fila a fila, respaldo y reversa comprobados; hojas intactas. |
| 4 | Reconciliar 45a y seleccionar planes | Identidad/versiones PAI resueltas; ninguna selección automática. |
| 5 | Enlazar trabajo y evidencias | Una tarea en un proyecto, aportes a varios planes sin duplicación ni avance ficticio. |

- [ ] Archivo inválido o falta de permiso no deja escrituras parciales.
- [ ] Responsable siempre explícito; proyecto y organización visibles antes de confirmar.
- [ ] Confirmación caducada por cambios de datos/permisos exige nueva revisión.
- [ ] Repetición y concurrencia preservan identidad; versión nueva no pisa trabajo sin decisión.
- [ ] Fallo de IA permite terminar manualmente y conserva selecciones.
- [ ] Informe explica cada fila y permite conciliar con la fuente confiable.
- [ ] Inventario de todos los archivos originales conciliado con copias y hashes; fallos explícitos, sin mover, eliminar ni sobrescribir fuentes.
- [ ] Corte a Command aprobado separadamente tras conciliación; base de datos operativa y Excel original respaldado/solo lectura, sin doble escritura indefinida.
- [ ] Archivos y cambios de agentes mantienen versiones/procedencia y aceptación explícita, sin modificar carpetas originales.
- [ ] Auditoría cubre cada cambio, no solo los campos actualmente observados por TaskHistory.

**Pendientes:** retención aprobada, identidad/versionado, cinco fechas, almacenamiento, lote piloto, selección institucional, política de actualización y reversa. No repetir el inventario como sustituto de resolver esas decisiones. Siguiente tramo útil: cerrar esas semánticas y completar T05f primero con datos sintéticos, conservando la verificación SQL PG ya obtenida. Copia real, carga confirmada y corte necesitan su procedimiento y aprobación; no son resultados de este checkpoint. No copiar fuentes, cargar archivos ni ejecutar migraciones en esta entrega documental.
