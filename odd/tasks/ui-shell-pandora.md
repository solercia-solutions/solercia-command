# UI alineada al shell de PANDORA — ODD

## Objetivo

Que el frontend de Solercia Command adopte `@solercia/ui` `^0.6.1` y se vea igual que el shell
Angular de PANDORA (`pandora_front`), copiando sus patrones de UI, con el Theme Studio de la
librería completo y un historial de versiones de tema por organización.

## Problema y motivo

El shell actual es una copia de boki-front anterior al porte de PANDORA y vive dentro de
`AppComponent`. La librería está en 0.5.0, el tema por organización no tiene historial y la pantalla
de apariencia es propia. Command necesita personalización fuerte por organización y un aspecto
consistente con PANDORA.

## Fuentes

- Encargo: `pandora-docs/shared/user-stories/2026-06-05-MIGRACION-UI-PANDORA/2026-10-02-prompt-ui-solercia-command.md`.
- Inventario bloque por bloque: `2026-10-02-inventario-ui-pandora-para-solercia-command.md` (misma carpeta).
- Fuente de verdad visual: `IDARTES/pandora_proxy/pandora_front`, rama `feature/shared-migracion-angular-pandora`. Solo lectura.
- Fuente para copiar el shell: worktree `SOLERCIA/solercia_flows/boki-front-worktrees/solercia-port-pandora-front`
  (rama `feature/solercia-port-pandora-front`, nacida sobre la librería 0.4.0, sin fusionar). Solo lectura.
- Librería: `solercia_flows/boki-front/projects/solercia/ui` (`CHANGELOG.md`, `docs/THEMING.md`, `docs/THEME-STUDIO.md` §3.2).

## Alcance autorizado

Autorizado por el usuario el 2026-10-02: «Arranca con todo para que quedemos alineados a Pandora_front».

Dentro: librería a `^0.6.1`; configuración global como PANDORA; shell (layout, sidebar multinivel,
menú móvil inferior, header, migas de pan, menú de usuario, panel de ayuda, logo, botón de tema);
centro de alertas, diálogo de confirmación y estados de error, vacío y carga; Theme Studio con
historial y restauración de versiones sobre un adaptador por organización; demostración de paridad.

Fuera: puente legacy, telemetría y aviso de privacidad, selector y entrada de módulos, footer
institucional, entidad por hostname, errores de soporte de la pasarela.

## Decisiones

- **Tailwind se queda en la versión 3.** La librería no exige Tailwind, los widgets del porte no usan
  utilidades y la rama de porte corre sobre la 3. Migrar a la 4 tocaría 33 archivos sin cambio visual.
- **Historial de versiones:** tabla nueva de solo inserción, migración `0028`, endpoints con cursor
  de 20, restauración con versión de origen y captura inicial. Contrato de la librería:
  `ThemeVersion {id, userName, userId, appliedAt, initialCapture, sourceVersionId}` y
  `ThemeVersionPage {versions, next}`.
- **Carga de logo fuera de alcance por ahora:** el contrato la marca como opcional y el
  almacenamiento de archivos sigue sin decidir. El logo entra por URL.
- **Se conservan** `OrgThemeSource` y `TenantThemeService` (organizaciones con UUID), el selector de
  organización y la campana de notificaciones como acciones del header.
- **`sol-alert-center` no está en la librería:** se copia de boki-front. El diálogo de confirmación y
  la directiva de revelado sí vienen en la librería 0.6.1 y se usan desde ella.

## Restricciones

- Rama `feat/ui-shell-pandora`, creada sobre `feat/conexion-solercia-connect`. Commits por unidad de
  trabajo, sin atribución a herramientas. Sin push sin autorización.
- Ninguna operación destructiva sobre datos. La migración `0028` solo se prueba en una base
  desechable; a la base real va únicamente con autorización expresa.
- Un solo escritor activo a la vez.
- Textos de interfaz en español colombiano con tuteo. Las llaves existentes del catálogo no se renombran.
- Antes de cerrar cada pantalla se aplica la lista de verificación de UX.
- Persistencia: se lee `agents/rules/solercia-persistence.md` antes de tocar repositorios o migraciones.

