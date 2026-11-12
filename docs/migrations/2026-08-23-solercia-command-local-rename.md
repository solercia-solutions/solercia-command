# Migración local a Solercia Command

La identidad aprobada es **Solercia Command** y la carpeta local pasa de
`gestion_proyectos` a `solercia-command`. La migración conserva el repositorio Git y limita
los cambios a identidad de producto, documentación, instrucciones y rutas locales.

## Rutas

| Estado | Ruta |
| --- | --- |
| Anterior | `/Users/camilocalderont/Proyectos/SOLERCIA/gestion_proyectos` |
| Nueva | `/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command` |
| Worktrees anterior | `/Users/camilocalderont/Proyectos/SOLERCIA/gestion_proyectos-worktrees` |
| Worktrees nueva | `/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command-worktrees` |

## Checklist de migración

- [x] Confirmar la raíz exacta, la ausencia de la ruta destino y la identidad Git previa.
- [x] Inventariar cambios existentes y respaldar temporalmente el diff y los archivos no
  rastreados antes de escribir.
- [x] Auditar worktrees registrados, remotos, symlinks, procesos y referencias absolutas.
- [x] Consultar CodeGraph antes de la búsqueda estructural amplia.
- [x] Actualizar el nombre visible del producto en las superficies canónicas actuales.
- [x] Actualizar `AGENTS.md`, `CLAUDE.md`, OpenSpec y rutas de instrucciones activas.
- [x] Actualizar ADR 0009 con el nombre y la carpeta local como decisiones aprobadas.
- [x] Mover la carpeta local de forma atómica a `solercia-command`.
- [x] Renombrar el contenedor hermano vacío y no registrado a
  `solercia-command-worktrees`.
- [x] Regenerar `.atl/skill-registry.md` desde la nueva raíz.
- [x] Verificar que `solercia-persistence` global y la regla adaptadora local resuelvan.
- [x] Auditar referencias residuales a la ruta absoluta anterior y clasificar las históricas
  o generadas que no deben editarse.
- [x] Auditar configuraciones e instrucciones activas en los demás checkouts de SOLERCIA;
  corregir `solercia_security/.env` y verificar que Compose resuelva `/src` desde la nueva
  raíz existente.
- [x] Confirmar que HEAD, rama, índice, objetos Git, cambios previos y archivos no rastreados
  permanecen presentes después del movimiento.
- [x] Confirmar que la ruta anterior no existe, la nueva es utilizable, los symlinks
  resuelven y `git diff --check` no reporta errores.
- [x] Diferir identificadores de ambiente y despliegue; el proyecto Docker Compose se fija
  explícitamente como `gestion_proyectos` para conservar contenedores y volúmenes locales.
- [x] Diferir cualquier renombre de remoto, repositorio GitHub, dominio, marca jurídica,
  esquema, tabla, contrato de API, paquete, módulo o símbolo de dominio.

Estado verificado: **17/17 elementos completados**.

## Evidencia de preflight

| Verificación | Resultado |
| --- | --- |
| Raíz Git | `/Users/camilocalderont/Proyectos/SOLERCIA/gestion_proyectos` |
| HEAD | `c256634a580f8fa1308a1484783d1bbef420cb40` |
| Rama | `preview` (`refs/heads/preview`) |
| Remotos | Ninguno configurado. |
| Worktrees registrados | Solo la raíz principal; no hay worktrees vinculados. |
| Contenedor hermano | Existe, está vacío y no aparece en `git worktree list`. |
| Procesos | No hay servidor de aplicación activo; dos shells inactivos y Zed conservan descriptores de la carpeta, lo cual no bloquea el renombre atómico en el mismo sistema de archivos. |
| Symlinks del proyecto | No hay symlinks propios fuera de dependencias y entornos; los inspeccionados resuelven. |
| CodeGraph | Índice vigente: 241 archivos, 3.723 nodos y 5.125 aristas. El launcher con Node 26 falla de forma segura; la consulta funciona con el Node 22 instalado. |
| Estado previo | `CLAUDE.md` modificado; `AGENTS.md`, la regla local de persistencia y ADR 0009 no rastreados. |
| Objetos Git | 5.838 objetos sueltos, sin packs ni basura; `git fsck --full` correcto. |

## Límites intencionales

| Superficie | Tratamiento |
| --- | --- |
| Nombre visible | Cambiar a **Solercia Command** en documentación actual, API y UI. |
| Carpeta local | Cambiar a `solercia-command`. |
| Docker Compose | Conservar el identificador `gestion_proyectos`; no migrar volúmenes ni contenedores. |
| Base de datos | Conservar `solercia`, esquemas, tablas, columnas y migraciones. |
| API | Conservar rutas, payloads, contratos y versiones. |
| Paquetes y módulos | Conservar, entre otros, `solercia-pm-frontend`, `solercia-pm` y `gestion.sh`. |
| Git y GitHub | Conservar HEAD, ramas, reflogs y objetos; no crear ni renombrar remotos o repositorios. |
| Dominios y marca jurídica | Diferidos hasta una validación independiente. |
| Historial | No reescribir ADR históricos, archivos archivados, capturas, logs, cachés ni claves históricas de Engram. |

