# Command: ruta para usarlo todos los días

**Prioridad 1: una aplicación personal confiable en el Mac. Prioridad 2: un piloto multiempresa.** Este documento es la entrada a la planificación solicitada. El usuario ya autorizó avanzar a implementación; esta actualización sigue siendo exclusivamente documental y no acredita un producto desplegado. Una comprobación previa separada, de solo lectura, prepara el trabajo de código; no se ejecutan aquí instalaciones, migraciones ni envíos.

- [Importación y planes institucionales 2026](command-institutional-plans-2026.md).
- [Gestión multiempresa y piloto IDARTES](command-multi-company-work-management.md).
- Línea normativa: [decisiones de plataforma](../decisions/2026-08-23-solercia-platform-decisions.md). Connect obtiene hechos; Command administra trabajo; Security conserva la autoridad de cumplimiento.

## Checkpoint ODD actual

El [registro resumible ODD](../../odd/tasks/command-daily-mvp.md) es la fuente de avance actual; conserva el orden autorizado: organizaciones → importación → expedientes → diario/Mac → IA → Jira. La matriz e inventario siguientes conservan el corte histórico y no descuentan las entregas ODD posteriores.

- G04: organización/admin/Generales atómicos, 236 offline + 13 PG verificados; falta aplicación operativa de 0026, backfill/startup e integración viva.
- Importación: preview, hechos, opciones y revisión de borrador/API/UI verificados; sin confirmación persistente, copia real ni tareas cargadas. Retención e identidad entre formatos/versiones siguen bloqueantes.
- Auditoría: PATCH de 16 campos, movimiento y soft delete verificados (cortes históricos 414/426/441). Alias público de ordenamiento de actividad `changed_at`: 22 pruebas independientes nuevas. Reorder ya cumple el contrato de tasks (líneas 202–220): `order` se excluye deliberadamente del historial; el cambio de sprint sí se registra. No hay decisión pendiente de reorder. La representación del evento CREATE sigue sin especificar y persiste la brecha transaccional; justificación/procedencia IA y expediente completo pendientes. T06 no está completo.
- Diario: dominio/servicio/adaptador/API y UI con build/browser sintético verificados. El PG inicial pasó tras completar imports de fixtures de roles/menús/dependencias; la proyección posterior de claves ya fue revalidada: 1 passed en 0.58 s, con consultas de repositorio alcanzadas. T07a acotada queda cerrada; T07 operativa permanece abierta. Flag false; política explícita con Bogotá sugerida, no elegida aún por la persona. No operación productiva.
- Mac: tres scripts con sintaxis/harness fake históricos; liveness de solo lectura y apertura de instancia existente. Nuevo `STARTUP_PROFILE=local_restricted`: omite seed/scheduler, conserva default, validación de cifrado y comprobaciones DB. Cleanup preserva errores originales tras corrección confirmada: 24 pruebas independientes en 0.33 s. La espera DB está acotada por número de intentos, no por tiempo total de reloj; cancelación inyectada, no probada sobre recursos reales.
- Runtime local: `scripts/local-runtime.py` y `scripts/tests/test_local_runtime.py`, 19 pruebas independientes. Plan pasivo por defecto, plist solo a stdout y `run` explícito para futuro desarrollo Angular local. Loopback fijo; requiere `LOCAL_RUNTIME_DATABASE_URL`/`LOCAL_RUNTIME_REDIS_URL` preparados sin imprimir URLs. Lock, handles de hijos propios y deadline de readiness. Solo hijos directos: descendientes Angular no demostrados; plist necesita entorno futuro. Sin arranque real, instalación, registro de plist ni migración DB. No es empaquetado productivo ni cierre de T07; respaldo/restauración y continuidad siguen pendientes.
- SMTP bloqueado, sin flujo de aprobación. Barrera temporal IA verificada (38 + 5 health aisladas): fake/configuración pasiva disponibles, toda IA real actual denegada, incluido HTTP local. No BYOK terminado ni cumplimiento; restaurar pruebas de transporte retiradas y auditar bypass por helpers privados antes de habilitar.

