# CICLO 1
Recupera el contexto del proyecto gestion_proyectos con mem_context, y para el detalle de la última fase usa mem_get_observation(id: 954). Luego continúa: el siguiente paso es el motor de alertas.

1.  ajusta lo que hay que agregar a un repositorio e inicia un commit inicial seguro sin archivos que tengan compromiso a nivel de seguridad.

2. Crea un documento en donde muestres cuál es las características que tienen que tener cada una de las metodologías para ver cuál es el estado actual que tenemos y que nos haría falta para desarrollar a nivel de funcionalidad de cada una.
3. Considero que una tarea debería tener la posibilidad de tener una ruta independiente así como las tiene Jira y por lo tanto no sé si sea posible que cada uno de los proyectos también tengan como un código como https://urlbase.com/task/[COD_PROYECTO]-[ID_TAREA] que le permita tener como una convención tipo código-y incremental si eso es posible sería genial porque se reiniciaría cada uno de los ID de las tareas, arrancando de desde 1 en cada proyecto.
4. las tareas deben tener una opción para dejar observaciones así como hace Jira y también tener opción de de crear subtareas esas tareas que contribuyen a tener un 100%, cada subtarea se comporta como otra tarea con las mismas características, en Jira las subtareas no permiten estimación, no se si lo hacemos igual.
5. Las tareas pensando en Planner debería también a ver una vista tipo cuadrilla o cuadrícula en donde yo pueda ver las tareas por cuadrícula.
6. Cuando hay más de 4 columnas en el tablero, se desborda y no se vé bien la última columna, ejemplo en la de Scrum que son 4, la última se ve cortada y deberíamos tener eso de forma más sencilla.
7. En los comentarios debe ser posible arrobar @ a los otros usuarios y esto debe permitir enviar un correo y notificación (esto va cuando tengamos el motor de notificaciones)
8. Se debe permitir adjuntar archivos a las tareas, y a las observaciones de las tareas, de modo que se pueda llevar o complementar el historial.
9. Funcionalidad de cerrar sprints y un backlog que permita ver los sprints en una cuadrilla de tiempo como lo hace jira.
10. hacer la funcionalidad de velocity con este detalle:
Velocity (velocidad del equipo)

Qué es: cuántos story points terminados (columna Done) cierra el equipo por sprint. Nada de "casi", nada de "en progreso" — solo lo HECHO cuenta. Esa es la disciplina.

Cómo se mide en nuestro sistema: al cerrar un sprint, sumo los puntos de las tareas en Done y lo guardo (sprint.completed_points). Con varios sprints tenés una serie → promedio de velocity.

Para qué sirve: para planear con datos, no con ilusión. Si el equipo hace ~30 pts/sprint, no le metés 50 al próximo. Y proyectás: "quedan 120 pts de backlog → ~4 sprints". Burndown te dice cómo va ESTE sprint; velocity te dice cuánto podés comprometer en el próximo.

Y ojo con esto —porque es donde casi todos la cagan—: velocity es por equipo, no por persona, y se mide, no se exige. El día que la uses para comparar equipos o presionar gente, dejó de medir realidad y empezó a medir mentiras infladas. Es una herramienta de planeación, no un látigo.

11. Motor de alertas — en 5 piezas

1. Reglas configurables (tabla alert_rules): condición + umbral. "Tarea vencida", "licencia a X días", "sprint <50% al 75% del tiempo", "tarea bloqueada >N días", "persona sobrecargada". El jefe las prende/apaga por organización.
2. Scheduler (APScheduler sobre Redis): corre cada hora, evalúa las reglas contra la BD, genera notifications. Idempotente — la misma alerta no se duplica (clave + estado activa/resuelta/silenciada).
3. Strategy por tipo de alerta: igual que las metodologías. Alerta nueva = clase nueva, cero cambios en el núcleo. Esto es lo que lo hace mantenible.
4. Canales: in-app (centro de notificaciones + badge), email digest configurable, y tiempo real por Redis pub/sub → WebSocket.
5. Cruce con el trabajo real: la alerta no es solo "venció" — es "venció Y nadie la tocó", cruzando due_date/risk_flag con completed_at y actividad. Eso es lo que Planner NO hace y vos sí querés.

La frase que lo resume: Planner te avisa que algo venció. El nuestro te avisa qué está en riesgo, de quién, y por qué — antes de que explote.



