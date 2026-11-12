# Proposal: 19 · Conector MCP (adaptador genérico de recursos externos vía Model Context Protocol)

## Intent

Las entidades usan servicios que la plataforma no integra nativamente y que pueden cambiar con el tiempo. Escribir un adaptador dedicado por cada servicio (estilo 15–18) no escala para la cola larga de herramientas internas. **MCP (Model Context Protocol)** es un protocolo abierto y estándar para exponer recursos y herramientas de cualquier servicio a un cliente. Este cambio habilita registrar **servidores MCP remotos como conectores del modelo del 14** y consumir sus recursos/herramientas **EN MODO LECTURA** bajo un puerto genérico de "recursos externos": sumar un servicio nuevo es configuración (registrar un servidor), no código. Entregable **backend-only**; frontend congelado; **SIN ejecución de herramientas de escritura** en esta ola.

## Scope

### In Scope
- **Adaptador `mcp`** que implementa el `IntegrationAdapter` del 14, cliente de transporte remoto **Streamable HTTP** (transporte MCP vigente; el antiguo HTTP+SSE de dos endpoints está deprecado) usando el **SDK oficial `mcp` de Python** (async). Se auto-registra (precedente `adapters/fake.py`), cero ediciones al orquestador del núcleo.
- **Puerto nuevo de solo lectura `ExternalResourceReaderPort`** (capacidad `external_resources`) en el núcleo del 14: `list_resources`, `read_resource(uri)`, `list_tools` (descubrimiento) y `call_tool` LIMITADO a herramientas marcadas `readOnlyHint`.
- **Descubrimiento y lectura MCP**: `initialize` (negociación de capacidades), `resources/list`, `resources/read`, `resources/templates/list`, `tools/list`; `tools/call` solo para herramientas de solo lectura, con allowlist default-deny.
- **Registro del servidor MCP como conector**: URL base + transporte + modo de auth (token estático tipo bearer o sin-auth para el MVP), credenciales cifradas reutilizando `connection_credentials` (Fernet) del 14.
- **Sección REST de lectura** bajo el conector: listar recursos/herramientas y leer recursos.
- **Servidor MCP fake local** para pruebas de contrato (in-process, sin red real).

### Out of Scope
- Ejecución de herramientas de escritura/destructivas o cualquier operación que mute el servicio externo.
- Handshake **OAuth 2.1 completo de MCP** (descubrimiento RFC 9728 Protected Resource Metadata, metadata RFC 8414, DCR RFC 7591, PKCE) → futuro; el MVP usa token estático / sin-auth.
- Transporte `stdio`/subprocess local (evita sandboxing de procesos): solo remoto HTTP.
- Almacenar/clasificar lo leído como ítems (cambio 22); primitiva `prompts/*`; suscripciones/streaming persistente; frontend.

## Capabilities

### New Capabilities
- `mcp-connector`: adaptador MCP (Streamable HTTP + SDK `mcp`), descubrimiento y lectura de recursos/herramientas, enforcement de solo-lectura, endpoints de lectura y servidor MCP fake de pruebas.

### Modified Capabilities
- `integration-ports`: nuevo puerto read-only `ExternalResourceReaderPort` + DTOs (`ExternalResource`, `ExternalTool`, `ExternalResourceContent`) y capacidad `external_resources` en el catálogo del núcleo; el protocolo de adaptador admite adquisición de credencial directa (token/none), no solo authorize/callback.
- `connectors`: registrar un conector MCP con config de servidor (URL/transporte/modo auth) y ruta de credencial directa, sin el flujo de navegador authorize/callback.

## Approach

