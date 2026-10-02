# Paridad de interfaz: Solercia Command frente al shell Angular de PANDORA

Fecha de la medición: 2 de octubre de 2026.

Este documento registra la comparación visual entre el frontend de Solercia Command y el shell
Angular de PANDORA con el mismo tema, el mismo menú y la misma persona en sesión. Cada diferencia
medida queda con su causa y su clasificación. Los números salen de `resultados.json`; las imágenes
de `imagenes/` son un subconjunto de las capturas.

## Resumen

- 48 combinaciones de escena, viewport y modo: 40 comparadas en vivo, 6 que no aplican y 2 sin
  referencia. Ninguna se comparó contra capturas previas: los dos frontends se sirvieron en local.
- Regiones con 0 % de diferencia en todas sus combinaciones: logo del header, menú móvil inferior,
  página de error 403 al llegar desde el shell, migas de pan a 390 px y diálogo de confirmación del
  Theme Studio.
- Las demás diferencias tienen causa identificada. Dos eran defectos del porte y se corrigieron en
  Command; el resto corresponde a alcance, a datos propios de cada pantalla o a decisiones de
  producto que siguen abiertas.
- Ruido de captura: dos corridas completas dieron 226 de 228 capturas idénticas píxel a píxel por
  lado. Las dos restantes son del Theme Studio de PANDORA a 1440 px en claro, cuyo alto varió 6 px
  en una corrida (`ruido.json`).

| Escena | Página completa (peor caso) | Por región (peor caso) |
|---|---|---|
| Shell completo con tabla | 15,18 % | encabezado 3,99 % · logo 0,00 % · sidebar 1,59 % · menú inferior 0,00 % · tabla 29,52 % (común 6,09 %) |
| Sidebar abierto con tres niveles | 2,50 % | sidebar 1,59 % |
| Sidebar colapsado | 2,38 % | sidebar 0,70 % |
| Menú móvil inferior y hoja «Más» | 0,38 % | menú inferior 0,00 % · hoja 0,11 % |
| Menú de usuario abierto | 4,94 % | disparador 1,50 % · panel 20,38 % (común 0,81 %) |
| Migas de pan | 2,31 % | migas 22,03 % (común 2,53 %) |
| Diálogo de confirmación | 30,64 % | diálogo 26,10 % (común 10,81 %) |
| Página de error 403, llegada desde el shell | 0,00 % | estado 0,00 % |
| Página de error 403, carga directa | 2,03 % | estado 15,08 % |
| Theme Studio inicial | 4,61 % | estudio 5,09 % (común 4,93 %) |
| Theme Studio con el historial abierto | 4,31 % | historial 1,19 % · estudio 4,78 % (común 4,64 %) |
| Theme Studio tras restaurar una versión | 3,73 % | diálogo 0,00 % · alerta 0,17 % · estudio 4,09 % · historial 0,69 % |

El peor caso se toma entre 1440×900 y 390×844 y entre claro y oscuro. «Común» es el porcentaje
dentro del área que comparten las dos capturas cuando sus tamaños difieren.

## Versiones comparadas

| Lado | Repositorio y rama | Commit | `@solercia/ui` | Angular |
|---|---|---|---|---|
| PANDORA | `pandora_front`, `feature/shared-migracion-angular-pandora` | `d4884a12d208a7791910838b92d6f1281595d636` | 0.6.1 | 22.1.4 |
| Command | `solercia-command/frontend`, `feat/ui-shell-pandora` | `c875c10d65e023e4c3c93b3df2be3ca325abca8b` | 0.6.1 | 22.0.6 |

Navegador: Chromium `chrome-headless-shell` (compilación 1243 de Playwright). Arnés:
`playwright-core` 1.63.0, `pixelmatch` 7.2.0, `pngjs` 7.0.0. Tema de comparación:
`pandora_front/src/assets/themes/idartes.json`.

## Método

1. **Dos frontends locales, sin backend.** Cada repositorio se sirve con `ng serve` en un puerto
   propio. PANDORA arranca con una configuración de proxy vacía, de modo que su servidor de
   desarrollo no reenvía nada a la pasarela. El repositorio de PANDORA se usa en solo lectura:
   `git status --short` quedó igual antes y después.
