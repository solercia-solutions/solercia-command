# Proposal: 14 · Puertos de integración (núcleo hexagonal + conectores)

## Intent

La plataforma debe leer insumos que hoy viven fuera (correo, calendario, tareas, transcripciones de reuniones, tickets) para alimentar clasificación, alertas y vista ejecutiva. Cablear cada proveedor dentro del negocio ata la lógica a Microsoft Graph, Google o GLPI y obliga a editar el núcleo por cada servicio nuevo. Este cambio define el **núcleo hexagonal solo-lectura**: puertos por capacidad + adaptadores y conectores por organización con OAuth y tokens cifrados. Los adaptadores reales (15–19) se conectan sin tocar el núcleo. Entregable **backend-only**; frontend congelado.

## Scope

### In Scope
- **Puertos read-only** (una interfaz por capacidad): lectura de correo, calendario, tareas externas, notas/transcripciones de reuniones y tickets/casos. Outlook y Gmail comparten el mismo puerto de correo cuando la semántica coincide (extensibilidad).
- **Registro de adaptadores** poblado en import-time (precedente `app/notify/registry.py`): adaptador nuevo = clase registrada, cero ediciones al núcleo. Núcleo lee comportamiento DESDE el adaptador, nunca `if provider == ...`.
- **Adaptador fake** en memoria (pruebas de contrato + flujo OAuth simulado, sin HTTP real).
- **Modelo de datos**: `connectors` (por organización), `connected_accounts` (por usuario), credenciales con tokens cifrados en reposo.
- **Flujo OAuth genérico**: botón "Conectar" → `authorize` (genera state/CSRF + URL del proveedor) → callback → intercambio de código por tokens → cifrado + registro de cuenta.
- **Sección de conectores** `/api/v1/connectors`: CRUD de conectores, `authorize`, callback, listar/desconectar cuentas, con permisos.

### Out of Scope
- Adaptadores reales Microsoft 365, Google, GLPI, Jira y MCP (cambios 15–19).
- Escritura hacia servicios externos (los puertos son solo-lectura).
- Almacenar/clasificar los insumos leídos como ítems (cambio 22).
- Cualquier cambio en `frontend/`.

## Capabilities

### New Capabilities
- `integration-ports`: puertos hexagonales read-only por capacidad + protocolo de adaptador + registro + adaptador fake.
- `connectors`: modelo de datos (conector/cuenta/credenciales cifradas), flujo OAuth genérico y sección REST `/api/v1/connectors` con permisos.

### Modified Capabilities
- None.

## Approach

Decisiones de arquitecto (a ratificar en design):
- **Núcleo en `app/integrations/`** (paquete propio, como `app/notify/`): `ports.py` (protocolos por capacidad), `registry.py` (registro de adaptadores), `oauth.py` (handshake genérico), `crypto.py` (cifrado simétrico Fernet con clave desde settings), `adapters/fake.py`.
- **Protocolo de adaptador**: declara `provider`, capacidades que soporta, intercambio de tokens OAuth y los puertos de lectura que implementa. El núcleo orquesta authorize/callback sin conocer al proveedor.
- **Tablas** (chain Alembic `0014` sobre `0013`):

| Tabla | Rol | Campos clave |
|-------|-----|--------------|
| `connectors` | Config por organización | `organization_id`, `provider`, `scopes`, `status`, auditoría, soft-delete |
| `connected_accounts` | Cuenta por usuario | `connector_id`, `user_id`, `organization_id`, `external_account_id`, `status` |
| `connection_credentials` | Tokens cifrados | `connected_account_id`, `access_token_enc`, `refresh_token_enc`, `expires_at` |

- **OAuth state** transitorio (CSRF) en Redis con TTL; el callback valida state antes de canjear.
- **Multi-tenant**: todo scoped por `organization_id`; tokens jamás en respuestas ni en logs.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/integrations/` | New | Puertos, registro, OAuth genérico, cifrado, adaptador fake |
| `backend/app/modules/connectors/` | New | router/service/repository/schemas/models — CRUD + OAuth |
| `backend/alembic/versions/0014_*` | New | Tablas de conectores/cuentas/credenciales, con downgrade |
| `backend/app/config.py` | Modified | Clave de cifrado de tokens (settings/env) |
| `docs/diagrams/er-model.md`, `docs/diagrams/c4-architecture.md` | Modified | **Nota obligatoria**: el apply DEBE actualizarlos (tablas nuevas + contenedor de integraciones) en el mismo commit de la migración |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Tokens comprometidos en reposo | High | Cifrado simétrico (Fernet) con clave por entorno; nunca en respuestas/logs; tabla de credenciales aislada |
| Fuga cruzada entre tenants (cuenta/token de otra organización) | Med | Filtro `organization_id` en repository; pruebas de aislamiento por tenant |
| CSRF / callback OAuth manipulado | Med | State firmado con TTL en Redis, validado antes del canje |
| Sobre-generalizar puertos sin adaptador real | Low | Adaptador fake valida la forma; interfaces mínimas por capacidad |
| Apply serializado por la cadena Alembic lineal | Med | `0014` encadena sobre `0013`; no aplicar en paralelo con otra migración |

## Rollback Plan

Área nueva y aislada. Rollback = revertir el merge; el `downgrade()` de `0014` elimina `connection_credentials`, `connected_accounts` y `connectors` (sin filas vivas previas). Sin adaptadores reales registrados, el núcleo queda inerte y no afecta ningún flujo existente.

## Dependencies

- Head Alembic `0013` (última revisión existente) → `0014` encadena aquí.
- Habilita los cambios 15–19 (adaptadores reales) y 22 (clasificador de insumos).
- `cryptography` (Fernet) como dependencia nueva de backend.

## Success Criteria

- [ ] Puertos definidos por capacidad; el adaptador fake pasa pruebas de contrato de cada puerto.
- [ ] Adaptador nuevo se registra sin editar el núcleo (verificado con el fake).
- [ ] Flujo OAuth genérico probado con el fake: `authorize` → callback → cuenta registrada + tokens cifrados.
- [ ] Tokens nunca en claro en BD ni en respuestas de la API.
- [ ] CRUD `/api/v1/connectors` con permisos (admin/manager configura; member conecta su cuenta).
- [ ] Migración `0014` aplicada; `docs/diagrams/er-model.md` y `docs/diagrams/c4-architecture.md` actualizados.

## Ronda de preguntas de propuesta

> No pude preguntar en vivo (ejecutor delegado). Supuestos que conviene ratificar antes de spec/design:

1. **Alcance de la cuenta conectada**: ¿una cuenta conectada por (usuario × conector) —asumido—, o se admiten varias cuentas del mismo proveedor por usuario (p. ej. dos buzones)?
2. **Ubicación del state OAuth**: ¿state transitorio en Redis con TTL (recomendado, ya hay Redis) o tabla `oauth_states`? Asumo Redis.
3. **Cifrado de tokens**: ¿Fernet (clave simétrica por entorno, simple para el MVP) —asumido— o envelope encryption/KMS desde ya? Asumo Fernet, con la frontera lista para migrar a KMS.
4. **Modelo de credenciales**: ¿tabla `connection_credentials` separada de `connected_accounts` (aísla secretos) —asumido— o columnas cifradas dentro de la cuenta?
5. **Puertos read-only estrictos**: ¿se confirma que este núcleo nunca escribe hacia el proveedor y que la escritura (crear tarea externa, responder correo) queda fuera de OLA 2?