## Modo de pruebas

- Backend: TDD estricto (fuente: `openspec/config.yaml`, `rules.apply.tdd`). Runner:
  `cd backend && pytest tests/<archivo> -v`, solo las pruebas del cambio. Nunca la suite completa
  contra una base real.
- Frontend: no hay runner de pruebas. Verificación con `npm run build`, `npm run lint` y navegador.

## Entrega

Estrategia `ask-on-risk`. Pronóstico: unas 6.000 líneas autoradas, muy por encima de 400. Cada tarea
U01–U07 es una frontera de rebanada. La estrategia de cadena (`stacked-to-main` o
`feature-branch-chain`) queda pendiente de la decisión del usuario cuando autorice push y PR.
La revisión nativa está apagada (`gentle-ai review mode status`: off, decidido por la configuración global).

## Tareas

- [x] U00 Commits del trabajo pendiente en la rama base: 13 commits, `799396d`..`046f589`. Sin pruebas ejecutadas.
- [x] U01 Subir `@solercia/ui` a `^0.6.1` y ajustar los cambios de contrato. Verifica: build y lint. Commit `3fe0afa`.
- [x] U02 Configuración global como PANDORA: locale es-CO, recarga ante chunk faltante, tema por
      defecto al arrancar, reglas `sol-*` de estilos, fuentes y favicon por tema, tema por defecto
      completo, retiro de `assets/config/theme-config.json`. Verifica: build y lint. Commit `0d8dd69`.
      Navegador pendiente (se verifica junto con U03).
- [x] U03 Shell: página shell y widgets del porte, menú adaptado a `GET /auth/me/menus`.
      Verifica: build y lint. Commits `04d71f6`, `6d9a265`, `f61f423`, `af58565`.
      Navegador en 1440×900 y 390×844, claro y oscuro: pendiente (U07a).
- [x] U04 Retroalimentación: centro de alertas, confirmación de la librería, estado de error,
      páginas de error e interceptor de errores. Verifica: build y lint. Commits `545adc7`,
      `0485645`, `81db97d`, `3c2c062`. Navegador pendiente (se verifica junto con U03).
- [ ] U05 Backend del historial de versiones de tema. Verifica: pruebas del cambio en rojo y luego en verde.
- [ ] U06 Theme Studio: adaptador de `THEME_STUDIO_STORE`, página que reemplaza «Apariencia» y llaves
      `sol.themeStudio.*`. Verifica: build, lint y navegador.
- [ ] U07a Verificación en navegador de U02–U06 sobre un entorno desechable (PostgreSQL temporal,
      backend y frontend en puertos propios), sin tocar la base real. Corrige lo que aparezca.
- [ ] U07 Paridad con PANDORA: capturas comparadas y documento de diferencias con su causa.

## Criterios de aceptación

- El build y el lint del frontend pasan en cada tarea.
- Las capturas del shell, sidebar abierto y colapsado, menú de usuario, una tabla, un diálogo de
  confirmación, estado de error y Theme Studio (inicial, historial, restauración) coinciden con las
  de PANDORA con el mismo tema, o cada diferencia queda documentada con su causa.
- El historial de versiones es de solo inserción y está aislado por organización.

## Progreso y evidencia

- 2026-10-02 U00: 13 commits locales verificados (`git log 1112731..HEAD`), sin atribución a
  herramientas, árbol limpio salvo `.pi/`.
- 2026-10-02 U01 (`3fe0afa`): librería resuelta en 0.6.1 desde el registro npm. Build exit 0 con la
  misma advertencia de presupuesto inicial (1.06 MB → 1.08 MB); lint exit 0 sin problemas, antes y
  después. Sin cambios de código: ninguna colisión entre los 35 selectores propios y los 59 de la
  librería. Riesgo evaluado: baja; sin revisión nativa (apagada).
  Pendiente de verificar en navegador: `sol-data-table` ahora colapsa a tarjetas por ancho del
  contenedor (5 usos en `pages/admin/*`). Diferido a U02: `meta.logo` falta en el tema por defecto.