Recibo consolidado histórico, sustituido por el recibo actual siguiente: 33 selecciones offline, 561 passed, 1 warning, 11.41 s, exit real 0, sin reintento de subconjunto. Separadamente: opciones SQL 6 PG passed/2.47 s y diario claves 1 PG passed/0.58 s, ambos alcanzaron consultas de repositorio. Harness shell fake y sintaxis bash individual de tres scripts pasaron. Último contenedor `98075ae62042` retirado por el padre con identidad exacta y ausencia confirmada. Los 7 casos PG son dos alcances distintos, no una suma con offline ni con recibos históricos; no acreditan suite completa. Recibos del padre, no ejecuciones de esta actualización. Todos los contenedores PG propios fueron retirados; sin migración productiva, flags habilitados, proveedor real ni commits. Los nuevos cortes 22/24/19 son independientes: no sumarlos entre sí ni al histórico de 561 offline + 7 PG. Evaluación nativa indisponible; comprobación independiente no acredita aprobación nativa. Delta guardado en Engram 5434; espejo del registro completo 5414 desactualizado, actualización pendiente del padre.

**Bloqueo del runner cerrado:** recibo final del verificador independiente, runner exacto completo de **35 selecciones: 607 passed, 1 warning, 11.24 s, exit 0**; los 44 cuerpos async nuevos se ejecutaron. El escritor solo añadió 12 decoradores `pytest.mark.asyncio` (4 actividad, 8 lifespan): RED 44 failed/2 passed → GREEN 46 passed. Se conserva el fallo combinado histórico: **44 failed, 563 passed, 1 warning, 11.29 s, exit 1**; faltaban marcadores, el runner aislado usaba `asyncio_mode=auto` y el combinado no. Los cuerpos nuevos no se ejecutaban entonces: no eran 44 regresiones funcionales demostradas. Verificación separada: supervisor **19 passed/0.030 s**, harness fake del launcher y 3 comprobaciones bash de sintaxis pasaron. Recibos del padre; esta actualización no ejecuta pruebas ni modifica código. No acredita independencia del orden, nueva ejecución PG ni arranque real. Solo se cierra la incompatibilidad del runner: T07 operativo, retención/identidad/cinco fechas de importación y representación CREATE/brecha transaccional siguen pendientes.

## Estado de terminación y evidencia (corte histórico)

La especificación de necesidades queda documentada en estos tres planes. **Documentación completa no equivale a implementación completa ni a operación confiable.** No se calcula un porcentaje de producto a partir de carpetas archivadas, fases documentales o pruebas antiguas.

Leyenda: **código** = implementación localizada; **parcial** = base útil que no satisface todo el objetivo; **planeado** = requisito sin entrega demostrada; **ejecución no verificada** = no se comprobó en servicios durante esta revisión; **histórico** = evidencia de otro corte, no garantía actual.

| Capacidad | Evidencia local o antecedente | Estado y brecha |
|---|---|---|
| Trabajo, proyectos, tableros, sprints y alertas | [Catálogo de capacidades](../../openspec/specs/README.md) | Base documentada; ejecución integral no verificada. El catálogo no es inventario actualizado de todos los cambios. |
| Connect y Outlook | [Servicio de integración](../../backend/app/modules/connectors/solercia_connect_service.py): registro, estado, sesión y sincronización | Código; Outlook probado según el antecedente confirmado por el usuario. Reutilizar, no rediseñar. No se repitió la prueba viva. |
| Resumen ejecutivo | [Dashboard](../../backend/app/modules/dashboard/service.py), líneas 66–95 | Parcial: agrupa trabajo por organización; no demuestra el resumen personal de hoy/mañana/vencidos/bloqueados. |
| Evaluaciones programadas | [Scheduler](../../backend/app/alerts/scheduler.py), líneas 6–9 y 37–51 | Código: intervalo horario predeterminado; bloqueo distribuido documentado como pendiente. No acredita recuperación tras suspensión. |
| IA intercambiable | [Registro](../../backend/app/ai/registry.py), líneas 38–53; [asistente](../../backend/app/modules/assistant/service.py), líneas 35–77 | Código: fake, OpenAI compatible y Anthropic; configuración/sondeo no son un asistente que valide tareas. |
| Correo | [Outbox](../../backend/app/email/outbox.py), líneas 57–102; [sender](../../backend/app/email/sender.py), líneas 54–76; [política](../../backend/app/email/policy.py), línea 24 | Código de encolado y envío automático, incluida licencia vencida urgente. No demuestra aprobación humana vinculada al contenido. Bloqueante para habilitar correo con el requisito actual. |
| Organizaciones | [Resolución de membresía](../../backend/app/dependencies.py), líneas 134–205 | Código: `X-Organization-Id` validado contra membresía; sin cabecera usa primera membresía. No asumir aislamiento por esquema o tenant tomado solo del JWT. |
| Importación y planes | [44](../../openspec/changes/44-importar-checklist-xlsx/state.yaml), [45a](../../openspec/changes/45a-planes-modelo-api/state.yaml), [51](../../openspec/changes/51-importar-tareas-multiformato/proposal.md) | Planeado: 44/45a con apply pendiente; 51 con aprobación pendiente. No acreditar importador ni API de planes entregados. |
| Aplicación Mac y continuidad | Auditoría previa suministrada: no se encontró paquete Mac | Planeado: doble clic, inicio de sesión, respaldo/restauración y recuperación siguen sin demostración. No es prueba de ausencia absoluta. |
| Archivos por tarea/comentario | [Servicio de adjuntos](../../backend/app/modules/attachments/service.py) y [modelo](../../backend/app/modules/attachments/models.py) | Código: almacenamiento local UUID, nombre original, autor, fechas, ámbito organizacional y controles de tamaño/tipo. No acredita espacio de trabajo gestionado, versiones ni retorno de agentes. |
| Historial y actividad | [Modelo](../../backend/app/modules/activity/models.py), [recorder](../../backend/app/modules/activity/recorder.py), [rutas](../../backend/app/modules/activity/router.py), [campos observados](../../backend/app/modules/tasks/service.py) | Parcial: actor user/system, fecha y antes/después; historial por tarea y actividad por persona. La lista observada incluye estado, responsable, estimaciones, sprint y prioridad, no todo cambio ni procedencia IA. |

