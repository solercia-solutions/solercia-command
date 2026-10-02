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
- [ ] U01 Subir `@solercia/ui` a `^0.6.1` y ajustar los cambios de contrato. Verifica: build y lint.
- [ ] U02 Configuración global como PANDORA: locale es-CO, recarga ante chunk faltante, tema por
      defecto al arrancar, reglas `sol-*` de estilos, fuentes y favicon por tema, tema por defecto
      completo, retiro de `assets/config/theme-config.json`. Verifica: build, lint y navegador.
- [ ] U03 Shell: página shell y widgets del porte, menú adaptado a `GET /auth/me/menus`.
      Verifica: build, lint y navegador en 1440×900 y 390×844, claro y oscuro.
- [ ] U04 Retroalimentación: centro de alertas, confirmación de la librería, estado de error,
      páginas de error e interceptor de errores. Verifica: build, lint y navegador.
- [ ] U05 Backend del historial de versiones de tema. Verifica: pruebas del cambio en rojo y luego en verde.
- [ ] U06 Theme Studio: adaptador de `THEME_STUDIO_STORE`, página que reemplaza «Apariencia» y llaves
      `sol.themeStudio.*`. Verifica: build, lint y navegador.
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

## Siguiente paso

U01.

## Espejo

Engram, tema `odd/ui-shell-pandora/tasks`: pendiente (ver progreso).
