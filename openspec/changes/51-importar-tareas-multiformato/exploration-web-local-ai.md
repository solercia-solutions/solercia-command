# Exploración: importación web de tareas y planes con IA local

**Cambio:** `51-importar-tareas-multiformato`  
**Fecha:** 2026-09-10  
**Estado:** exploración revisada; decisiones de producto confirmadas el 2026-09-10; habilitada la preparación de propuesta, sin implementación nueva.  
**Almacén:** híbrido, este archivo + Engram `sdd/51-importar-tareas-multiformato/explore-web-local-ai`.

Este documento materializa la exploración del ejecutor SDD y su corrección acotada de evidencia sobre el cambio 50. Complementa `exploration.md` sin sobrescribirlo. Sus recomendaciones web/IA sustituyen las recomendaciones incompatibles anteriores, no constituyen archivo o cierre de 44 ni aprobación de una propuesta.

## 1. Resultado recomendado

Importación **web** de checklist y planes institucionales de 2026: **subir → validar determinísticamente → revisar y editar sugerencias de IA local → confirmar y guardar**.

La clasificación sugiere proyectos existentes; no decide identidades, responsables, fusiones ni creación de proyectos. Las actividades de plan permanecen separadas de las tareas. Su vinculación posterior no bloquea la primera importación.

## 2. Evidencia y límites

El ejecutor leyó `CLAUDE.md`, la regla de persistencia, el registro de decisiones de plataforma, `openspec/config.yaml`, la exploración anterior de 51, secciones relevantes de 44/45a y el plan del 5 de septiembre. Verificó selectivamente parsers Jira, router, puerto y registro LLM, adaptador compatible, proyectos, persistencia de tareas y precedente frontend. Una corrección posterior leyó exactamente `openspec/changes/50-proyecto-generales-y-mover-tarea/exploration.md`.

CodeGraph no estaba disponible por falta del ejecutable; se usaron lecturas y búsquedas dirigidas. El ejecutor SDD no ejecutó comandos, pruebas, instalaciones, consultas de BD ni investigación externa. La inspección de fuentes fue una acción de apoyo de lectura local mediante Python, sin modificar documentos ni enviar datos a servicios externos.

Los conteos siguientes describen las versiones inspeccionadas, no constantes para los parsers.

### Inventario de fuentes

Raíz operativa: carpeta `2026` de OneDrive SDMujer. Los cinco archivos estaban disponibles localmente, sin estado `dataless`.

| Fuente | Estructura verificada | Tratamiento recomendado |
|---|---|---|
| `VARIOS/TAREAS/CHECKLIST_TAREAS.csv` | UTF-8 BOM, `;`, 139 registros y 139 ID únicos no vacíos; 11 encabezados | Perfil de tareas; igualdad completa CSV/XLSX no comprobada |
| `VARIOS/TAREAS/CHECKLIST_TAREAS.xlsx` | `Checklist Tareas!A1:K140`; sin fórmulas ni combinaciones en hoja principal; validaciones `B2:B140`, `J2:J140` | Excluir `Resumen`; conservar procedencia por fila |
| `PLANES/DECRETO 612/13. Plan de accion Institucional 2026 Consolidado dependencias - CORREGIDO.xlsx` | `PlandeacciónInstitucional`, encabezados fila 8 `A:AE`; 108 anclas de actividad en K, filas 9–223; 1986 rangos combinados | Única versión PAI autorizada; extracción especializada y alcance pendiente |
| `PLANES/DECRETO 612/2623_PLAN_DE_SEGURIDAD_Y_PRIVACIDAD_DE_LA_INFORMACIÓN_v2_20260120.docx` | Seis tablas; tabla 2: 25 actividades y seis separadores; tabla 3: diez enlaces control–actividad | Importar actividades, no separadores ni enlaces como tareas |
| `PLANES/DECRETO 612/2624_PLAN_DE_TRATAMIENTO_A_RIESGOS_DE_SEGURIDAD_DE_LA_INFORMACIÓN_v2_20260120.docx` | Tabla 5: 29 riesgos con ID únicos; tablas 7/8/9: 1 + 14 + 11 = 26 acciones | Riesgos como contexto; cuatro filas adicionales de tabla 11 con solapamiento no verificado: no sumarlas automáticamente |