### Inventario documental, no lista de entregas terminadas

El inventario siguiente conserva la auditoría suministrada; se contrastaron selectivamente 44, 45a, 51, 43 y el catálogo. No se normalizaron estados ni archivos SDD.

| Cambios | Situación documental |
|---|---|
| 33 búsqueda/filtros; 34 estimación; 35 avance; 36 jerarquía; 37 metodología; 38 OAuth; 39 capacidades de conectores; 40 importación Jira usuario; 41 importación Jira administrador | Planificación completa y apply pendiente según el inventario previo; no afirmar implementación por ese estado. |
| 44 checklist; 45a planes | Propuesta, especificación, diseño y tareas terminados; apply/verify/archive pendientes, confirmado en `state.yaml`. |
| 47 Connect operativo | Diseño bloqueado histórico; no interpretar ese bloqueo como fallo actual de Outlook. |
| 49 conexión directa; 50 Generales/mover; 52 conciliación correo; 53 varias cuentas | Exploraciones, no entregas implementadas. |
| 51 importación multiformato | Propuesta pendiente de aprobación; sin diseño ni tareas según la auditoría. |
| cycle2-design-system | En pausa; no bloquear P1 por rediseño visual. |
| Archivos 01–32, 42, 43, 48 | Archivo histórico. Inconsistencias informadas: 04 conserva IN-PROGRESS; 42 archive pendiente; 43 apply/verify/archive pendientes, esto último confirmado por lectura. No corregidas. |

Dependencias registradas que deben respetarse al retomar: 33 ← 30 + 32; 35 ← 27 + 28; 36 ← 27; 38 ← 26; 44 ← 43. La propuesta 51 requiere el mínimo de 50 para checklist y 45a reconciliado para planes; no exige terminar todo el movimiento de tareas del 50. Tener un prerrequisito archivado no demuestra su disponibilidad operativa.

## Contrato P1: uso personal diario