2. **Toda la API se intercepta en el navegador.** `capture.mjs` resuelve cada petición con
   `simulacion.mjs`, que traduce los datos neutros de `datos/sintetico.json` al contrato de cada
   lado: el mismo árbol de menú de tres niveles, la misma persona, el mismo tema y el mismo
   historial de versiones. El logo del tema se sirve a Command desde los assets de PANDORA. Una
   petición sin simular responde 404 y queda registrada; la corrida final no registró ninguna.
3. **Red cerrada.** Solo se permite `localhost` y las fuentes de Google que usa el tema (Inter). La
   corrida final no bloqueó ninguna otra salida y la fuente cargó en los dos lados en todas las
   escenas.
4. **Condiciones fijas.** 1440×900 y 390×844, factor de escala 1, `es-CO`, zona `America/Bogota`,
   reloj fijo y animaciones anuladas. PANDORA se abre por `localhost`, que es el nombre de host con
   el que resuelve la entidad del tema.
5. **Modo claro y oscuro.** El tema declara `meta.defaultMode: light` y la librería lo impone en
   cada carga, en los dos lados. El modo oscuro se alcanza con el botón de tema del header.
6. **Comparación.** `pixelmatch` con umbral 0,1 sobre la página completa y sobre cada región
   recortada por selector. Si los tamaños difieren, se compara el área común y el sobrante de la
   unión cuenta como diferente; así el porcentaje no depende del color de relleno ni del modo.
7. **Estilos calculados.** Para los elementos de cada región se comparan 31 propiedades de
   `getComputedStyle`. Sirve para separar una diferencia de estilo de una de contenido. Los colores
   de borde solo cuentan cuando el borde se pinta.

Datos sintéticos únicamente: no hay nombres, correos ni documentos de personas reales, y el nombre
de la entidad se reemplaza por «Organización de Prueba» en los dos lados.

## Cómo reproducir

```bash
# 1. Dependencias del arnés, fuera del repositorio
mkdir -p "$TMP/paridad" && cd "$TMP/paridad" && npm init -y && npm install playwright-core pixelmatch pngjs
echo '{}' > "$TMP/paridad/proxy-vacio.json"

# 2. Los dos frontends
(cd frontend && npx ng serve --host localhost --port 54311)
(cd "$PANDORA_FRONT" && npx ng serve --host localhost --port 54312 --proxy-config "$TMP/paridad/proxy-vacio.json")

# 3. Capturas y comparación
DEPS="$TMP/paridad" OUT="$TMP/paridad/salida" CHROME=<ejecutable de Chromium> \
PANDORA_FRONT=<raíz de pandora_front> node docs/paridad-ui-pandora/arnes/capture.mjs
```

Variables opcionales: `COMMAND_URL` y `PANDORA_URL` (por defecto los puertos de arriba) y `ONLY`
(expresión regular sobre `escena__viewport__modo`). Utilidades: `tabla.mjs` imprime la tabla de este
documento, `ruido.mjs` compara dos corridas y `hoja.mjs` arma las imágenes de `imagenes/`.

## Diferencias y su causa

### a. Deliberadas por alcance