## Verificación posterior

| Verificación | Resultado |
| --- | --- |
| Ruta efectiva | `/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command`; la ruta anterior ya no existe. |
| Worktrees | La raíz principal aparece con la ruta nueva; el contenedor hermano se renombró, continúa vacío y no está registrado. |
| Inodos | La raíz conservó el inodo `32096828` y `.git` conservó `32276806`. |
| Git | HEAD `c256634a580f8fa1308a1484783d1bbef420cb40`, rama `preview`, `refs/heads/preview`, índice, refs, reflogs y configuración sin cambios. |
| Objetos | Manifiesto SHA-256 idéntico para los 5.838 objetos; `git fsck --full` correcto antes y después. |
| Cambios previos | El patch previo de `CLAUDE.md` sigue aplicable en reversa; la regla no rastreada de persistencia es idéntica byte a byte; `AGENTS.md` y ADR 0009 conservan su contenido previo más los cambios aprobados. |
| Symlinks | 77 inspeccionados; 0 rotos. No se crearon adaptadores nuevos. |
| Registro de skills | `.atl/skill-registry.md` regenerado con 91 skills y encabezado `solercia-command`. |
| Persistencia global | El registro resuelve `~/.agents/skills/solercia-persistence/SKILL.md`; también existen sus cuatro referencias requeridas por la regla local. |
| Virtualenv | 28 archivos de activación/entrypoint/configuración reparados mediante reemplazo exacto de ruta; Python 3.13.12, pip, pytest 9.1.1 y Alembic 1.14.0 ejecutan desde la nueva raíz. |
| Docker Compose | `docker compose config` conserva `name=gestion_proyectos`; no se tocaron contenedores, volúmenes ni datos. |
| Configuración externa activa | `solercia_security/.env` usa la nueva raíz en `SRC_REPO`; `docker compose config` resuelve el bind de `sast-orchestrator` hacia `/src` desde esa raíz existente y en modo solo lectura. |
| CodeGraph | Sincronizado en la nueva raíz: 243 archivos, 3.758 nodos y 5.242 aristas; estado vigente con Node 22. |
| Validación estructural | `git diff --check`, parseo JSON, parseo AST de Python y `bash -n gestion.sh` correctos. |
| Pruebas de aplicación | No se ejecutaron: el cambio se limita a ruta local, identidad visible, documentación y metadatos; no cambió lógica de dominio. |

## Auditoría externa de configuración activa

La búsqueda acotada cubrió la ruta absoluta anterior bajo `SOLERCIA`, incluidos archivos
ocultos e ignorados, con un límite de 20 MiB por archivo. Se excluyeron `.git` y
`node_modules`; las cachés y salidas generadas se contaron por separado para no confundirlas
con configuración o instrucciones operativas.

| Clasificación | Archivos | Resultado |
| --- | ---: | --- |
| Configuración o instrucción activa | 0 | `solercia_security/.env` fue corregido y Compose resolvió la nueva raíz existente. |
| Histórica o registro de migración | 2 | Conservada para mantener trazabilidad. |
| Caché o artefacto generado | 3.513 | No operativa; no se editó. |
| Documentación externa diferida | 3 | No participa en la configuración actual; queda a cargo de sus propietarios si se reactiva. |

## Referencias residuales registradas

No quedan coincidencias de la ruta absoluta anterior en configuraciones o instrucciones
activas. Los 3.518 archivos con coincidencias que permanecen están clasificados y no son
operativas para esta migración.

### Históricas o de migración

- `docs/migrations/2026-08-23-solercia-command-local-rename.md`: registra
  deliberadamente la ruta anterior, el preflight y el resultado de la migración.
- `docs/estrategia/TRANSCRIPCIONES.md`: transcripción histórica ignorada por Git.

### Cachés y artefactos generados

- 26 logs de `.playwright-mcp`, 18 entradas de caché de Ruff, 48 bases de caché de mypy y
  3.415 archivos de bytecode Python conservan rutas de la ejecución que los produjo.
- 6 artefactos de seguridad en `../.solercia-command-rename-state/` conservan el estado y los
  respaldos previos al movimiento.

### Documentación externa diferida

- `solercia_flows/openspec/PROMPT-OLA-6.md`.
- `solercia_flows-worktrees/e2-planeacion/openspec/PROMPT-OLA-6.md`.
- `solercia_security/docs/analisis-fusion-gestion-proyectos.md`.

Estas tres referencias pertenecen a otros repositorios o worktrees. No intervienen en la
configuración activa verificada y deben actualizarse por sus propietarios solo si vuelven a
usarse como instrucciones operativas.
