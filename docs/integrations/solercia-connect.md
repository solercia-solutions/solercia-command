# Integración con Solercia Connect

Command lee correo, calendario y notas de reunión a través de un runtime local
de [Solercia Connect](https://github.com/) en lugar de hablar con Microsoft o
Google directamente.

## Por qué es un servicio y no una dependencia

El registro de decisiones de plataforma
(`docs/decisions/2026-08-23-solercia-platform-decisions.md`) lo fija en su §2.2:

> «Se prohíben la base de datos compartida, las entidades ORM compartidas, las
> claves foráneas entre bases, las importaciones directas del repositorio
> hermano y las dependencias obligatorias de arranque.»

Por eso este adaptador es un cliente HTTP del contrato loopback de Connect. La
consecuencia práctica, que es la que importa a diario: **si Connect no está
corriendo, Command arranca igual** y solo degrada las capacidades que Connect
respalda (§2.3).

Hay una segunda razón, más concreta. Connect sostiene la sesión viva de una
persona —su perfil de navegador o sus tokens OAuth—. Manteniéndolo fuera del
proceso de Command, **ninguna credencial de un buzón ajeno entra jamás a la
base de datos de Command**. Lo único que Command guarda es la llave del runtime
local.

## Qué lee

| Capacidad de Command | Capacidad de Connect | Notas |
|---|---|---|
| `mail` | `mail.sent.list` | El cuerpo llega como texto; el marcado se limpia una sola vez, en el adaptador |
| `calendar` | `calendar.events.list` | Connect no observa ubicación en esta superficie: el DTO la deja vacía |
| `meeting_notes` | `meeting.transcript.get` | WebVTT con hablantes; `participants` sale de las voces del acta |

Connect decide su propia ruta —API oficial primero, navegador supervisado solo
como fallback explícito (§3.1-3.2)—. Este adaptador no elige rutas: solo
declara si el fallback está permitido para ese conector.

## Configuración

Dos variables en el `.env` del backend:

```bash
# Direcciones permitidas para el runtime de Connect. Es la guarda anti-SSRF:
# apuntar a un host equivocado sería leer el buzón de otra persona.
SOLERCIA_CONNECT_BASE_URL_ALLOWLIST=["http://127.0.0.1:8765","http://host.docker.internal:8765"]
SOLERCIA_CONNECT_TIMEOUT_SECONDS=60
```

`host.docker.internal` cubre el caso normal en desarrollo: Command en
contenedor, Connect en la máquina del usuario, que es donde vive la sesión.

La llave del runtime y la cuenta a leer **no van en el `.env` de Command**: se
registran por conector, y se guardan cifradas con el mismo mecanismo que el
resto de credenciales de integración.

## Registrar un conector

El conector necesita cuatro datos:

| Campo | Qué es | Ejemplo |
|---|---|---|
| `base_url` | Dirección del runtime, dentro de la allowlist | `http://127.0.0.1:8765` |
| `api_key` | El `SOLERCIA_CONNECT_API_KEY` de ese runtime | — |
| `account` | La cuenta cuya sesión sostiene el runtime | `persona@entidad.example.gov.co` |
| `target` | Superficie de Connect a leer | `outlook`, `teams`, `onedrive`, `gmail`, `google_calendar` |

Opcional: `allow_browser_fallback` (por defecto `false`). Actívalo solo cuando
esa cuenta no tenga todavía los permisos oficiales del tenant.

## Frontera de identidad

Antes de devolver un solo registro, el adaptador compara la cuenta que Connect
reporta haber leído con la que el conector pidió, sin distinguir mayúsculas. Si
no coinciden, o si Connect no reporta ninguna, la lectura entrega **cero
registros** y un error tipado. Es la §4 del registro de decisiones: una sola
identidad canónica observada, y procedencia que nunca sustituye una identidad
verificada por una solicitada.

## Cómo falla

Cada fallo es distinguible a propósito, porque «Connect no está corriendo» y
«Connect dice que la cuenta está mal» exigen respuestas distintas:

| Error | Significa | Qué hacer |
|---|---|---|
| `SolerciaConnectUnavailableError` | El runtime no respondió | Iniciarlo; Command sigue funcionando sin él |
| `SolerciaConnectAuthError` | Llave rechazada, o la sesión del proveedor caducó | Revisar la llave, o reconectar la cuenta en Connect |
| `SolerciaConnectAccountMismatchError` | Connect respondió por otra cuenta | Revisar qué cuenta sostiene ese runtime |
| `SolerciaConnectConfigError` | Configuración inutilizable | Revisar `base_url` contra la allowlist |
| `SolerciaConnectProtocolError` | Connect respondió en una forma desconocida | Revisar que las versiones de ambos productos correspondan |

## Levantar el runtime

En la máquina que tiene la sesión, no en el contenedor:

```bash
export SOLERCIA_CONNECT_API_KEY="<una llave local de alta entropía>"
export SOLERCIA_CONNECT_BROWSER_FALLBACK=true    # solo si hace falta el fallback

# El servicio es un ejecutable propio, distinto de la CLI:
solercia-connect-service                          # escucha en 127.0.0.1:8765
```

Desde el repositorio de Connect, el atajo equivalente es `make service`.

Verificar que responde:

```bash
curl http://127.0.0.1:8765/v1/health
```

## Compartir el runtime con otra persona

Alguien que solo necesita leer su propio correo desde su propia máquina —con
Claude Code o con cualquier otro cliente— **no necesita Command ni esta
integración**. Necesita Connect, y nada más.

Los pasos están en `docs/integrations/compartir-solercia-connect.md`.