Los nombres se presentan normalizados Unicode; el sistema de archivos puede usar caracteres descompuestos.

**Checklist:** `ID`, `Estado`, `Vencido`, `Urgencia`, `Categoría`, `Tarea`, `Detalle`, `Fecha Límite`, `Solicitante`, `Apoyo IA`, `Observaciones`. **No existe `Responsable`**; `Solicitante` no demuestra asignación.

**PAI:** responsable administrativo (I), código (J), actividad (K), producto (L), evidencia (M), objetivos, estrategia, políticas MIPG y seguimiento. Hay 29 responsables crudos y 27 tras recortar espacios; esto acredita mezcla de dependencias, no múltiples entidades jurídicas. En `O9:O226` aparecen 108 `Programado`, 109 `Ejecutado` y un vacío: no asumir parejas exactas. J tiene solo diez valores distintos; responsable + código produce 95 combinaciones para 108 actividades: tampoco es clave única. S menciona 2025 pese al archivo 2026; no corregirlo por inferencia. La hoja principal no tiene fórmulas; `Hoja1!A7` contiene una fórmula sin evaluar.

**PSPI:** tabla 2 con encabezados `No.`, `ACTIVIDAD`, `PRODUCTO`, `FECHA FIN`, `RESPONSABLE`, `META 2026`, `CONTROL ISO 27001:2022`; tabla 3 con relaciones control–actividad.

**PTR:** las tablas de acciones comparten `Riesgo`, `Acción`, `Responsable`, `Fecha`, `Meta 2026`, `Producto`, `Control ISO 27001:2022`, `Actividad Plan Seguridad`. La tabla 11 tiene `Acción`, `Responsable`, `Fecha Límite`, `Estado`, `Control ISO 27001:2022`; no está demostrada su independencia de las 26 acciones.

### Huellas SHA-256

| Fuente | SHA-256 |
|---|---|
| Checklist CSV | `1fa9f25fe6e21e94c1a36418f6214e27d185ff8bef87040ed511cd24930b82fa` |
| Checklist XLSX | `26e4422c1bbda9ad3c931b8e282e41f5d4313d7c8a9ac7533ed6929bfa814a8e` |
| PAI corregido | `34c79d82ff746f527c08f3383d020dde649eac9f1d09d88b68fd11ee4c42baf3` |
| PSPI 2623 | `50390957097eb80d499fd1728ce5e63095aa040a723e7fbbc777e0bce360e5dd` |
| PTR 2624 | `92f524a7b02df4cc0c8ffb1186787d8952e0c26e3b1c2fa63ab728e4595404f0` |

Hash + hoja/tabla + ancla identifica procedencia de una versión, **no identidad de negocio entre versiones**.

La lectura necesitó corregir detección heurística de delimitador, celdas XML vacías y selección ambigua por prefijo. El resultado final usó `;` y el nombre NFC exacto del PAI. No se evaluaron fórmulas. Quedan pendientes igualdad completa CSV/XLSX, normalización de dominios y fechas e integridad de vínculos entre planes.

## 3. Decisiones confirmadas y diferencias