1. **Arranque local:** abrir Command con doble clic en un acceso del Mac que abra la web local. Gestionar inicio, parada, estado y errores de sus servicios; inicio al ingresar al Mac configurable y explícitamente habilitado. No depender de una terminal abierta.
2. **Privacidad:** escuchar solo en localhost por defecto, incluidos servicios de soporte según corresponda. Sin túnel público ni exposición anónima. Connect es opcional: su caída no impide gestionar tareas locales.
3. **Persistencia:** conservar tareas, adjuntos, procedencia y decisiones tras reinicio o actualización; definir ubicación, permisos, retención y respaldo. Demostrar restauración en un destino aislado antes de confiar trabajo real.
4. **Continuidad:** comprobar reinicio, cierre de sesión, suspensión/reactivación, indisponibilidad de red y caída parcial. Mostrar diagnóstico y recuperación acotada; evitar trabajos programados duplicados o ráfagas de envíos al despertar.
5. **Resumen personal:** mostrar hoy, mañana, vencidas y bloqueadas para el usuario y ámbito elegido, con fecha de actualización por fuente, zona horaria explícita y acceso a la tarea/evidencia. La agregación entre empresas será deliberada y conservará permisos.
6. **Estados claros:** cargando, vacío legítimo, sin resultados por filtro, error y éxito. Datos viejos se identifican como tales; un fallo de consulta nunca se presenta como «no hay pendientes».
7. **Carga inicial y destino:** checklist CSV/XLSX de 2026 primero; planes institucionales seleccionados después. El objetivo sí es reemplazar Excel por la base de datos de Command como fuente de verdad operativa, mediante corte explícito tras conciliación y respaldo. Coexistencia transitoria, nunca doble escritura indefinida; originales preservados en solo lectura después del corte.
8. **Interfaz:** únicamente correcciones funcionales para P1. Renovación visual diferida hasta disponibilidad de `@solercia/ui`; no crear un sistema visual paralelo.

### Asistencia IA: clasificar y validar, no autorizar

- Por tarea, proponer clasificación y apoyo **total / parcial / no es posible**, con justificación, evidencia referenciada, límites y datos faltantes. La persona puede editar o rechazar cada sugerencia.
- Validar coherencia de fechas, responsable, proyecto, entidad, duplicidad potencial y evidencia; separar controles deterministas de juicios probabilísticos. La IA no sustituye validaciones de permisos o identidad.
- «Apoyo total» puede significar preparar un borrador completo; nunca concede autoridad para ejecutar, cambiar compromisos o enviar mensajes.
- Procesamiento local/privado por defecto. Los adaptadores intercambiables no autorizan egreso a servicios externos; un proveedor remoto requiere decisión explícita sobre datos, destino y seguridad.
- Si no hay modelo, falla o no existe evidencia suficiente: conservar el trabajo y permitir clasificación/validación manual, sin bloquear el núcleo.

### BYOK avanzado, ejecución de agentes y salida de datos

BYOK (claves propias) y ejecución de agentes son capacidades deseadas, todavía no acreditadas. Separar **proveedor de modelo**, por ejemplo OpenAI, de **entorno de ejecución de agentes**, por ejemplo OpenCode o Pi: configurar uno no instala, autoriza ni demuestra el otro. Mantener ejecución local/privada y adaptadores fake por defecto hasta permitir expresamente el egreso; una clave disponible no concede permiso para transmitir datos.

Antes de cualquier salida, curar y anonimizar únicamente copias destinadas al exterior de prompts, contexto, adjuntos, cargas de herramientas y registros; los originales permanecen intactos. La seudonimización no equivale a anonimización ni elimina por sí sola el riesgo de reidentificación. Si no se puede demostrar que el destino, canal y contenido cumplen la política aplicable, denegar el egreso y conservar una ruta local/manual. Nunca incluir credenciales de nube en prompts o registros. Aplicar permisos por organización y tarea, y auditar acciones de agentes con la distinción de procedencia descrita abajo. Ninguna capacidad de agente elude la aprobación de correo.

**Evidencia de política actualizada:** [controles de privacidad IA](command-ai-privacy-controls.md) conserva citas, páginas, alcance y hashes: contexto de tres PDF y secciones pertinentes del DOCX revisados según recibo, no una nueva lectura de originales en este checkpoint. El DOCX sigue «[pendiente de aprobación CIGD]» (XML ¶751); faltan el anexo distrital y GT-GU-4. La revisión no acredita aprobación, vigencia completa ni dictamen jurídico. La denegación temporal de adaptadores reales es una barrera técnica, no implementación integral de esos controles.

**Compuerta:** la revisión restante bloquea usar datos reales en servicios externos; no bloquea implementar localmente con fakes y datos sintéticos. Ni BYOK ni anonimización alegada sustituyen esa revisión y la autorización de egreso.

### Tarjeta, espacio de trabajo y agentes externos

La persona trabaja con tarjetas y carpetas/archivos por tarea, usando agentes de programación externos potentes. Se propone asociar un **espacio de trabajo gestionado por tarea**, reutilizando adjuntos e historial; no incorporar un IDE. La decisión entre almacenar copias/versiones administradas o enlazar carpetas existentes sigue abierta. El almacenamiento compatible con S3 en Docker es una opción en evaluación, no una tecnología seleccionada ni instalada. Preservar las carpetas actuales: este plan no autoriza moverlas, borrarlas ni modificarlas.

