# Guía de prueba — Solercia Command con `@solercia/ui` 0.5.0

**Tiempo estimado: 10 minutos.** Todo está encendido y verificado; solo tienes que abrir y seguir los pasos.

---

## Acceso

| | |
|---|---|
| **URL pública** | https://8tg439pz-4242.use2.devtunnels.ms |
| **URL local** | http://localhost:4242 |
| **Usuario** | `admin@solercia.com` |
| **Contraseña** | `Admin123*` |
| **API / Swagger** | http://localhost:8081/docs |

La URL pública funciona desde cualquier red, celular incluido. Es un túnel propio de Solercia Command: no interfiere con el de `solercia_flows` ni con el webhook de Meta.

---

## Qué cambió (para saber qué estás mirando)

Tres componentes que vivían sueltos dentro de Solercia Command ahora son parte de la librería `@solercia/ui` 0.5.0, publicada en npm. Command dejó de apuntar a un archivo `.tgz` local y la consume del registro como cualquier dependencia.

| Componente | Antes | Ahora |
|---|---|---|
| Árbol de proyectos | código local del producto | `sol-tree` de la librería |
| Panel de notificaciones | código local del producto | `sol-notification-panel` de la librería |
| Selector de empresa | código local del producto | `sol-scope-switcher` de la librería |
| Drawer (panel lateral) | copia local duplicada | `sol-drawer` de la librería |

Lo que se movió es el **mecanismo**. Todo lo del negocio — de dónde salen los datos, a dónde navega cada cosa, qué se persiste — se quedó en Command.

---

## Prueba 1 — Árbol de proyectos (3 min)

**Ruta:** `/hierarchy`

Hay 16 proyectos cargados: 5 raíces y 11 con proyecto padre.

1. Entra a `/hierarchy`.
2. **Verifica que las raíces se vean ya expandidas al entrar**, sin que tengas que hacer clic. Este es un cambio deliberado: antes arrancaba todo colapsado y había que expandir para ver lo único que la pantalla existe para mostrar.
3. Revisa que cada nodo conserve lo de siempre: la tarjeta, la etiqueta de metodología, la fracción de avance (`hechas/total`) y la barra de progreso con su color según el porcentaje.
4. Haz clic en el chevron de un proyecto con hijos: debe plegar y desplegar.
5. **Prueba el teclado** (aquí hay un arreglo nuevo): pon el foco en un nodo con `Tab` y muévete con `↑` y `↓`. El foco debe pasar de una fila a la siguiente de forma predecible. Antes, la tecla presionada en un nodo anidado la reprocesaban también sus padres y el foco terminaba en el nodo equivocado.
6. Con `→` expandes, con `←` colapsas. Con `Enter` sobre una hoja navegas al proyecto.
7. Haz clic en un nodo: debe llevarte al detalle del proyecto, igual que antes.

---

## Prueba 2 — Selector de empresa (2 min)

**Dónde:** en el encabezado, visible en cualquier pantalla ya autenticado.

Te creé una segunda empresa para que puedas probarlo de verdad; con una sola no se aprecia nada.

1. Abre el selector. Deben aparecer **dos**: `Solercia` y `Acme Consultores`, cada una con tu rol debajo del nombre.
2. **Fíjate en que el rol ahora se ve también en el botón**, no solo al desplegar.
3. **Verifica que el desplegable NO se recorte** contra el borde del encabezado. Antes podía quedar cortado; ahora se proyecta por encima de todo.
4. Prueba el teclado: abre con `Enter`, muévete con las flechas, cierra con `Escape`. El foco debe volver al botón al cerrar.
5. Cambia a `Acme Consultores`. La aplicación debe recargar el contexto completo.

> ⚠️ **Esperado, no es un error:** `Acme Consultores` está recién creada y **vacía**. Al cambiarte, vas a ver listas sin datos por todos lados. Eso está bien: lo que se prueba es que el cambio de empresa funcione y que no queden datos de la anterior. Vuelve a `Solercia` para seguir.

---

## Prueba 3 — Panel de notificaciones (2 min)

**Dónde:** el ícono de campana en el encabezado. Hay notificaciones sembradas.

1. Ábrelo. Debe listar las notificaciones con su etiqueta de tipo y el tiempo relativo ("hace 2 h").
2. Verifica el contador de no leídas.
3. Prueba **Marcar como leída** en una fila, y **Marcar todas como leídas**.
4. Haz clic sobre la fila de una notificación de tarea: debe navegar a esa tarea. Antes esto era un botón chiquito; ahora toda la fila es clicable, que es mucho más fácil de acertar.
5. Cierra con el botón del encabezado, con `Escape` y haciendo clic afuera.

**Lo más importante de esta pantalla:** ahora distingue "no tienes notificaciones" de "no pudimos cargarlas". Antes una carga fallida se veía igual que una bandeja vacía, y esa confusión estaba registrada como deuda en la auditoría del producto. Si quieres forzarlo, apaga el backend (`make off` en otra terminal y vuelve a abrir el panel): debe salir un error explícito con botón de **Reintentar**, no un "no tienes notificaciones" mentiroso.

---

## Prueba 4 — Drawer migrado (2 min)

El panel lateral duplicado se eliminó; ahora es el de la librería. Revisa que abra y cierre bien en:

1. `/connections` → botón de crear conexión (y el de credenciales).
2. `/projects` → editar un proyecto.
3. `/projects/:id` → abre una tarea del tablero; el detalle sale en el panel lateral.

En el **cronograma** de un proyecto, el detalle debe abrirse con un velo suave, **sin desenfocar el fondo**. En el resto, el fondo sí se desenfoca. Esa diferencia era un parámetro del componente viejo y se conservó con el sistema de temas.

---

## Lo que NO va a funcionar (dicho de frente)

**La acción "Resolver" del panel de notificaciones desapareció.** El panel viejo tenía tres acciones por fila (Ver tarea · Marcar como leída · Resolver); el componente de la librería solo expone las dos primeras.

No se disimuló mapeando "Resolver" sobre "Marcar como leída", porque eso escribiría un estado distinto en la base de datos fingiendo ser el mismo. La solución correcta es agregarle a la librería la capacidad de acciones extra por fila y publicar un `0.5.1`. Está identificado y pendiente de tu visto bueno.

También vas a ver un aviso de tamaño de paquete al compilar (1,04 MB contra un umbral de aviso de 1,00 MB). Es una guardia que el propio proyecto configuró en su `angular.json`, ya se excedía antes de este trabajo, y el umbral que rompe la compilación es 2 MB. No bloquea nada.

---

## Comandos

```bash
cd /Users/camilocalderont/Proyectos/SOLERCIA/solercia-command

make status      # semáforo de cada pieza con sus URLs
make logs        # logs del front
make off         # apaga todo (los datos de la base se conservan)
make on          # vuelve a encender
make help        # todos los objetivos disponibles
```

## Puertos (ninguno se pisa con los otros productos)

| Producto | Front | API | Base de datos |
|---|---|---|---|
| **Solercia Command** | 4242 | 8081 | 5434 · Redis 6380 |
| solercia_flows | 4200 | 3000 / 8000 | 5433 |
| solercia_security | 14200 | 18000 | 15432 · pruebas 5432 |

Durante este montaje aparecieron dos colisiones reales que quedaron corregidas: el Postgres de Command chocaba con el contenedor de pruebas de `solercia_security` (que publica el 5432 abierto), y el script `npm start` del front apuntaba al 4200, el puerto de `solercia_flows`.