| Tema | Línea vigente |
|---|---|
| Canal | Web obligatoria; CLI no es requisito del MVP |
| Revisión | Sugerencias editables antes de guardar; queda superada la prohibición anterior de editar filas |
| IA | Solo local o servidor propio; ninguna IA externa ni fallback externo |
| Destino | Proyectos existentes del tenant; «Generales» predeterminado para todas las organizaciones |
| Estados | `COMPLETADA` última; no comprimir estados incompatibles silenciosamente |
| Planes | Actividades distintas de tareas; enlaces posteriores |
| Consolidación | No heredar fusiones, subtareas ni grupos de contexto automáticos del CSV histórico |
| Fuentes | Checklist CSV/XLSX, PAI corregido y DOCX PSPI/PTR; PTEP excluido hasta seleccionar fuente |
| Formatos anteriores | JSON genérico y `routing.yaml` no son prerrequisitos demostrados del nuevo MVP; cualquier diferimiento debe quedar explícito en propuesta |
| Persistencia | No recomendar savepoints para ocultar commits de repositorios |
| 45a | No aplicar «tal cual» sin revisar identidad PAI, alcance histórico de 11 actividades y dependencias de migración |

Las restricciones «sin creación/fusión automática» son límites conservadores del alcance aprobado, no pruebas de que el usuario haya renunciado a esas capacidades futuras.

Se conservan de 44 trazabilidad, importación revisable, ausencia de truncamiento silencioso e idempotencia. La deuda de avance sigue mencionando 44 en `openspec/specs/data-maintenance/spec.md:142`; un reemplazo estrecho no la resuelve ni autoriza abandonarla.

## 4. Estado del código y áreas afectadas

| Evidencia | Consecuencia |
|---|---|
| `backend/app/integrations/adapters/jira/file_parser.py` | Precedente BOM, XLSX y límites; no reutilizar su vocabulario Jira ni selección de hoja para PAI |
| `backend/app/modules/jira_import/router.py` | Upload y permisos; lee archivo completo antes del límite, sin garantía de memoria acotada |
| `backend/app/ai/ports.py`, `registry.py` | `LlmPort` ofrece `complete/probe`, no embeddings; registro también admite proveedores externos |
| `backend/app/ai/adapters/openai_compatible.py` | Allowlist exacta de URL no prueba propiedad del servidor; registra hasta 200 caracteres del cuerpo de error del proveedor |
| `docker-compose.yml` | `LLM_PROVIDER: fake`; sin capacidad real de inferencia/hardware acreditada |
| `backend/app/modules/projects/models.py` | Nombre, descripción, código, jerarquía y `project_kind` para candidatos; calidad real no comprobada |
| `backend/app/modules/tasks/repository.py:191–267` | Lookup por origen en organización; `create/save` ejecutan `commit`: conflicto con atomicidad |
| `frontend/src/pages/connections/connections.component.ts` | Precedente de upload; no es la ubicación funcional recomendada |
| Artefactos de 45a | Modelo de planes diseñado; búsqueda dirigida no encontró implementación de `Plan` |
| `openspec/changes/50-proyecto-generales-y-mover-tarea/exploration.md`, §§4.2, 7.6, 8–9 | Existe exploración de Generales, movimiento y estado canónico; §7.6 registra dependencia de 51. No acredita implementación. Corrige la ausencia de artefactos erróneamente reportada por el primer pase |

Ubicaciones candidatas a decidir en diseño: `backend/app/modules/task_import/`, dominio de planes de 45a, `frontend/src/pages/task-import/` y `frontend/src/entities/task-import/`. Sin escrituras en Connect ni biblioteca UI compartida.

## 5. Descomposición mínima recomendada

```text
50: capacidad mínima Generales + estados válidos ──→ 51: checklist web
45a: modelo de planes e identidad reconciliada ──→ 51: fuentes de planes
                  ambas ramas ──→ preview editable + confirmación atómica
```

Dependencias conceptuales, no cambios adicionales ni tareas creadas:

1. **50 mínimo:** destino predeterminado por organización, resolución segura y tablero con `COMPLETADA` última. No arrastrar traslado masivo, historial de movimientos, sprints ni conciliación.
2. **45a:** separación plan/actividad/tarea, aislamiento y `null ≠ 0`; revisar unicidad `(plan, code)` frente a PAI y anclaje Alembic. No asumir que J puede alimentar `activity.code`.
3. **51:** perfiles por fuente, preview que distingue tipos de registro, clasificación local y guardado confirmado.
4. **44:** reconciliar qué capacidad sustituye 51 y conservar la deuda no absorbida antes de cerrar 44.