| Diferencia | Regla que la respalda | Efecto medido |
|---|---|---|
| El header de PANDORA lleva el selector de módulos; el de Command, el selector de organización y la campana. | Encargo, punto 7: no se porta el selector de módulos. Documento de tareas: se conservan el selector de organización y la campana. | Encabezado 1,85–1,88 % a 1440 px y 3,38–3,99 % a 390 px. |
| PANDORA pinta el footer institucional. | Encargo, punto 7. | El área principal mide 864 px en PANDORA y 900 px en Command a 1440 px; a 390 px la página de PANDORA mide 925 px y la de Command 844 px. Explica la mayor parte del 14–15 % de página completa del shell móvil. |
| El sidebar de PANDORA lleva su marca al pie; el de Command agrega la entrada «Vista previa de tareas» al final del menú. | Encargo, punto 7 (lo exclusivo de PANDORA no se porta) y punto 6 (se conserva lo propio de Command). | Sidebar 1,47–1,59 % abierto y 0,64–0,70 % colapsado; hoja «Más» 0,11 %. |
| En PANDORA las migas viven dentro del puente legacy y su primer tramo es el módulo, con enlace; en Command viven en el layout y los grupos no enlazan. | Encargo, punto 7: no se portan el puente legacy ni el selector de módulos. | A 1440 px la barra mide 40 px en PANDORA y 32 px en Command (2,48–2,53 % en el área común). A 390 px, 0 %. Para comparar el mismo camino, el menú de Command se envuelve en un nodo con el nombre del módulo. |
| En carga directa, la página de error de PANDORA usa el tema de la entidad y la de Command el tema por defecto. | Encargo, punto 7: no se porta la entidad por nombre de host. Command carga el tema de la organización al entrar al shell. | Estado de error 11,91–15,08 % en carga directa (color primario y fuente de títulos). Al llegar desde el shell, 0 % en los cuatro casos. |
| El Theme Studio de Command no ofrece «Adjuntar imagen» y adapta tres textos (sin referencias al legacy, con el nombre del producto). | Documento de tareas: la carga de logo queda fuera de alcance por ahora. Encargo, punto 7. | Estudio 2,48–5,09 %. La primera tarjeta mide 469 px en PANDORA y 439 px en Command a 1440 px, y desplaza lo que sigue. |
| Los `<button>` de Command heredan la tipografía del documento (14 px, interlineado 21 px); los de PANDORA conservan la del navegador (13,33 px). | Encargo, punto 8, y decisión del documento de tareas: Tailwind se queda en la versión 3, cuya hoja base normaliza los botones. | Los íconos dentro de un botón quedan 1 px más arriba en Command: flecha del sidebar, flecha del menú de usuario y cierre de alertas y hojas. Disparador 0,85–1,50 %; alerta 0,15–0,17 %. Las cajas miden lo mismo. |
| Command declara Inter 400–700 y Manrope; PANDORA declara Inter 400–600. | Encargo, punto 6: se conserva lo propio de Command, cuyas pantallas usan el peso 700. | El texto en negrita 700 se pinta con 600 en PANDORA. Historial 0,30–1,19 %. |
| El ícono de las actividades nativas es verde en PANDORA. | Encargo, punto 7: distingue lo nativo de lo legacy. | Sin medir: el grupo que contiene esa actividad quedó cerrado en las escenas. Se constató en el código. |

### b. Dato distinto inevitable

| Diferencia | Causa | Efecto medido |
|---|---|---|
| Tabla. | Son pantallas distintas sobre el mismo `sol-data-table`: la de PANDORA exige un filtro, tiene buscador, paginación, ocho columnas y acciones al inicio; la de Command tiene cinco columnas y acciones al final. | 26,14–29,52 % (3,22–6,09 % en el área común). Los estilos calculados del contenedor, los encabezados y las celdas coinciden salvo el ancho de columna. |
| Diálogo de confirmación de la tabla. | Acciones y textos distintos («desactivar» frente a «eliminar»). | 15,32–26,10 %. El alto pasa de 174 px a 192 px o 210 px por el largo del mensaje; los demás estilos calculados coinciden. Con el mismo texto, el diálogo del Theme Studio da 0 %. |
| Insignia del menú de usuario. | PANDORA muestra el nombre corto de la entidad y Command el rol. Los datos sintéticos ponen el mismo texto en los dos lados. | Sin efecto en la medición. |

### c. Defectos del porte, corregidos

| Defecto | Corrección | Antes → después |
|---|---|---|
| A 390 px, con una sola organización, el selector no se reducía a su avatar y las acciones del header tapaban el logo y el botón de tema. La regla existente solo cubría la variante con varias organizaciones. | `frontend/src/styles.scss`, líneas 466–471. Commit `a524de7`. | Logo 8,15 % → 0 %; encabezado 11,28 % → 3,99 % (claro). |
| La nota del reloj de soporte decía «America/Bogota» sin el desfase «(UTC−05:00)» que muestra PANDORA. | `frontend/src/widgets/user-menu/ui/user-menu.component.ts`, líneas 360–378, y `frontend/src/assets/i18n/es-CO.json`, línea 1566. Commit `c875c10`. | El bloque del reloj pasa de 78 px a 96 px, igual que en PANDORA, y deja de aparecer en la comparación de estilos. |

### d. Librería `@solercia/ui`

