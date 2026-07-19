# Proposal: 15 · Adaptador Microsoft 365 (Graph, solo lectura)

## Intent

El núcleo hexagonal del 14 queda inerte sin adaptadores reales. Este cambio implementa el PRIMER adaptador real: Microsoft Graph **solo lectura**, para que una organización con Microsoft 365 alimente clasificación, alertas y vista ejecutiva con su correo Outlook, calendario, tareas de Planner y —si el tenant lo expone— transcripciones de reuniones de Teams. Autorización **delegada** del usuario mediante el flujo OAuth del 14 (Entra ID / Azure AD como IdP). Backend-only; **cero cambios al núcleo del 14**; sin escritura.

## Scope

### In Scope
- Adaptador `microsoft365` que implementa `IntegrationAdapter` (14) y se auto-registra en import-time (precedente `adapters/fake.py`); cero ediciones al núcleo.
- Puertos implementados: correo (`MailReaderPort`), calendario (`CalendarReaderPort`), tareas externas (`ExternalTaskReaderPort`), notas de reunión (`MeetingNotesReaderPort`).
- Handshake OAuth de Entra ID (authorization code, confidential client): `authorize_url`, `exchange_code`, `refresh` sobre `login.microsoftonline.com/{tenant}/oauth2/v2.0/*`. *(Errata: PKCE se difirió como follow-up del 14 por decisión ratificada en design.md — las firmas del núcleo no enhebran `code_verifier`; ver design.md, sección "Flujo confidential-client".)*
- Mapeo Graph → DTOs agnósticos del 14; paginación `@odata.nextLink`; backoff ante `429 Retry-After`; degradación por capacidad no disponible.

### Out of Scope
- Cualquier cambio a `app/integrations/` o `app/modules/connectors/` del 14 (se consumen tal cual, sin migraciones nuevas).
- Escritura hacia Graph (enviar correo, crear evento/tarea): puertos solo-lectura.
- `TicketReaderPort`: Graph no aplica → lo cubren GLPI/Jira (17–18).
- Almacenar/clasificar los insumos leídos (cambio 22); cualquier cambio en `frontend/`.

## Capabilities

### New Capabilities
- `adapter-microsoft365`: adaptador Graph solo-lectura sobre los puertos del 14 (correo/calendario/tareas/notas) + handshake OAuth de Entra ID.

### Modified Capabilities
- None. No se modifica ningún requisito de `integration-ports` ni `connectors`.

## Approach — Mapeo capacidad → endpoint Graph → scope delegado

| Capacidad | Puerto (14) | Endpoint Graph (GET) | Scope delegado | Admin consent |
|-----------|-------------|----------------------|----------------|---------------|
| Correo Outlook | `MailReaderPort` | `/me/messages`, `/me/mailFolders/{id}/messages`, `/me/messages/delta` | `Mail.Read` | No |
| Calendario | `CalendarReaderPort` | `/me/calendarView?startDateTime&endDateTime`, `/me/events` | `Calendars.Read` | No |
| Tareas Planner | `ExternalTaskReaderPort` | `/me/planner/tasks`, `/planner/plans/{id}/tasks` | `Tasks.Read` | No (exige pertenecer al grupo/plan) |
| Notas/transcripciones Teams | `MeetingNotesReaderPort` | `/me/onlineMeetings/{id}/transcripts`, `.../transcripts/{tid}/content` | `OnlineMeetingTranscript.Read.All` (+ `OnlineMeetings.Read` para resolver la reunión) | **Sí** |