## TAREAS FUTURAS QUE QUIERO VALIDAR
- Integración con el CI/CD o ser el jira de bitbucket, pero para gitlab. Es decir quiero proponer usar gitlab en lugar de bitbucket y luego que podamos tener esa relación que tiene jira con bitbucket a nivel de código pero con gitlab.
- El módulo de notificaciones debe poder tener una sección de notificaciones tipo push, en vivo de manera que se actualice en tiempo real, tambien por correo y generar resumenes como lo hace Microsoft Planner, avisando al usuario que tiene la tarea y a la persona que le supervisa.


## REGLAS
- al máximo procura usar componentes propios para todo, veo que hace falta un buen componente para mejorar la experiencia con las listas desplegables, que permita seleccionar uno, muchos, que permita buscar como parte de la lista, algo como lo que hace bootstrap-select pero 100% a mano con código bk-nombre, no sé si existe pero sería bueno.
- los cuadros de texto se vuelven de texto enriquecido, tambien en lo posible que sea algo personalizado para el tema de los @, de los link de otras tareas, para mostrar imagenes, inclusive tablas, pero si no es posible uno propio, entonces usar uno open source del cual nunca vayamos a tener lío de licencias ni incomtabilidades.





# CICLO 2 DISEÑO
He visto el cambio después de los desarrollos y los ajustes que hiciste el día de ayer y me parecen términos generales que ese color morado le da una una muy buena tonalidad y y combina muy bien con el azul oscuro en la en la vista de oscura la vista Dark sin embargo hay algunas cosas que quisiera revisar de fondo para que quedará bien ajustado lo primero es que todos los modales o los cuadros de diálogo por ejemplo para crear usuarios para agregar roles a los usuarios está nos están centrando en la digamos cómo se tenía antes del cambio si estaban bien centrados en toda la pantalla entonces los los campos se ocultan o se ven muy en la parte de arriba y no no se alcanza a ver el modo completo entonces ahí ahí como un error que se revisar y ajustar por otro lado en el otro agente dice que creo un componente para las listas desplegables pero en realidad yo no vi el cambio no no me pareció que que que haya cambiado y dice que él esos componentes le puso un prefijo de SP y te comentó qué es lo que yo quiero realmente lo que yo quiero es crear un conjunto de herramientas y de componentes de vaquen de Front perdón de Front en angular que sean lo suficientemente versátiles en el sentido en que se les pueda cambiar de piel muy rápidamente con el Jason y se puedan usar en diferentes proyectos sin que se parezcan y que sin que se vean que son lo mismo cambiar en colores en fuentes en tamaños en bordes en sombras en Blur en animaciones de cómo se abren los elementos o cómo suceden las transiciones y por eso cuando iniciar el proyecto de boki-front pues la idea era crear componentes propios para en lo posible no depender de de otras dependencias o instalaciones que puedan agregar complejidad de mantenimiento más adelante sino que se puedan pues utilizar esas herramientas propias yo tengo ya que recuerde un un componente de formulario un componente de tarjeta de Card tengo un componente de data Table que permite inclusive hacer filtros con un campo externo y también ordenamiento de columnas y realmente lo que yo quiero es conservar lo mismo a veces lo qué pasa cuando utilizamos agentes es que yo le digo pásate en este código y en últimas pues copia aparte pero no copia todo y entonces para evitar eso y poder tener la biblioteca actualizada yo quiero que me digas cómo yo puedo crear un paquete y que yo pueda aportar entre proyectos que sea de estos componentes incluyendo la la parametrización dinámica de los de los estilos sí por qué porque a cada seguramente van a salir otras otros componentes a crear por ejemplo acá va a tener mucha importancia del tema de las listas desplegables hay unas cosas que no me gustan para nada en este momento son por ejemplo como se se asocian los roles a una persona cuando es un sistema pequeño pues listar los roles en el mismo de modal pues está bien sin embargo cuando cuando son más de 20 opciones pues los roles hacia abajo se van a ver mal y eso debería tener otra forma más elegante para poderlo administrar se desaprovecha mucho también a veces la pantalla porque el modal que se abre tiene más o -1 50% de de ancho y sería bueno que tuviera mucho más ancho y en la vista móvil pues todo debería ir hacia abajo en la vista móvil en general me parece que están bien sin embargo a pesar y cambio en general el color el tema del del del Blur que se muestra cuando se abre uno al se ve un poco más moderno yo sigo viendo los mismos recuadro las mismas las tarjetas me parece que no no no no mejoraron mucho se ven muy parecido a lo que ya estaba no veo no sé si el concepto para mí es de de moderno es que tenga como brillantes que sean como algo estilo neón que tengan fondos que se muevan con con conforme se mueve el Mouse creo que me estoy imaginando unos unos estilos que realmente tengan muchas más transiciones cuando yo vaya explorando en un panel de administrador vayan apareciendo los dos componentes o los carta medidas que yo le hago scroll Down eso es lo que más o menos yo estaba pensando y justo yo no sé si eso puede estar dentro del alcance de lo que hablamos porque pues ya salta un poco más allá de cambiar la piel de cambiar el el estilo en las fuentes y ya empezamos a hablar de comportamientos dinámicos entre componentes sin embargo lo pongo sobre la mesa y quiero que que me ayudes a a revisarlo en cuanto a la Skill que yo te comentaba es existía que tú me decías pues que eso no solucionaba todo pues de todas maneras me gustaría validarlo para ver si lo podemos instalar porque la herramienta del Cloud Design me parece que es muy buena y no sé si de ahí de Claudine podríamos nosotros basarnos o inspirarnos para mejorarlo en resumen acá necesito dos cosas la primera es una orientación una planificación de cómo poder tener una librería de componentes compartida que yo pueda más adelante licenciado o patentar porque de todas maneras este trabajo a mí me gustaría mucho que si yo pudiera vender o entregar bajo sobar o distribuir libremente el software en entidades públicas pues me gustaría mucho que que se pudiera patentar el código sí para que eso se quede muy claro es un código que solamente hice yo y solamente está hecho con esta arquitectura por mí y de esa manera más adelante pueda llegar a tener algunos contratos de de proveedor exclusivo de contratación directa entonces pues dicho eso si era también poner dentro de uno de los puntos el tema de organizar los modales de todas mandar capturas de pantalla de eso para que te descuenta que algunas cosas y sobre todo esto de los quedaron mal porque se ven muy elevados entonces yo estoy seguro que es un tema de de algún estilo que se cambió y que no se debió haber cambiado.