El clasificador local no es el agente ejecutor. Cada encargo externo debe identificar tarea, organización, instrucciones, archivos/versiones permitidos y alcance; no habilitar acceso global al directorio personal ni a otras entidades. El agente devuelve artefactos y diferencias por una vía controlada: recepción, validación, vista previa, aceptación explícita y registro auditable. No admitir escrituras silenciosas del agente o clasificador en datos de negocio.

Requisitos propuestos: acceso limitado por tarea y tenant, protección frente a rutas/symlinks fuera del alcance, versiones inmutables con hash/procedencia y relación derivado-de, actor observado de importación/aprobación y autor/agente/modelo externos declarados con su evidencia y estado de verificación, respaldo de archivos junto con sus referencias. Un enlace roto o un archivo externo cambiado debe ser visible. La recepción de evidencia no completa automáticamente una tarea: cumplimiento y cierre requieren validación humana de sus criterios.

**Auditoría completa requerida:** cada cambio dentro de Command, en datos, archivos, enlaces, clasificación, permisos y estado, debe conservar actor observado humano/IA/clasificador/sistema, fecha, antes/después (o referencias a versiones), justificación cuando exista y procedencia IA, diferenciando ejecutor de aprobador. Propuestas aceptadas/rechazadas y recepción de retornos externos deben ser trazables; sin cambios silenciosos. El importador o aprobador observado no demuestra quién creó el artefacto fuera de Command ni qué agente/modelo utilizó. Registrar la autoría externa declarada separadamente, con evidencia y estado «verificado», «no verificado» o «desconocido»; nunca fabricar atribuciones. Los eventos externos fuera de línea solo se incorporan al historial como hechos cuando están respaldados por evidencia; una declaración no verificada conserva esa condición. El historial actual es una base parcial, no prueba de cobertura universal. No registrar secretos.

### Correo: requisito confirmado, mecanismo todavía propuesto

**Ningún correo sale sin aprobación explícita de cuenta, destinatarios (incluidos CC/CCO), asunto, cuerpo y adjuntos.** Aplica también a mensajes urgentes, resúmenes, reintentos y envíos programados. Una preferencia general de notificaciones no aprueba contenido futuro desconocido.

Mecanismo propuesto: vista previa inmutable, aprobación vinculada a su versión y al despacho concreto; cualquier cambio invalida la aprobación. Registrar quién aprobó, cuándo, qué contenido y cuenta, vencimiento/revocación y resultado. Consumir la autorización una sola vez, con clave idempotente y auditoría que impidan otro despacho ante doble clic, concurrencia o reintento. Ante resultado incierto del proveedor, conciliar antes de reenviar. La programación puede preparar el borrador; cada contenido final requiere aprobación válida. Esto **no está demostrado en el código actual**.

## Hitos en orden de dependencia

| Hito | Entrega mínima | Condición de salida |
|---|---|---|
| H0: seguridad de operación | Plan de arranque local, inventario de efectos, bloqueo de correo y respaldo | Protocolo aprobado para comprobar un entorno aislado sin túnel, correo ni mutación de producción. |
| H1: aplicación Mac confiable | Ciclo de servicios, doble clic, persistencia y recuperación | Arranque/inicio de sesión y restauración comprobados; datos conservados tras suspensión y reinicio. |
| H2: checklist utilizable | 50 mínimo + contrato de 51 reconciliado con 44/43, auditoría completa y referencias a archivos | Importación confirmada, responsable explícito, repetición segura e informe conciliado; corte posterior aprobado a base de datos, originales preservados. |
| H3: resumen diario | Hoy/mañana/vencidas/bloqueadas y frescura | Casos vacíos, errores y datos desactualizados distinguibles; Connect reutilizado sin dependencia obligatoria. |
| H4: asistencia y comunicaciones seguras | Clasificación + validación IA/manual; espacio de trabajo y retorno auditado de agentes; control de aprobación | Versiones y cambios aceptados trazables; correo permanece deshabilitado hasta demostrar aprobación y no duplicación. |
| H5: planes seleccionados | 45a reconciliado + tramo institucional de 51 | Actividades, tareas y evidencias vinculadas sin duplicar trabajo; conciliación y reversa comprobadas. |
| H6: piloto multiempresa | Aislamiento y paridad priorizada con IDARTES | Criterios del [plan P2](command-multi-company-work-management.md) satisfechos, sin prometer paridad Jira total. |