No crear identificadores ni artefactos para los nombres de fases futuras citados históricamente por 45a.

## 6. Clasificación local: alternativas y controles

| Alternativa | Ventaja | Costo o límite |
|---|---|---|
| Embeddings locales y similitud con proyectos | Salida acotada y comparación directa | Puerto nuevo; similitud no equivale a confianza calibrada |
| Generación local con salida estructurada | Aprovecha `LlmPort`; admite contexto textual | Mayor variabilidad y cómputo por medir |

**Recomendación:** comparar con una línea base determinista; elegir en diseño mediante evidencia, no por tamaño anunciado. No hay modelo, umbral, precisión, tamaño ni velocidad acreditados.

- Entrada mínima: título, categoría y fragmentos pertinentes; excluir nombres, correos y observaciones innecesarias.
- Candidatos activos y autorizados del tenant actual. Revalidar cada ID sugerido.
- IA sin autoridad sobre estructura, permisos, instrucciones incrustadas, responsables, fechas ni fusiones.
- Configuración cerrada a infraestructura propia aprobada; no basta el registro global.
- Bloquear egreso externo y redirecciones no autorizadas; no descargar modelos automáticamente.
- Sin contenido documental en logs, errores, trazas, cachés compartidas o fixtures. Proteger el registro de cuerpos de error antes de reutilizar el adaptador.
- Fallo/abstención de IA: conservar preview y permitir clasificación manual, no presentar archivo vacío.
- Evaluar etiquetas revisadas con conjunto reservado; evitar fuga entre duplicados, formatos equivalentes y versiones.
- Medir acierto por proyecto, cobertura/abstención, correcciones, salidas inválidas, latencia fría/caliente y memoria máxima en hardware propio.

## 7. Riesgos y garantías de diseño

| Riesgo | Garantía recomendada |
|---|---|
| Escrituras parciales | Caso de uso propietario de transacción; UoW explícito con varios repositorios; adaptadores sin commit |
| Regresión al retirar commits | Caracterización y compatibilidad temporal explícita; no compensación ni savepoints como excepción silenciosa |
| Reintentos/concurrencia | Identidad de origen separada del proyecto sugerido; restricciones y pruebas PostgreSQL |
| CSV/XLSX equivalentes | Namespace de checklist + tenant; hash distinto no implica nuevos registros |
| Versiones PAI | Código y responsable+código no únicos; cambios de fila no autorizan crear/fusionar |
| Preview obsoleto | Vincular confirmación a fuente, selección, ediciones, tenant y plan validado; revalidar al guardar |
| Tenants | Tenant desde autenticación, nunca desde RESPONSABLE; referencias/cachés/preview/confirmación aislados |
| Archivo hostil | Límites antes y durante lectura/descompresión; no ejecutar fórmulas/macros/recursos externos |
| Migraciones | Verificar cadena real; no reservar números desde documentos antiguos |
| Métricas | No convertir seguimiento, controles o riesgos en tareas; conservar advertencia 2025/2026 |

Métodos, esquema de corrida, almacenamiento temporal, TTL, endpoints, parser DOCX y modelo son decisiones de diseño, no preguntas de implementación para el usuario.

## 8. UX mínima

La persona incorpora trabajo real con control sobre destino y contenido antes de guardarlo.

- Organización, fuente reconocida, avance y conteos reales; no inventar porcentajes.
- Selector buscable de proyectos válidos; Generales como default visible, no certeza de IA fingida.
- Preview separado por tareas/actividades de plan, origen, destino, cambios y advertencias. Editar sugerencias no altera el texto fuente.
- Conservar selección/correcciones al volver o fallar. Confirmación explícita con conteos; no preautorizar actualizaciones.
- Filtros y edición agrupada; controles accesibles y mensajes en español colombiano formal.

