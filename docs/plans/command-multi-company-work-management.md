# Gestión multiempresa: piloto IDARTES después del uso personal

**Prioridad 2: sustituir el trabajo Jira-like necesario para un piloto, no prometer toda la plataforma Jira.** La operación personal confiable del [plan P1](command-personal-daily-mvp.md) es el primer resultado; una renovación visual no es prerrequisito.

## Checkpoint ODD actual

El [registro ODD](../../odd/tasks/command-daily-mvp.md) conserva tareas y recibos actuales; el piloto Jira sigue pendiente, sin promesa de paridad total ni finalización autónoma de todas las capacidades. El orden autorizado comienza por organizaciones/importación/expedientes y diario/Mac, antes de IA y Jira.

G04 entregó creación atómica de organización/admin/Generales: 236 offline y 13 PG reales verificados; instancias propias retiradas. La migración 0026 no fue aplicada operativamente; organizaciones existentes/backfill/startup y aislamiento integral siguen pendientes. La limpieza/cancelación de contexto por cambio de organización en importación y diario, y logout en diario, fue comprobada en browser sintético, no como piloto multiempresa vivo.

PATCH/movimiento/soft delete tienen historial verificado; CREATE/reorder/justificación/procedencia IA no están completos. El resumen diario permanece apagado por defecto y no demuestra agregación multiempresa operativa. Launcher Mac abre servicios existentes, no los instala/inicia ni prueba continuidad. SMTP bloqueado no equivale a aprobación de envíos; toda IA real actual está temporalmente denegada, incluido HTTP local, sin certificar cumplimiento ([privacidad](command-ai-privacy-controls.md)).

Recibo consolidado actual: 33 selecciones offline, 561 passed, 1 warning, 11.41 s, exit real 0, sin reintento de subconjunto. PG independiente: opciones 6 passed/2.47 s y diario claves 1 passed/0.58 s, consultas de repositorio alcanzadas. T07a backend acotado y brecha PG de T05i cerrados; T07 operativa sigue abierta. Harness shell fake y tres comprobaciones individuales bash pasaron. Último CID `98075ae62042` retirado por el padre con identidad exacta/ausencia comprobadas. Los 7 casos PG son dos alcances separados; no sumarlos con offline/históricos ni afirmar suite completa. No hubo migración Jira, copia/carga real, proveedor IA real, despliegue productivo ni commits; flags originales false y espejo Engram pendiente del padre. Antes del piloto: resolver operación segura, retención/identidad de importación y matriz de paridad; no anticipar infraestructura innecesaria.

## Punto de partida y alcance

Hay una base de organizaciones, membresías, proyectos y metodologías. [dependencies.py](../../backend/app/dependencies.py), líneas 134–205, resuelve `X-Organization-Id` contra la membresía y rechaza ámbitos no autorizados; sin cabecera conserva el comportamiento de primera membresía. Esto no demuestra aislamiento integral, pero impide tratar multiempresa como un modelo por inventar desde cero.

La narrativa JWT/esquema de `CLAUDE.md` no debe confundirse con esa implementación. Antes de proponer tablas, cambiar tenancy o migrar datos, auditar código, permisos y relaciones existentes contra las [decisiones de plataforma](../decisions/2026-08-23-solercia-platform-decisions.md). Una divergencia normativa necesita decisión explícita, no rediseño silencioso.

| Área | Estado defendible | Brecha para el piloto |
|---|---|---|
| Organizaciones/membresías | Código localizado | Auditoría de permisos efectivos y cobertura de aislamiento de extremo a extremo. |
| Proyectos, metodología, tableros y sprints | Base descrita en el [catálogo](../../openspec/specs/README.md) | Verificar los flujos reales de IDARTES y sus límites; no asumir equivalencia Jira. |
| Importación Jira | Cambios 40/41 planificados según inventario previo | Migración verificable, alcance y reconciliación pendientes. |
| Búsqueda, estimaciones y avance | Cambios 33–35 con aplicación pendiente según inventario previo | Priorizar solo lo que bloquee la paridad acordada. |
| Agregación personal entre entidades | Requisito | Selección deliberada del ámbito y preservación de permisos por registro. |
| Repositorios, PR y CI tipo Bitbucket | Fuera de alcance, sin implementación acreditada | Evaluación independiente; no confundir alojamiento de código con gestión de tareas. |

## Contrato de pertenencia y aislamiento

1. Una persona puede pertenecer a varias organizaciones con roles distintos. Cambiar de entidad debe ser explícito, visible y actualizar datos, cachés y acciones pendientes; no arrastrar permisos de la entidad anterior.
2. Organización no equivale a proyecto. Cada proyecto conserva su metodología; cada tarea vive en un proyecto. Los [planes institucionales](command-institutional-plans-2026.md) vinculan compromisos y evidencias sin duplicar tareas.
3. El resumen personal puede agregar varias entidades solo por elección deliberada. Cada resultado conserva su organización y enlaces autorizados; agregar no concede acceso ni habilita escrituras cruzadas.
4. La revocación de membresía debe retirar acceso también de búsquedas, archivos, resultados IA y cachés. No revelar existencia, títulos o fragmentos de otra organización.
5. Connect continúa siendo integración independiente: identidad de cuenta y ámbito organizacional deben validarse sin permitir mezclas por coincidencia de correo o por una selección anterior.
6. BYOK y ejecución de agentes requieren permisos por organización, tarea, proveedor y acciones admitidas. OpenAI es un proveedor de modelo; OpenCode/Pi son entornos de agentes, no permisos de egreso. Auditar acciones dentro de Command sin inventar autoría externa; conservar el estado desconocido/no verificado cuando corresponda. La [revisión de política parcial de P1](command-personal-daily-mvp.md) bloquea datos reales externos, no desarrollo local con fakes. Curar solo copias de salida, sin secretos en prompts/logs ni correo sin aprobación.

