# Solercia Project Manager

Gestor de proyectos multi-tenant que reemplaza Jira y Microsoft Planner. Cada
proyecto elige su metodología al crearse (Planner, Kanban, Scrum o personalizada)
y eso define su comportamiento: columnas del tablero, estados permitidos, sprints
y modo de estimación.

## Arranque rápido

Requisitos: Docker y Docker Compose.

```bash
docker compose up --build
```

Este comando levanta los cuatro servicios (PostgreSQL, Redis, backend FastAPI y
frontend Angular). La primera ejecución tarda unos minutos mientras se construyen
las imágenes.

## URLs

| Recurso | URL |
|---------|-----|
| Interfaz de usuario | http://localhost:4200 |
| Documentación de la API (Swagger) | http://localhost:8000/docs |
| API base | http://localhost:8000/api/v1 |

## Credenciales de demostración

| Campo | Valor |
|-------|-------|
| Correo | admin@solercia.com |
| Contraseña | Admin123* |

## Cómo registrar un proyecto

1. Ingresa a http://localhost:4200 e inicia sesión con las credenciales de
   demostración.
2. En la pantalla de proyectos, haz clic en **Crear proyecto**.
3. Escribe el nombre del proyecto y, opcionalmente, una descripción.
4. Selecciona la metodología que necesitas:
   - **Planner**: estados simples, sin sprints ni puntos de historia.
   - **Kanban**: flujo continuo con tablero, sin sprints.
   - **Scrum**: backlog, sprints y estimación por puntos de historia (Fibonacci).
   - **Personalizada**: define tus propios estados y columnas.
5. Guarda. El proyecto queda almacenado en PostgreSQL y aparece en tu lista.

## Comandos útiles

Estos atajos están disponibles a través del `Makefile`:

| Comando | Descripción |
|---------|-------------|
| `make up` | Construye y levanta todos los servicios. |
| `make down` | Detiene y elimina los contenedores. |
| `make logs` | Muestra los registros de todos los servicios en tiempo real. |
| `make ps` | Muestra el estado de los servicios. |

## Servicios y puertos

| Servicio | Puerto host | Descripción |
|----------|-------------|-------------|
| frontend (Angular) | 4200 | Interfaz de usuario |
| backend (FastAPI) | 8000 | API y Swagger en `/docs` |
| postgres | 5432 | Base de datos |
| redis | 6379 | Caché y colas |

## Variables de entorno

Copia `.env.example` a `.env` para personalizar la configuración. Las variables
clave son `DATABASE_URL`, `REDIS_URL` y `JWT_SECRET`. En cualquier ambiente que no
sea de desarrollo, cambia `JWT_SECRET` por un valor secreto y seguro.

## Licencia

Copyright (C) 2026 Cristian Camilo Calderón Tapia.

Solercia Command es software libre: puedes usarlo, estudiarlo, modificarlo y
redistribuirlo bajo los términos de la Licencia Pública General Affero de GNU
(GNU AGPL), versión 3, publicada por la Free Software Foundation. Se distribuye
SIN NINGUNA GARANTÍA; consulta el archivo [LICENSE](LICENSE). Si ofreces una versión
modificada como servicio en red, debes poner su código fuente a disposición de
quienes usan ese servicio.
