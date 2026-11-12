# Solercia Command — Frontend

Aplicación web de Solercia Command para coordinar proyectos y trabajo multi-tenant. Construida con **Angular 20**
(componentes standalone + signals) y **Tailwind CSS 3** con tema claro/oscuro.

## Tecnología

- Angular 20 standalone, ruteo con lazy loading y guard funcional.
- HttpClient con interceptor de autenticación (Bearer JWT).
- Tailwind CSS 3 (`darkMode: 'class'`) con tokens `--sp-*` para claro/oscuro.
- Estado local con Angular signals.

## Requisitos

- Node.js 22+
- npm 10+

## Desarrollo local

```bash
npm install
npm start
```

La aplicación queda disponible en http://localhost:4200 y consume la API en
`http://localhost:8000/api/v1` (ver `src/app/core/api.config.ts`).

Usuario de prueba sembrado en el backend:

- Correo: `admin@solercia.com`
- Contraseña: `Admin123*`

## Build de producción

```bash
npm run build
```

El resultado queda en `dist/frontend`.

## Docker

```bash
docker build -t solercia-pm-frontend .
docker run -p 4200:4200 solercia-pm-frontend
```

En el `docker compose` raíz el servicio se publica en el host en el puerto 4200.

## Estructura

```
src/app/
  core/        Servicios transversales (auth, theme, interceptor, guard, config)
  shared/ui/   Componentes reutilizables (button, card, text-input)
  features/
    auth/      Inicio de sesión
    projects/  Listado y creación de proyectos
```

## Tema claro/oscuro

El botón de la cabecera alterna la clase `dark` en `<html>`. Los colores se
definen como canales RGB en `src/styles.scss` (`:root` y `.dark`) y se exponen a
Tailwind como colores semánticos (`brand`, `surface`, `text`, `muted`, `border`).
La preferencia se guarda en `localStorage` y, en su ausencia, se usa
`prefers-color-scheme`.