### Pruebas requeridas antes del piloto, no ejecutadas aquí

| Superficie | Casos de aislamiento que deben demostrarse |
|---|---|
| Tareas/proyectos/planes | Lectura, escritura, asignación, movimiento, enlaces y listados de otra organización rechazados. |
| Búsqueda | Resultados, conteos, sugerencias y fragmentos restringidos al ámbito autorizado. |
| Archivos/evidencias | Descarga, vista previa, versiones y espacios de trabajo por tarea sin acceso cruzado o posterior a revocación; agentes externos solo acceden a archivos habilitados y devuelven cambios para aceptación auditada. |
| IA | Contexto, recuperación, prompts, respuestas, caché y registros sin filtración entre entidades; egreso cerrado por defecto. |
| Connect | Cuenta, conector, sesión, sincronización e insumos asociados al ámbito correcto; identidad discrepante falla de forma cerrada. |
| Interfaz y agregación | Cambio de entidad limpia contexto; agregación seleccionada solo incluye membresías vigentes. |
| Jobs y auditoría | Ámbito conservado al programar/reintentar; cada cambio con actor humano/IA/clasificador/sistema, fecha, antes/después, justificación disponible y procedencia IA; ejecutor y aprobador diferenciados. |

## Orden del piloto y paridad mínima

| Hito | Trabajo priorizado | Puerta de salida |
|---|---|---|
| P2.0: alcance y brechas | Elegir equipo/proyecto IDARTES y registrar flujos realmente usados en Jira | Matriz «imprescindible / posterior / fuera» validada por responsables. |
| P2.1: seguridad | Auditar membresías/roles y ejecutar casos de aislamiento | Sin acceso cruzado; privilegios mínimos y auditoría verificables. |
| P2.2: trabajo cotidiano | Workflow, backlog, sprints, asignación, prioridades y estimación requeridos por el piloto | Crear, priorizar, planear, ejecutar, revisar y cerrar trabajo sin rutas esenciales rotas. |
| P2.3: migración | Mapeo de estados/usuarios, vínculos, adjuntos e historial dentro del alcance acordado | Ensayo con muestra, conciliación, respaldo, repetición segura y reversa; sin corte automático. |
| P2.4: operación | Recuperación, soporte, observabilidad, acceso y capacidad | Ensayo de restauración y período de convivencia; responsables aceptan continuidad. |
| P2.5: corte limitado | Decisión humana basada en evidencia del piloto | Migrar solo el alcance aceptado; Jira sigue disponible según plan de retorno. |

No hacer depender P2 de todas las automatizaciones, extensiones o reportes de Jira. Cada ausencia debe registrarse como brecha aceptada, alternativa manual o bloqueo; «Jira-like» describe el flujo objetivo, no una garantía de paridad total.

## Operación, costos y adquisiciones

La estimación de **20–50 millones de COP/año** es una referencia incierta aportada por el usuario, no una cotización ni ahorro verificado. Comparar licencias evitables con desarrollo, soporte, disponibilidad, respaldo, seguridad, energía, conectividad y mantenimiento.

No comprar hardware todavía. Medir usuarios concurrentes, volumen de tareas/adjuntos, retención, consultas, trabajos programados y carga de IA; definir requisitos institucionales de seguridad y continuidad. Elegir infraestructura solo con carga medida, objetivos operativos y costo total de propiedad, separando el Mac personal del despliegue institucional.

El almacenamiento compatible con S3 en Docker permanece como opción en evaluación, no seleccionada; se decidirá con aislamiento, respaldo, recuperación y costos medidos.

El alojamiento de repositorios, pull requests y CI al estilo Bitbucket constituye otro producto/alcance: requiere una evaluación y autorización independientes. No queda implementado ni financiado por aprobar este piloto.

## Criterios de aceptación y decisiones pendientes

- [ ] Equipo piloto y matriz de paridad mínima aprobados, con brechas explícitas.
- [ ] Aislamiento probado en tareas, búsqueda, archivos, IA y Connect, incluida revocación de permisos.
- [ ] Cambio de entidad inequívoco; agregación personal deliberada sin elevar acceso.
- [ ] Workflow/backlog/sprints/roles/auditoría satisfacen los casos imprescindibles del piloto.
- [ ] Migración conciliada, respaldo restaurado y retorno practicable antes de cualquier corte.
- [ ] Responsables de operación y soporte, objetivos de recuperación y costos documentados.
- [ ] Correo sujeto a la aprobación vinculada definida en P1; ni jobs ni IA eluden esa barrera.
- [ ] Archivos y retornos de agentes preservan versiones y aislamiento; evidencia adjunta no implica tarea completada. Reutilizar adjuntos/historial actuales y cerrar sus brechas, sin IDE integrado.

Pendientes: equipo y alcance piloto, roles concretos, historial que se migrará, duración de convivencia, requisitos institucionales de alojamiento y presupuesto medido. **Siguiente acción:** continuar las brechas de P1 identificadas en el registro ODD, sin reiniciar como planeadas las entregas ya verificadas. Preparar despliegue seguro expresamente autorizado y resolver retención/identidad antes de carga real. La fase institucional multiempresa/Jira se mantiene completa en la hoja de ruta: después de estabilizar P1, acordar la matriz de paridad y realizar la auditoría de brechas antes del piloto. No instalar infraestructura ni rediseñar la base de datos por anticipación; este documento no declara esas entregas implementadas.