---

## CICLO 2 — Instrucciones procesadas y estado

> Transcripción de arriba convertida a instrucciones accionables. Plan formal (proposal + fases + tareas marcables): **`openspec/changes/cycle2-design-system/`**.

### Instrucciones (qué se pidió)

**A. Bugs**
- A1. Modales descentrados: se cortan arriba, no se ve el formulario completo (regresión de estilo).
- A2. Modales angostos (~50% ancho): hacerlos más anchos; en móvil, todo apilado hacia abajo.

**B. UX**
- B1. Asignar roles con +20 opciones: el checkbox-list se ve mal; patrón más elegante (buscable/multiselección).
- B2. Listas desplegables: dropdown/select propio sólido (existe `bk-select`, falta usarlo donde corresponde).

**C. Estratégico (orientación → ahora ejecución)**
- C1. Librería de componentes propia `@boki/ui`, "skin por JSON" (color, fuente, tamaño, borde, sombra, blur, animaciones), sin depender de UI de terceros, conservando form/card/data-table.
- C2. Empaquetar/versionar para compartir entre proyectos sin copia-pega.
- C3. Licenciar/patentar como autoría propia (derecho de autor + registro DNDA; "patente" no aplica al código).

**D. Exploratorio**
- D1. Look más dinámico (neón/glow/glass + fondos reactivos al mouse + scroll-reveal). Es comportamiento, no solo "piel".
- D2. Validar el skill `frontend-design` (ya instalado).

**Transversal:** best practices de creación de paquetes, **logging** y **manejo de excepciones** en el front.

### Estado (¿en qué vamos?)

| Fase | Descripción | Estado |
|------|-------------|--------|
| 0 | Bugfix modales centrados + evidencia | ✅ HECHO (`bee1a27`, `docs/screenshots/modales/`) |
| 1 | Plan de librería | ✅ HECHO (`docs/libreria-componentes-plan.md`) |
| 2 | Arrancar `@boki/ui` (scaffold + theme + logging + errores + base + build) | 🔵 EN CURSO |
| 3 | Quick wins UX (modales anchos/móvil, roles→`bk-select`, animaciones de apertura) | ⬜ PENDIENTE |
| 4 | Migrar la app a consumir `@boki/ui` | ⬜ PENDIENTE |
| 5 | Spike "vibe" dinámico (glass/glow/scroll-reveal opt-in) | ⬜ PENDIENTE (opcional) |
| 6 | Publish privado + LICENSE + registro DNDA | ⬜ PENDIENTE |

Checklist marcable y validación: `openspec/changes/cycle2-design-system/tasks.md`.