No se encontró ninguna diferencia atribuible a la librería: los dos lados usan la 0.6.1 y las
regiones que dependen solo de ella dieron 0 % o quedaron explicadas por las causas de arriba. Los
límites ya registrados en el documento de tareas (textos del historial en «usted», rechazo de
`primitives.breakpoint` al importar, logo ancho en la vista previa) se ven igual en los dos lados y
no son diferencias de paridad.

### e. Decisiones de producto pendientes

No se tomó ninguna. Quedan abiertas:

- **Entradas «Perfil» y «Apariencia» del menú de usuario.** PANDORA las muestra; Command solo
  «Ayuda y soporte» y «Cerrar sesión». El panel mide 299 px frente a 240 px (20,38 %; 0,81 % en el
  área común). «Apariencia» depende de la decisión sobre el guard de administrador del Theme
  Studio, y la página de perfil no se portó.
- **Guard de administrador del Theme Studio.** La ruta está abierta a toda persona con sesión, como
  en PANDORA.
- **Canal de ayuda.** El panel de Command abre sin catálogo ni enlace de soporte. La ayuda
  contextual de PANDORA depende de su configuración de servidor y se dejó apagada en la medición.
- **Estado inicial y auto-cierre del sidebar.** Sin preferencia guardada, PANDORA arranca colapsado
  y Command expandido. El auto-cierre al navegar lo declara el tema; el de la comparación lo
  activa en los dos lados. El arnés fija el estado en cada escena.
- **Interfaz de restablecer el tema**, **interceptor de errores** y **organización activa tras
  iniciar sesión**: sin cambios frente a lo registrado en el documento de tareas.

## Cobertura

- **Sin referencia (2):** página de error 403 en carga directa y modo oscuro, en los dos viewports.
  Sin header no hay botón de tema y el tema de PANDORA impone el modo claro.
- **No aplica (6):** sidebar abierto y colapsado a 390 px, donde lo reemplaza el menú inferior, y
  menú inferior a 1440 px.
- **Tras restaurar una versión**, claro y oscuro dan el mismo resultado: aplicar el tema vuelve a
  imponer su modo por defecto en los dos lados.
- **Fuera de esta medición:** páginas 401, 404 y 500; estados de carga, vacío y error del menú;
  panel de ayuda; centro de notificaciones; inicio de sesión; importación y exportación del Theme
  Studio, su panel móvil de vista previa y la paginación del historial con más de 20 versiones;
  anchos intermedios; comportamiento del auto-cierre del sidebar al navegar.

## Detalle por escena, viewport y modo

