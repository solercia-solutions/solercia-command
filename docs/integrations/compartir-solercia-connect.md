# Compartir Solercia Connect con otra persona

Para alguien que solo necesita leer su propio correo desde su propia máquina,
con Claude Code o con otro cliente. **No necesita Command ni Docker.**

Lo importante de entender antes de empezar: Connect no es un servicio al que la
persona se conecte. Es un programa que corre **en su equipo**, con **su** sesión
y **sus** credenciales. Nadie más ve esos datos, y no hay ninguna cuenta central
que administrar.

## 1. Instalar

Requiere Python 3.12 o superior.

```bash
# Con uv (recomendado: queda aislado y en el PATH)
uv tool install solercia-connect

# Alternativa con pipx
pipx install solercia-connect
```

Si todavía no hay un paquete publicado, se instala desde el wheel que se
entrega:

```bash
uv tool install ./solercia_connect-<version>-py3-none-any.whl
```

Verificar:

```bash
solercia-connect --help
```

## 2. Configurar

Crear un archivo de entorno propio, por ejemplo `~/.solercia/connect.env`:

```bash
# Aplicación pública/nativa de Microsoft para OAuth por código de dispositivo.
# No lleva secreto de cliente.
SOLERCIA_CONNECT_MICROSOFT_CLIENT_ID=<client id de la aplicación registrada>
SOLERCIA_CONNECT_MICROSOFT_TENANT=organizations
```

Cargarlo al invocar:

```bash
export SOLERCIA_CONNECT_ENV_FILE=~/.solercia/connect.env
```

> El archivo contiene configuración, no contraseñas. Connect nunca pide ni
> almacena la contraseña: eso ocurre en el navegador de la persona, contra
> Microsoft.

## 3. Conectar la cuenta

```bash
solercia-connect connect outlook persona@entidad.gov.co
```

Se abre el navegador, la persona inicia sesión y autoriza. El navegador se
cierra y Connect guarda el token en el llavero del sistema operativo. De ahí en
adelante no vuelve a hacer falta el navegador.

Comprobar el estado:

```bash
solercia-connect status outlook persona@entidad.gov.co
```

## 4. Leer correo

```bash
solercia-connect run \
  --provider microsoft.graph \
  --capability mail.sent.list \
  --start '2026-08-01T00:00:00-05:00' \
  --end   '2026-09-01T00:00:00-05:00' \
  --account persona@entidad.gov.co
```

Devuelve JSON por la salida estándar. Para lotes grandes conviene escribir a
archivo en vez de imprimir:

```bash
solercia-connect run ... --output correos.json
```

## 5. Usarlo con Claude Code

Es una herramienta de línea de comandos que devuelve JSON, así que Claude Code
la invoca como cualquier otro comando. Dos recomendaciones que ahorran
problemas:

1. **Usar siempre `--output archivo.json`.** Un mes de correos son cientos de
   miles de caracteres; pasarlos por el contexto del modelo es caro y
   normalmente innecesario. Que el modelo procese el archivo.
2. **Fijar el rango de fechas explícitamente.** Connect usa rangos exactos con
   fin exclusivo y no los amplía por su cuenta.

Para dejarlo permanente, agregar al `CLAUDE.md` del proyecto de esa persona:

```markdown
## Lectura de correo

Para leer correo usa `solercia-connect run --capability mail.sent.list`
con `--start`, `--end`, `--account` y `--output`. Nunca amplíes el rango de
fechas que te den: si no hay resultados, son cero.
```

## Lo que NO hay que compartir

- **La llave del runtime local** (`SOLERCIA_CONNECT_API_KEY`). Cada persona
  genera la suya; solo hace falta si va a exponer el servicio HTTP.
- **El perfil del navegador ni el llavero.** Contienen la sesión. Copiarlos a
  otra máquina es entregar el acceso a la cuenta.
- **Los archivos `.env` con valores reales.** Se comparte la plantilla, nunca el
  archivo lleno.

## Si algo falla

| Síntoma | Causa habitual |
|---|---|
| `configuration_invalid` con `SOLERCIA_CONNECT_MICROSOFT_CLIENT_ID` | Falta el archivo de entorno o la variable |
| Pide iniciar sesión otra vez | El token caducó; repetir `connect` |
| `browser_account_mismatch` | La sesión del navegador es de otra cuenta |
| Cero registros | El rango de fechas está vacío. No ampliarlo: revisar las fechas |

Para diagnóstico estructurado:

```bash
solercia-connect doctor outlook
```
