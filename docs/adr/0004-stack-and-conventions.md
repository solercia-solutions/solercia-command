# ADR 0004 — Stack tecnológico y convenciones de idioma

- **Estado:** Aceptado
- **Fecha:** 2026-06-26
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/ARCHITECTURE.md`, `docs/API.md`

---

## Contexto

Solercia Project Manager necesita un stack moderno, productivo y coherente para un MVP
multi-tenant que se levanta completo con `docker compose up --build`. El proyecto, además,
es bilingüe por diseño: el equipo desarrolla en inglés, pero el producto se entrega a
personas usuarias de habla hispana en Colombia. Necesitamos fijar tanto las tecnologías como
las **convenciones de idioma**, para que ambas decisiones sean explícitas y no queden a
criterio de cada quien.

## Decisión

### Stack tecnológico

**Backend**

| Componente       | Elección                          | Razón                                                        |
| ---------------- | --------------------------------- | ------------------------------------------------------------ |
| Framework        | FastAPI                           | Async nativo, validación con Pydantic, Swagger automático.   |
| ORM              | SQLAlchemy 2.0 (estilo async)     | API moderna `select()`, tipado, ecosistema maduro.           |
| Driver DB        | asyncpg                           | Driver async de alto rendimiento para PostgreSQL.            |
| Validación       | Pydantic v2                       | Esquemas de entrada/salida rápidos y estrictos.              |
| Configuración    | pydantic-settings                 | Carga tipada desde variables de entorno.                     |
| Servidor ASGI    | uvicorn                           | Servidor async estándar para FastAPI.                        |
| Base de datos    | PostgreSQL 16                     | Relacional robusto; habilita RLS para endurecer multi-tenant.|
| Caché / colas    | Redis 7                           | Aprovisionado para necesidades futuras (no crítico en MVP).  |

**Frontend**

| Componente | Elección                   | Razón                                                       |
| ---------- | -------------------------- | ----------------------------------------------------------- |
| Framework  | Angular 20 (standalone)    | Componentes standalone, sin NgModules; base heredada del proyecto. |
| Estilos    | Tailwind 3                 | Utilidades + tokens de tema; `darkMode: 'class'`.           |
| Servidor   | `ng serve` en `0.0.0.0:4200` | Desarrollo con recarga en caliente dentro del contenedor.  |

**Puertos y conexión**

- Backend: uvicorn en el puerto de contenedor `8000`, publicado en el host `8000`.
- Frontend: `ng serve` en `0.0.0.0:4200`, publicado en el host `4200`.
- `DATABASE_URL = postgresql+asyncpg://app:app@postgres:5432/solercia`
- API base desde el navegador: `http://localhost:8000/api/v1`
- CORS: el backend permite el origen `http://localhost:4200`.
- Auth: JWT *bearer*. Admin semilla: `admin@solercia.com` / `Admin123*`.

### Convenciones de idioma (estrictas)

La regla separa **lo que se construye** de **lo que la persona usuaria lee**.

1. **En inglés** — código y artefactos técnicos:
   - Identificadores (variables, funciones, clases, métodos).
   - Nombres de archivo, carpetas, ramas.
   - Comentarios de código.
   - Claves de JSON y nombres de campo de la API.
   - Mensajes de commit, descripciones de PR y documentación técnica interna.

2. **En español colombiano formal con tuteo** — todo texto visible para la persona usuaria:
   - Mensajes de la API y errores de validación devueltos al cliente.
   - Etiquetas, botones, *placeholders* y títulos de la UI.
   - *Toasts*, mensajes de éxito/error y textos de ayuda.

3. **Tuteo formal, nunca voseo.** Se usa la forma de tú colombiana:
   - Correcto: «Inicia sesión», «Crea proyecto», «El nombre es obligatorio»,
     «Selecciona una metodología», «Verifica tus datos».
   - Incorrecto (voseo rioplatense): «Iniciá sesión», «Creá proyecto», «Ingresá»,
     «Seleccioná», «Verificá».

4. **Ortografía correcta en español.** Todo texto en español lleva tildes, acentos y eñes:
   gestión, sesión, contraseña, está, metodología, organización, descripción, validación.

#### Ejemplos del contrato de idioma

```python
# Código y claves en inglés; mensajes visibles en español formal (tuteo).
class ProjectCreate(BaseModel):
    name: str = Field(..., description="Nombre del proyecto")
    description: str | None = None
    methodology: Methodology

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("El nombre es obligatorio.")  # user-facing: Spanish
        return value
```

```typescript
// Angular: identificadores y nombres en inglés; copy de UI en español formal.
export const LOGIN_COPY = {
  title: 'Inicia sesión',
  emailPlaceholder: 'Correo electrónico',
  passwordPlaceholder: 'Contraseña',
  submit: 'Ingresar',
  invalidCredentials: 'Correo o contraseña incorrectos.',
} as const;
```

## Consecuencias

### Positivas

- **Coherencia de stack:** async de extremo a extremo (FastAPI + SQLAlchemy 2.0 async +
  asyncpg) y un frontend Angular standalone con Tailwind; decisiones alineadas y sin
  ambigüedad para todo el equipo.
- **Producto idiomático:** la persona usuaria recibe siempre español colombiano formal y
  bien acentuado, mientras el código permanece en inglés y portable para cualquier
  colaborador.
- **Separación clara de responsabilidades de idioma:** se elimina la duda de «¿en qué idioma
  va esto?» — depende de si es artefacto técnico o texto visible.
- **Swagger y tipos** gratis por usar FastAPI + Pydantic, lo que documenta el contrato de
  `docs/API.md` de forma viva.

### Negativas / costos

- **Disciplina bilingüe:** exige vigilar que ningún texto visible se escape en inglés y que
  ningún identificador termine en español. Conviene reforzarlo en revisión de código.
- **Riesgo de voseo o de pérdida de tildes** al redactar copy con prisa; se mitiga con la
  regla explícita y ejemplos canónicos de este ADR.
- **Versiones fijadas (Angular 20, Tailwind 3, PostgreSQL 16, etc.):** acotan el MVP pero
  exigirán una decisión deliberada para actualizar mayor versión más adelante.