| Escena | Viewport | Modo | Estado | Página completa | Por región |
|---|---|---|---|---|---|
| Shell completo con tabla | 1440×900 | claro | comparada en vivo | 2,48 % | encabezado 1,88 % · logo 0,00 % · sidebar 1,59 % · tabla 26,14 % (común 3,22 %; 1152×532 / 1152×406) |
| Shell completo con tabla | 1440×900 | oscuro | comparada en vivo | 3,31 % | encabezado 1,85 % · logo 0,00 % · sidebar 1,47 % · tabla 26,27 % (común 3,39 %; 1152×532 / 1152×406) |
| Shell completo con tabla | 390×844 | claro | comparada en vivo | 14,14 % | encabezado 3,99 % · logo 0,00 % · menú inferior 0,00 % · tabla 29,46 % (común 6,01 %; 358×505 / 358×379) |
| Shell completo con tabla | 390×844 | oscuro | comparada en vivo | 15,18 % | encabezado 3,38 % · logo 0,00 % · menú inferior 0,00 % · tabla 29,52 % (común 6,09 %; 358×505 / 358×379) |
| Sidebar abierto con tres niveles | 1440×900 | claro | comparada en vivo | 1,76 % | sidebar 1,59 % |
| Sidebar abierto con tres niveles | 1440×900 | oscuro | comparada en vivo | 2,50 % | sidebar 1,47 % |
| Sidebar abierto con tres niveles | 390×844 | claro | no aplica | — | A 390 px el sidebar no se pinta: lo reemplaza el menú inferior. |
| Sidebar abierto con tres niveles | 390×844 | oscuro | no aplica | — | A 390 px el sidebar no se pinta: lo reemplaza el menú inferior. |
| Sidebar colapsado | 1440×900 | claro | comparada en vivo | 1,55 % | sidebar 0,70 % |
| Sidebar colapsado | 1440×900 | oscuro | comparada en vivo | 2,38 % | sidebar 0,64 % |
| Sidebar colapsado | 390×844 | claro | no aplica | — | A 390 px el sidebar no se pinta: lo reemplaza el menú inferior. |
| Sidebar colapsado | 390×844 | oscuro | no aplica | — | A 390 px el sidebar no se pinta: lo reemplaza el menú inferior. |
| Menú móvil inferior y hoja «Más» | 1440×900 | claro | no aplica | — | A 1440 px el menú inferior no se pinta: navega el sidebar. |
| Menú móvil inferior y hoja «Más» | 1440×900 | oscuro | no aplica | — | A 1440 px el menú inferior no se pinta: navega el sidebar. |
| Menú móvil inferior y hoja «Más» | 390×844 | claro | comparada en vivo | 0,38 % | menú inferior 0,00 % · hoja 0,11 % |
| Menú móvil inferior y hoja «Más» | 390×844 | oscuro | comparada en vivo | 0,11 % | menú inferior 0,00 % · hoja 0,11 % |
| Menú de usuario abierto | 1440×900 | claro | comparada en vivo | 1,57 % | disparador 0,85 % · panel 20,37 % (común 0,79 %; 288×299 / 288×240) |
| Menú de usuario abierto | 1440×900 | oscuro | comparada en vivo | 2,26 % | disparador 0,87 % · panel 20,38 % (común 0,80 %; 288×299 / 288×240) |
| Menú de usuario abierto | 390×844 | claro | comparada en vivo | 4,64 % | disparador 1,47 % · panel 20,37 % (común 0,79 %; 288×299 / 288×240) |
| Menú de usuario abierto | 390×844 | oscuro | comparada en vivo | 4,94 % | disparador 1,50 % · panel 20,38 % (común 0,81 %; 288×299 / 288×240) |
| Migas de pan | 1440×900 | claro | comparada en vivo | 0,97 % | migas 21,98 % (común 2,48 %; 1152×40 / 1152×32) |
| Migas de pan | 1440×900 | oscuro | comparada en vivo | 1,53 % | migas 22,03 % (común 2,53 %; 1152×40 / 1152×32) |
| Migas de pan | 390×844 | claro | comparada en vivo | 1,89 % | migas 0,00 % |
| Migas de pan | 390×844 | oscuro | comparada en vivo | 2,31 % | migas 0,00 % |
| Diálogo de confirmación | 1440×900 | claro | comparada en vivo | 2,97 % | diálogo 15,32 % (común 6,56 %; 448×174 / 448×192) |
| Diálogo de confirmación | 1440×900 | oscuro | comparada en vivo | 1,52 % | diálogo 15,42 % (común 6,67 %; 448×174 / 448×192) |
| Diálogo de confirmación | 390×844 | claro | comparada en vivo | 30,64 % | diálogo 25,92 % (común 10,60 %; 360×174 / 360×210) |
| Diálogo de confirmación | 390×844 | oscuro | comparada en vivo | 27,96 % | diálogo 26,10 % (común 10,81 %; 360×174 / 360×210) |
| Página de error 403 (llegada desde el shell) | 1440×900 | claro | comparada en vivo | 0,00 % | estado 0,00 % |
| Página de error 403 (llegada desde el shell) | 1440×900 | oscuro | comparada en vivo | 0,00 % | estado 0,00 % |
| Página de error 403 (llegada desde el shell) | 390×844 | claro | comparada en vivo | 0,00 % | estado 0,00 % |
| Página de error 403 (llegada desde el shell) | 390×844 | oscuro | comparada en vivo | 0,00 % | estado 0,00 % |
| Página de error 403 (carga directa) | 1440×900 | claro | comparada en vivo | 0,79 % | estado 15,08 % |
| Página de error 403 (carga directa) | 1440×900 | oscuro | sin referencia | — | En carga directa no hay botón de tema y el tema de PANDORA impone el modo claro; no hay captura oscura comparable. |
| Página de error 403 (carga directa) | 390×844 | claro | comparada en vivo | 2,03 % | estado 11,91 % |
| Página de error 403 (carga directa) | 390×844 | oscuro | sin referencia | — | En carga directa no hay botón de tema y el tema de PANDORA impone el modo claro; no hay captura oscura comparable. |
| Theme Studio inicial | 1440×900 | claro | comparada en vivo | 2,75 % | estudio 2,58 % (común 2,39 %; 1152×5283 / 1152×5273) |
| Theme Studio inicial | 1440×900 | oscuro | comparada en vivo | 2,85 % | estudio 2,70 % (común 2,52 %; 1152×5283 / 1152×5273) |
| Theme Studio inicial | 390×844 | claro | comparada en vivo | 4,12 % | estudio 4,55 % (común 4,39 %; 358×5899 / 358×5909) |
| Theme Studio inicial | 390×844 | oscuro | comparada en vivo | 4,61 % | estudio 5,09 % (común 4,93 %; 358×5899 / 358×5909) |
| Theme Studio con el historial abierto | 1440×900 | claro | comparada en vivo | 2,64 % | historial 0,67 % · estudio 2,48 % (común 2,30 %; 1152×5601 / 1152×5591) |
| Theme Studio con el historial abierto | 1440×900 | oscuro | comparada en vivo | 2,73 % | historial 0,66 % · estudio 2,60 % (común 2,42 %; 1152×5601 / 1152×5591) |
| Theme Studio con el historial abierto | 390×844 | claro | comparada en vivo | 3,87 % | historial 1,19 % · estudio 4,30 % (común 4,15 %; 358×6546 / 358×6556) |
| Theme Studio con el historial abierto | 390×844 | oscuro | comparada en vivo | 4,31 % | historial 1,18 % · estudio 4,78 % (común 4,64 %; 358×6546 / 358×6556) |
| Theme Studio tras restaurar una versión | 1440×900 | claro | comparada en vivo | 3,01 % | diálogo 0,00 % · alerta 0,17 % · estudio 2,91 % (común 2,74 %; 1152×5661 / 1152×5651) · historial 0,69 % |
| Theme Studio tras restaurar una versión | 1440×900 | oscuro | comparada en vivo | 3,01 % | diálogo 0,00 % · alerta 0,17 % · estudio 2,91 % (común 2,74 %; 1152×5661 / 1152×5651) · historial 0,69 % |
| Theme Studio tras restaurar una versión | 390×844 | claro | comparada en vivo | 3,73 % | diálogo 0,00 % · alerta 0,15 % · estudio 4,09 % (común 3,95 %; 358×6661 / 358×6671) · historial 0,30 % |
| Theme Studio tras restaurar una versión | 390×844 | oscuro | comparada en vivo | 3,73 % | diálogo 0,00 % · alerta 0,15 % · estudio 4,09 % (común 3,95 %; 358×6661 / 358×6671) · historial 0,30 % |