P1 puede empezar a aportar valor con H1–H3 y ruta manual, manteniendo correo apagado. H4/H5 amplían el uso, no justifican postergar indefinidamente el uso personal seguro.

## Criterios de aceptación de P1

- [ ] Abrir desde el Mac y reconocer estado de servicios sin terminal; configuración de inicio de sesión reversible.
- [ ] Mantener datos tras reinicio y recuperar un respaldo verificado, con pérdida máxima y tiempo objetivo acordados.
- [ ] No exponer servicios públicamente ni enviar correo sin aprobación vinculada y auditable.
- [ ] Importar un lote aprobado y repetirlo sin duplicados, fusiones implícitas ni pérdida de datos fuente.
- [ ] Mostrar pendientes personales y antigüedad real de datos; fallos de Connect no anulan el trabajo local.
- [ ] Recuperar ejecución tras suspensión sin duplicar trabajos; limitar a una instancia mientras no exista coordinación demostrada.
- [ ] Clasificar y validar tareas con evidencia editable o ruta manual; ningún borrador equivale a ejecución autorizada.
- [ ] Registrar una jornada de uso real y sus incidencias antes de declarar «listo para uso diario».
- [ ] Auditar cada cambio con actor, fecha, antes/después y procedencia; probar también cambios de título, fecha, sprint, archivos y clasificación; `order` está deliberadamente excluido según el contrato actual de tasks.
- [ ] Acceder solo a archivos autorizados por tarea/entidad; aceptar versiones devueltas por agentes sin sobrescribir originales ni cerrar tareas por adjuntar evidencia.
- [ ] Aprobar corte a base de datos tras conciliación y restauración; preservar Excel original en solo lectura, sin doble escritura permanente.
- [ ] Preservar toda la fuente 2026 y sus archivos: copiar con inventario/hash y conciliación de fallos explícitos, sin mover, borrar ni sobrescribir originales.
- [ ] BYOK/agentes respetan permisos por organización; salida denegada sin política y autorización suficientes, incluidas herramientas y registros; secretos nunca en prompts/logs.

## Decisiones pendientes y siguiente acción segura

Pendientes: forma de distribución Mac y gestor de servicios; ubicación/retención de respaldos y objetivos de recuperación; ventana del piloto y fecha de corte a base de datos; almacenamiento administrado o enlaces a carpetas por tarea; canal de retorno y permisos de agentes externos; selección de actividades institucionales; modelo local y recursos; mecanismo exacto de aprobación/despacho; alcance medible de paridad IDARTES. La autorización de implementación no resuelve estas decisiones ni autoriza egreso, corte de datos o envíos.

**Siguiente acción:** seguir las prioridades del [registro ODD](../../odd/tasks/command-daily-mvp.md): protocolo y autorización de operación segura; decisiones de retención/identidad antes de confirmación real; representación CREATE y brecha transaccional antes de ampliar auditoría (reorder ya cumple contrato); integración real bajo protocolo autorizado después de la regresión offline consolidada y del PG de opciones/claves ya verificados. El launcher ya abre una instancia existente y el runtime tiene pruebas aisladas, pero no demuestran ciclo real de servicios ni uso diario. No ejecutar el arranque habitual como diagnóstico inocuo ni habilitar flags por haber pasado pruebas sintéticas.

No se inició ningún servicio: `gestion.sh on` puede terminar procesos, instalar componentes y abrir un túnel público anónimo; el entrypoint del backend aplica migraciones y el perfil predeterminado de [lifespan](../../backend/app/main.py) siembra datos y registra trabajos. `local_restricted` omite seed/scheduler, pero conserva cifrado y comprobaciones DB; no autoriza arranque ni migraciones. Esos efectos requieren un protocolo posterior, no esta planificación.

### Trazabilidad de la revisión inicial (histórica)

Lectura de código y documentación, sin pruebas funcionales ni comprobación viva. Rama observada: `feat/conexion-solercia-connect`; el árbol ya tenía cambios staged y archivos sin rastrear, incluidos planes y artefactos OpenSpec. Se preservaron; esta entrega solo añade los tres documentos enlazados. Las cifras históricas del registro de plataforma no describen automáticamente el estado actual.