- 2026-10-02 U02 (`0d8dd69`, 14 archivos): build exit 0 con la advertencia de presupuesto inicial
  (1.11 MB; el aumento son las reglas `@font-face` que ahora se incrustan en `styles.css`); lint
  exit 0 sin problemas. Sin verificación en navegador: los servicios locales estaban apagados.
  Logo y favicon propios creados en `src/assets/logos/` a partir de la marca del header.
  Efectos conocidos: el texto base pasa de 16 px a 14 px como en PANDORA; la librería no aplica
  `meta.favicon` ni `meta.defaultMode` del tema por defecto (solo de temas de organización), así
  que el favicon sale del `<link rel="icon">` de `index.html`. `component.table.variant` quedó sin
  fijar, igual que en el tema por defecto de PANDORA. Riesgo evaluado: baja.
- Cambio de orden: U04 va antes que U03 porque el panel de ayuda del shell depende del estado de
  error y este del servicio de alertas.

- 2026-10-02 U04 (`545adc7`, `0485645`, `81db97d`, `3c2c062`): build exit 0 con la advertencia de
  presupuesto inicial (1.12 MB); lint exit 0 sin problemas. Sin verificación en navegador.
  24 llamadas de toasts migradas a `AlertService` y `shared/lib/toast/` eliminado. Seis
  confirmaciones puras migradas a `SolConfirmDialogComponent` (dependencias, menús, organizaciones,
  roles, usuarios, conexiones). Rutas `no-autorizado`, `prohibido`, `error-servidor` y comodín a la
  página no encontrada (antes redirigía a `projects`). Riesgo evaluado: media, diferida a la rebanada.
  **Abierto para decisión del usuario:** el interceptor de errores quedó inactivo para las 110
  llamadas actuales (todas llevan el token de exclusión porque sus pantallas ya muestran el error
  en línea); solo actúa sobre llamadas nuevas. Activarlo por pantalla exige quitar su token y su
  error en línea.
  Hallazgos de UX sin aplicar: las confirmaciones migradas pierden el estado «Eliminando…»; las
  alertas duran 5 s y no pausan con el cursor; 401 solo ofrece volver al inicio; el backend no envía
  `X-Request-Id`, así que el código de seguimiento no aparece.

- 2026-10-02 U03 (`04d71f6`, `6d9a265`, `f61f423`, `af58565`): build exit 0 con 2 advertencias
  (presupuesto inicial 1.09 MB; nueva: estilos de `sidebar.component.ts` 5.57 kB contra el
  presupuesto de 4 kB, PANDORA usa 6 kB); lint exit 0 sin problemas. Sin verificación en navegador.
  El shell es la ruta padre de las vistas autenticadas; fuera quedan `login`, `auth/callback`, las
  páginas de error y el comodín. Lo propio de Command vive en `pages/shell/ui/shell-page.component.ts`:
  selector de organización, campana con sondeo de 60 s, importación de tareas, cierre de sesión y
  enlaces de respaldo. Riesgo evaluado: media, diferida a la rebanada.
  Diferencias frente a PANDORA: sidebar expandido por defecto y sin auto-cierre; menú de usuario sin
  «Perfil» ni «Apariencia»; las páginas pierden el contenedor centrado de 80rem; el logo ya no
  enlaza a `/projects`; el login queda sin header.
  **Abierto para decisión del usuario:** canal de «Ayuda y soporte» (`SUPPORT_URL` es `null` y el
  panel abre vacío); auto-cierre del sidebar.
  Hallazgos de UX sin aplicar: en móvil el error del menú no se ve ni se reintenta; en modo riel no
  se muestran vacío ni error; la rama activa no se expande al recargar.
  Llaves huérfanas sin borrar: `nav.brandAria`, `nav.logout`, `nav.mobileNavAria`,
  `nav.primaryNavAria`, `nav.sidebarCollapse`, `nav.sidebarExpand`, `nav.sidebarToggle`,
  `nav.themeToDark`, `nav.themeToLight`.

## Siguiente paso

U05.

## Espejo

Engram, tema `odd/ui-shell-pandora/tasks`: observación #5499 (guardada con `engram save`; el
guardado por MCP falla por sesiones simultáneas). Resincronizar al cierre de cada tarea.