## Imágenes

Cada imagen muestra PANDORA, Command y el mapa de diferencias, en ese orden. En el mapa, el rojo
marca los píxeles distintos y el área sobrante cuando los tamaños difieren.

| Archivo | Contenido |
|---|---|
| `01-shell-d1440-claro.png`, `02-shell-d1440-oscuro.png`, `03-shell-m390-claro.png` | Shell completo con tabla. |
| `04-sidebar-abierto-d1440-claro.png`, `05-sidebar-colapsado-d1440-oscuro.png` | Sidebar. |
| `06-menu-movil-mas-m390-claro.png` | Menú inferior con la hoja «Más». |
| `07-menu-usuario-panel-d1440-claro.png` | Panel del menú de usuario. |
| `08-migas-d1440-claro.png` | Migas de pan. |
| `09-confirmacion-dialogo-d1440-claro.png`, `15-estudio-confirmacion-m390-claro.png` | Diálogo de confirmación: tabla y Theme Studio. |
| `10-error-403-d1440-oscuro.png`, `11-error-403-directa-estado-d1440-claro.png` | Página de error 403: desde el shell y en carga directa. |
| `12-estudio-inicial-d1440-claro.png`, `13-estudio-historial-d1440-claro.png`, `14-estudio-restaurada-d1440-claro.png` | Theme Studio: inicial, historial y tras restaurar (primeros 900 px). |

El conjunto completo (228 capturas y 114 mapas de diferencias, unos 37 MB) queda fuera del
repositorio y se regenera con el arnés.