| Estado | Respuesta |
|---|---|
| Cargando | Indicar extracción, validación o clasificación |
| Vacío legítimo | Explicar ausencia de registros importables y cómo continuar |
| Sin resultados por filtro | Quitar filtros conservando total original |
| Error | Motivo específico, recuperación y preview conservado |
| Éxito | Conteos guardados y enlaces reales |

No deshabilitar confirmación sin explicar qué falta; no diálogos nativos ni pérdida de ediciones.

## 9. Criterios de aceptación recomendados

1. Perfiles con fixtures sintéticos sin fijar conteos observados como límites funcionales.
2. PAI respeta fuente autorizada, combinaciones y alcance; no fuerza parejas ni unicidad de J.
3. PSPI/PTR excluyen separadores/tablas contextuales; solapamientos pendientes no se agregan.
4. Validación/sugerencias sin escrituras de negocio; solo confirmar guarda lo revisado.
5. Edición de campos permitidos con procedencia identificable.
6. Fallo de escritura revierte lote confirmado; reintentos/concurrencia no duplican.
7. Sin sobrescribir ajustes, eliminar registros omitidos ni fusionar versiones por inferencia.
8. Pruebas negativas de aislamiento y rechazo de destinos externos de IA.
9. IA indisponible permite revisión manual; ninguna salida crea proyectos o asigna responsables.
10. Actividades y tareas separadas; no presentar avances ausentes como cero.
11. Services con fakes; atomicidad/restricciones/migraciones con PostgreSQL; UI con cinco estados y accesibilidad.

## 10. No objetivos

Outlook, Connect 49, conciliación 52, cuentas 53, contactos, creación automática de usuarios/proyectos, traslado completo de tareas, fusiones automáticas, sincronización de vuelta a documentos, suite completa de seguimiento de planes y autoridad de cumplimiento de Security.

Tampoco instalación de modelos ni importación real de archivos durante esta fase.

## 11. Decisiones de negocio confirmadas

Confirmación explícita del usuario después de esta exploración:

1. **Responsable del checklist:** seleccionar un usuario válido en la vista previa, individualmente o para varias filas, antes de confirmar. No equiparar solicitante con responsable ni asignar automáticamente al importador.
2. **PAI:** mostrar actividades con filtros por responsable administrativo y política; el usuario selecciona cuáles importar. No asumir el subconjunto de seguridad ni importar todo automáticamente.
3. **Investigación:** seguir hacia la propuesta con evidencia local; investigación externa SDD no seleccionada. La evaluación del clasificador local queda como trabajo explícito, sin modelo o precisión inventados.

Reconciliar 51/44 no autoriza descartar deuda comprometida. La discrepancia 2025 permanece advertida; cargar seguimiento histórico como parte del MVP necesitaría decisión adicional.

**Gate de producto habilitado para preparar propuesta:** decisiones confirmadas, investigación no seleccionada y evidencia disponible en disco y Engram. No equivale a aprobación de la propuesta futura ni a autorización técnica para aplicar tareas inexistentes. El registro nativo no fue editado ni sustituido por este documento.

## 12. Handoff SDD

- Preflight resuelto: interactivo, híbrido, auto-chain, presupuesto de revisión 800; estrategia de ramas diferida.
- STATUS nativo de 51: `gentle-ai.sdd-status/v2`, `nextRecommended: propose`, `blockedReasons: []`; faltan propuesta/specs/diseño/tareas. Planificación local autorizada; implementación no lista.
- Ejecutor: `sdd-explore`; resultado parcial por decisiones y materialización pendientes, no por implementación fallida.
- Materialización de este artefacto realizada por el padre; no se modificó la exploración anterior.
- Corrección acotada de evidencia de 50 aplicada; no prueba implementación de esa dependencia.
- Skill de fase resuelto tras fallback inicial: `/Users/camilocalderont/.claude/skills/sdd-explore/SKILL.md`; inyectarlo explícitamente en próximas fases.
- No pruebas funcionales, commits, publicación ni cambios en archivos institucionales.
