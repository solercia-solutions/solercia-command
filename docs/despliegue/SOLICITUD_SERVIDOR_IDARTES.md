# Solicitud de servidor para la herramienta de gestión de proyectos con asistente de IA

**Para:** [Nombre], [Cargo] — [Área de Tecnología / Sistemas], Instituto Distrital de las Artes (IDARTES)
**De:** Cristian Camilo Calderón Tapia — [Cargo / dependencia]
**Fecha:** [AAAA-MM-DD]
**Asunto:** Solicitud de un servidor virtual para la puesta en producción de la herramienta de gestión de proyectos que reemplaza a Jira, con un módulo de inteligencia artificial en fase MVP

## 1. Objeto

Se solicita la asignación de un servidor virtual para desplegar en producción **Solercia Command**,
la herramienta de gestión de proyectos que reemplaza a Jira en el equipo. La herramienta incluye
un **asistente de inteligencia artificial en fase de producto mínimo viable (MVP)** que se ejecuta
dentro del propio servidor, sin enviar información a servicios externos.

## 2. Contexto

- La información de trabajo del equipo ya fue migrada desde Jira a la herramienta: 21 proyectos,
  1.756 tareas, 100 sprints y 96 usuarios, conservando las fechas reales de creación,
  actualización, vencimiento y resolución.
- La herramienta cubre los usos que hoy se resuelven en Jira: proyectos con metodología
  configurable (Scrum, Kanban o tipo Planner), backlog, sprints, tableros, tareas y subtareas,
  comentarios, filtros por vigencia y una vista ejecutiva del estado del equipo.
- El módulo de IA lee los correos del período, los agrupa por conversación, identifica a qué
  tarea corresponden y si quedaron atendidos o pendientes, y deja una **propuesta** que una
  persona acepta o descarta. El sistema no cambia el estado de una tarea por sí solo.

## 3. Por qué la IA se ejecuta dentro del servidor

- **Confidencialidad:** el contenido de los correos institucionales no sale del servidor. El
  modelo de lenguaje es de pesos abiertos y se ejecuta localmente.
- **Reproducibilidad:** con la configuración definida, el mismo correo produce la misma
  clasificación en cada corrida, lo que permite auditar y comparar resultados.
- **Flexibilidad:** si en el futuro la entidad lo decide, la herramienta permite conectar un
  proveedor externo con llave propia (BYOK) sin cambios de código, con aviso explícito sobre el
  envío de información fuera del servidor.

## 4. Requerimientos del servidor

La herramienta no requiere GPU. Las cifras se basan en pruebas con un perfil de servidor
emulado (4 vCPU, 8 GB para el modelo) y en el consumo medido de cada componente.

| Recurso | Mínimo (operación viable) | **Recomendado** | Óptimo (si existe disponibilidad) |
|---|---|---|---|
| vCPU | 4 | **8** | 8 a 16 |
| Familia de procesador | x86-64 con AVX2 (Intel Xeon o AMD EPYC) | **Intel Xeon Scalable de 3.ª generación o posterior, o AMD EPYC, con AVX2** | Intel Xeon de 4.ª generación o posterior (AVX-512 y AMX) |
| Memoria RAM | 16 GB | **32 GB** | 32 a 64 GB |
| GPU | No requerida | No requerida | NVIDIA L4 (24 GB) o T4 (16 GB) asignada a la VM |
| Disco | 150 GB SSD | **250 GB SSD** | 250 GB SSD + volumen de respaldos |
| Sistema operativo | Ubuntu Server 24.04 LTS (64 bits) | Ubuntu Server 24.04 LTS | Ubuntu Server 24.04 LTS |
| Virtualización | VMware u Oracle, con las instrucciones AVX2 expuestas a la VM | Igual | Igual, con *passthrough* de GPU |

### 4.1 Distribución estimada de memoria (perfil recomendado)

| Componente | Memoria |
|---|---|
| Modelo de IA local (9.000 millones de parámetros, cuantizado) | 8 GB (pico medido: 7 GB) |
| Modelo de búsqueda semántica (embeddings) | 1 GB |
| Base de datos PostgreSQL | 4 GB |
| Redis, API y aplicación web | 3 GB |
| Sistema operativo y Docker | 2 GB |
| Margen para crecimiento y picos | 14 GB |

### 4.2 Tiempos esperados del asistente de IA

El asistente corre dos veces al día (06:00 y 23:59) y procesa por lotes, sin afectar el uso
interactivo de la herramienta. En el perfil probado (4 vCPU), una corrida de 40 conversaciones
toma entre 20 y 60 minutos, según el procesador. Con 8 vCPU se espera reducir ese tiempo cerca
de la mitad, y con GPU a pocos minutos. Estas estimaciones se confirmarán en el servidor asignado
con el diagnóstico de la sección 6.

## 5. Red, acceso y operación

- **Acceso de usuarios:** HTTPS (443) con un subdominio institucional (por ejemplo,
  `[proyectos].idartes.gov.co`) y su certificado TLS.
- **Acceso administrativo:** SSH restringido a la red o VPN institucional.
- **Salida a internet:** HTTPS durante la instalación y las actualizaciones, para descargar las
  imágenes de contenedores (Docker Hub, GitHub Container Registry) y los modelos de IA
  (registro de Ollama o Hugging Face). En operación, la IA no requiere salida a internet.
- **Software:** Docker Engine y Docker Compose. La herramienta se despliega en contenedores
  (base de datos, caché, API, aplicación web y modelo de IA), con versiones fijas.
- **Respaldos:** copia diaria de la base de datos con retención mínima de 7 días, según la
  política de respaldos de la entidad.
- **Correo:** para el módulo de IA se requiere, en una fase posterior, la autorización de
  lectura del buzón de los usuarios que lo activen, conforme a la política de la entidad.

## 6. Verificación previa

Una vez asignado el servidor, se ejecutará un diagnóstico de solo lectura
(`diagnostico-servidor-ia.sh`) que no requiere privilegios de administrador ni modifica el
sistema. Ese diagnóstico confirma la CPU, las instrucciones disponibles, la memoria y el disco, y
con él se ajustan los límites de cada componente antes de la puesta en producción.

## 7. Beneficios esperados

- Continuidad de la gestión de proyectos del equipo en una herramienta propia, con la
  información ya migrada desde Jira.
- Seguimiento de compromisos que hoy llegan por correo, con propuestas trazables que una persona
  valida.
- Información institucional procesada dentro de la infraestructura de la entidad.

Quedo atento a la asignación del servidor o a los ajustes que el área considere sobre las
especificaciones.

Cordialmente,

Cristian Camilo Calderón Tapia
[Cargo]
cristian.calderontapia@idartes.gov.co