- Adaptador `app/integrations/adapters/mcp.py`: por operación abre `ClientSession` sobre `streamablehttp_client(base_url, headers=Authorization?)`, `initialize`, ejecuta la lectura y cierra. Traduce recursos/herramientas MCP → DTOs agnósticos del puerto.
- **Enforcement solo-lectura**: default-deny en `call_tool`; permite únicamente herramientas con `readOnlyHint: true` presentes en un allowlist por conector. Todo contenido devuelto se trata como **dato inerte** (nunca se auto-ejecuta ni interpreta).
- **Config del servidor** (URL/transporte/auth) en el JSONB del conector si el modelo lo admite; si no, columna aditiva mínima (migración encadenada ≥ `0014`). Token estático → `connection_credentials` cifrado.
- **Anti-SSRF**: allowlist de hosts MCP + bloqueo de rangos privados por defecto + https-only en producción. Timeouts y topes de tamaño/número por llamada.
- Multi-tenant y RBAC reutilizados del 14 (scoped por `organization_id`; registrar = admin/manager; leer = miembro).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/integrations/ports.py` | Modified | `Capability.external_resources` + `ExternalResourceReaderPort` (read-only) |
| `backend/app/integrations/dtos.py` | Modified | DTOs `ExternalResource`/`ExternalTool`/`ExternalResourceContent` |
| `backend/app/integrations/adapters/mcp.py` | New | Adaptador MCP (Streamable HTTP, SDK `mcp`), auto-registro |
| `backend/app/integrations/adapters/__init__.py`, `app/db_init.py` | Modified | Import del adaptador para registro import-time |
| `backend/app/modules/connectors/` | Modified | Registro MCP (URL/transporte/auth) + endpoints de lectura de recursos/herramientas |
| `backend/app/config.py` | Modified | `MCP_HOST_ALLOWLIST`, timeouts, topes de tamaño |
| `backend/requirements.txt` | Modified | SDK `mcp` (dependencia nueva) |
| `backend/alembic/versions/00xx_*` | New (condicional) | Columna de config del conector, solo si no cabe en el JSONB existente |
| `docs/diagrams/c4-architecture.md` (+ `er-model.md` si hay columna) | Modified | Adaptador/integración MCP; ER solo si hay migración |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Servidor MCP arbitrario/no confiable: contenido de recursos y descripciones de tools puede portar inyección de prompts o payloads | High | Solo-lectura; contenido tratado como dato inerte (nunca auto-ejecuta/evalúa); registro solo admin/manager; topes de tamaño |
| SSRF / acceso a red interna vía la URL del servidor | High | Allowlist de hosts + bloqueo de rangos privados por defecto; https-only en producción |
| Ejecución accidental de herramienta de escritura | Med | Default-deny en `call_tool`; solo `readOnlyHint: true` + allowlist por conector (el hint es no confiable, se combina con allowlist) |
| Sandboxing / ejecución local | Low | Solo transporte remoto HTTP; sin `stdio`/subprocess; el adaptador es cliente de red, no ejecuta código |
| Agotamiento por respuestas grandes/lentas | Med | Timeout por llamada + topes de tamaño/número; conexión/pool acotados |
| Token en reposo / fuga cross-tenant | Med | Fernet + `connection_credentials` y scoping `organization_id` del 14; tokens jamás en respuestas ni logs |
| Apply serializado por la cadena Alembic (si hay columna) | Med | Encadena sobre la cabeza vigente ≥ `0014`; no aplicar en paralelo con otra migración |

## Rollback Plan

Área aislada. Rollback = revertir el merge; quitar el registro del adaptador `mcp` deja el núcleo del 14 con solo el fake, inerte. Si hubo columna aditiva, su `downgrade()` la elimina. Sin filas MCP vivas previas: cero impacto en flujos existentes.

## Dependencies

- **`14-integration-ports` ARCHIVADO** (regla OLA 2: el apply de 19 no inicia hasta que su dependencia esté archivada; la planeación puede correr en paralelo cuando 14 tenga al menos `design`).
- SDK oficial **`mcp` de Python** como dependencia nueva de backend.
- Cabeza Alembic vigente al momento del apply (≥ `0014`) solo si se agrega columna de config.

## Success Criteria

- [ ] Adaptador `mcp` registrado sin editar el orquestador del núcleo; puerto `external_resources` con contrato estrictamente de lectura.
- [ ] Contra el servidor MCP fake: `list_resources`/`read_resource`/`list_tools` funcionan; `call_tool` de una herramienta `readOnlyHint` OK; herramienta de escritura → RECHAZADA.
- [ ] Registro de un servidor MCP como conector (URL + auth) con token cifrado, sin flujo de navegador OAuth.
- [ ] URL fuera del allowlist o hacia rango privado → rechazada (anti-SSRF); timeout aplicado por llamada.
- [ ] Tokens nunca en respuestas ni en logs; aislamiento multi-tenant verificado.
- [ ] Suite verde con TDD estricto; `docs/diagrams/c4-architecture.md` actualizado (y `er-model.md` si hubo migración).

## Ronda de preguntas de propuesta

> No pude preguntar en vivo (ejecutor delegado). Supuestos a ratificar antes de spec/design:

1. **Auth del MVP**: ¿soportamos solo **token estático (bearer/API key) + sin-auth** para el MVP, difiriendo el handshake OAuth 2.1 completo de MCP (RFC 9728/8414, DCR RFC 7591, PKCE)? Asumido: sí.
2. **Ejecución de herramientas**: ¿el MVP permite invocar herramientas marcadas `readOnlyHint` (con allowlist default-deny), o se limita SOLO a recursos (list/read) y deja TODA invocación de tools fuera? Asumido: permitir tools de solo lectura con allowlist.
3. **Transporte**: ¿solo remoto **Streamable HTTP**, excluyendo `stdio`/subprocess por sandboxing? Asumido: sí.
4. **Config del conector MCP**: ¿reutilizamos la tabla `connectors` con config en JSONB (sin migración) o agregamos columna aditiva mínima encadenada al ≥ `0014`? Asumido: JSONB si cabe; si no, columna aditiva mínima.
5. **Anti-SSRF**: ¿exigimos allowlist de hosts MCP + bloqueo de rangos privados por defecto + https-only en producción? Asumido: sí.