Base OIDC/refresh: `openid profile email offline_access User.Read` (identifica el `external_account_id` vía `userPrincipalName`). Endpoints authorize/token: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/{authorize,token}` (`tenant=organizations` para cualquier tenant M365).

**Permiso de aplicación para transcripciones (nota obligatoria)**: `OnlineMeetingTranscript.Read.All` es un scope `.All` que exige **consentimiento de administrador**; el acceso delegado solo devuelve transcripciones de reuniones organizadas por el usuario firmado, y la vía por permiso de aplicación exige además una *application access policy* de Teams. **Fallback**: si el tenant no otorgó el consentimiento, el adaptador declara la capacidad `meeting_notes` **no disponible** y responde un error claro (`capability_unavailable`), sin afectar correo/calendario/tareas.

## Testing Strategy
- Fixtures JSON de respuestas Graph **reales** (mail/calendar/planner/transcripts) bajo `tests/fixtures/graph/`; cliente HTTP inyectable → **cero red en CI**.
- Contrato: cada puerto del 14 devuelve sus DTOs desde el fixture; paginación `@odata.nextLink` recorrida completa; `429` con `Retry-After` respeta backoff; `meeting_notes` sin consent degrada.
- Registro: el adaptador aparece por `provider="microsoft365"` sin editar el núcleo (misma prueba del 14).

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Transcripciones exigen admin consent (`.All`) | High | Degradar `meeting_notes` a "no disponible" con error claro; documentar el consentimiento requerido |
| Throttling `429` (Outlook/Planner agresivo) | Med | Honrar `Retry-After` + backoff exponencial; `$select`/`$top` para acotar carga |
| Tenant sin Planner/Grupos M365 | Med | `/me/planner/tasks` vacío → capacidad activa pero sin datos, nunca error |
| Cambios de forma en Graph | Low | DTOs agnósticos aíslan el negocio; fixtures versionados |
| Fuga de tokens en logs del adaptador | Med | Reusar cifrado/no-log del 14; jamás loggear access/refresh ni respuestas crudas con tokens |

## Rollback Plan

Adaptador aislado y aditivo. Rollback = revertir el merge; al desregistrarse, `provider="microsoft365"` desaparece del registro y el núcleo del 14 vuelve a quedar solo con el fake. **Sin migraciones nuevas** (usa las tablas del 14).

## Dependencies

- `14-integration-ports` archivado (puertos, registro, protocolo de adaptador, modelo Connector/ConnectedAccount/ConnectionCredentials, flujo OAuth genérico, cifrado Fernet).
- Cliente HTTP async (`httpx`, ya en el stack) para Graph.
- Habilita el cambio 22 (clasificador de insumos) usando este adaptador como referencia; 16 (Google) reutiliza los mismos puertos.

## Success Criteria
- [ ] El adaptador `microsoft365` se registra sin editar el núcleo del 14 (verificado con la prueba de registro).
- [ ] Correo/calendario/tareas devuelven los DTOs del 14 desde fixtures Graph reales, **sin red en CI**.
- [ ] Handshake OAuth de Entra ID (authorize → callback → refresh) probado a través del flujo del 14.
- [ ] `meeting_notes` degrada con error claro (`capability_unavailable`) cuando falta el admin consent de transcripciones.
- [ ] `429` con `Retry-After` respeta backoff; paginación completa vía `@odata.nextLink`.
- [ ] Cero escritura hacia Graph; tokens nunca en respuestas ni en logs.

## Ronda de preguntas de propuesta

> No pude preguntar en vivo (ejecutor delegado). Supuestos a ratificar antes de spec/design:

1. **Tenant OAuth**: ¿`organizations` (cualquier tenant M365, recomendado para multi-organización) o un tenant fijo por conector? Asumo `organizations`, con `tenant` configurable por conector.
2. **Transcripciones**: ¿aceptas el fallback "capacidad no disponible" cuando falte admin consent (asumido), o el 15 debe intentar además el modo application-permission + *application access policy*?
3. **Alcance de tareas**: ¿solo Planner (asumido) o también Microsoft To Do (`/me/todo/lists`, mismo scope `Tasks.Read`) bajo el mismo puerto de tareas externas?
4. **Ventana de lectura**: ¿un `since`/`limit` por defecto acotado (ej. correo/eventos de los últimos 30–90 días) para contener volumen y throttling? Asumo los parámetros del puerto (`since`/`limit`) con default acotado.
