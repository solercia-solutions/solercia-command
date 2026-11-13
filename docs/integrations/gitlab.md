# Integración con GitLab

Solercia Command se conecta a GitLab con un token de acceso de **solo lectura**. Con él puedes vincular los repositorios de cada proyecto y ver, en el detalle de cada tarea, los merge requests y commits que la mencionan. Command nunca escribe en GitLab.

## 1. Crea el token

Puedes usar cualquiera de estos tres tipos de token:

| Tipo | Dónde se crea | Cuándo conviene |
|---|---|---|
| Token personal | Tu avatar → **Edit profile** → **Access tokens** | Pruebas o equipos pequeños |
| Token de grupo | Grupo → **Settings** → **Access tokens** | Recomendado: cubre todos los repositorios del grupo sin depender de una persona |
| Token de proyecto | Repositorio → **Settings** → **Access tokens** | Cuando solo se vincula un repositorio |

Al crearlo:

1. Asigna un nombre que lo identifique, por ejemplo `solercia-command`.
2. Define una fecha de vencimiento y regístrala en el calendario del equipo para renovarlo a tiempo.
3. Para tokens de grupo o de proyecto, elige el rol **Reporter**: alcanza para leer merge requests y commits.
4. Marca **solo** el alcance `read_api`. Opcionalmente puedes agregar `read_repository` o `read_user`.
5. Copia el token; GitLab lo muestra una sola vez.

Command rechaza el token, sin guardarlo, cuando:

- no tiene el alcance `read_api`;
- tiene cualquier alcance fuera de esta lista de solo lectura: `read_api`, `read_user`, `read_repository`, `read_registry`, `read_virtual_registry`, `read_observability`, `openid`, `profile` y `email`. Por ejemplo, se rechazan `api`, `write_*`, `sudo`, `admin_mode`, `create_runner`, `manage_runner`, `k8s_proxy`, `self_rotate` y `ai_features`, y también cualquier alcance nuevo que GitLab agregue hasta que se revise;
- GitLab no permite consultar sus alcances (`GET /api/v4/personal_access_tokens/self` responde 404, por ejemplo en versiones antiguas de GitLab);
- GitLab lo reporta como vencido, revocado o inválido.

La dirección del servidor también se rechaza si contiene espacios o caracteres de control.

## 2. Permite el servidor de GitLab

Por seguridad, Command solo se conecta a servidores listados en la variable `GITLAB_BASE_URL_ALLOWLIST` del backend (nombres de servidor separados por coma). El valor por defecto es `gitlab.com`.

Si tu entidad usa una instancia propia, agrégala en el `.env`:

```env
GITLAB_BASE_URL_ALLOWLIST=gitlab.com,gitlab.entidad.gov.co
```

Reglas de la validación:

- La dirección debe usar `https`.
- El nombre del servidor debe coincidir exactamente con uno de la lista; no se aceptan subdominios ni direcciones con usuario (`https://usuario@servidor`).
- La validación ocurre antes de cualquier llamada de red.

Después de cambiar la variable, reinicia el backend para que la tome.

## 3. Registra la conexión en Command

Un administrador o gestor de la organización:

1. Abre **Conexiones** y elige **Conectar GitLab**.
2. Ingresa la dirección del servidor (por ejemplo, `https://gitlab.com`) y el token.
3. Al guardar, Command valida el token contra GitLab (`GET /api/v4/user` y `GET /api/v4/personal_access_tokens/self`) y lo guarda cifrado. El token no vuelve a mostrarse ni se registra en los logs.
4. Si GitLab rechaza el token, no queda ninguna conexión creada: corrige el token y vuelve a guardar.

## 4. Vincula los repositorios de cada proyecto

En la tarjeta de GitLab, en **Conexiones**, elige un proyecto de Command y marca los repositorios que le corresponden. La lista muestra los proyectos de GitLab de los que el token es miembro. Command comprueba cada repositorio con GitLab antes de guardarlo. Puedes vincular hasta 20 repositorios por proyecto.

## 5. Qué muestra la integración

En el detalle de cada tarea, el panel **Desarrollo** consulta en vivo los repositorios vinculados al proyecto y muestra:

- **Merge requests** cuyo título menciona la clave de la tarea, con estado, autor, rama, fecha y enlace.
- **Commits** cuyo mensaje menciona la clave de la tarea, con autor, fecha y enlace.

La clave se compara como palabra completa y sin distinguir mayúsculas: `CMD-12` coincide con `CMD-12: corrige el inicio de sesión` o con `[cmd-12]`, pero no con `CMD-123`. Para que una tarea muestre actividad, incluye su clave en el título del merge request o en el mensaje del commit.

Límites de esta versión:

- Solo lectura y en vivo: no hay webhooks ni copia local de la actividad.
- Los commits se buscan entre los más recientes de todas las ramas (hasta 500 por repositorio); los merge requests, por búsqueda en el título.
- Cualquier miembro de la organización que pueda ver la tarea ve su panel **Desarrollo**; solo administradores y gestores configuran el token y la vinculación.
