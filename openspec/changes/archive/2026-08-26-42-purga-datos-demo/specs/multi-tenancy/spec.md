# Delta for multi-tenancy

## MODIFIED Requirements

### Requirement: R4 — Seed idempotente con miembros demo condicionales

El seed inicial DEBE ser idempotente y crear la organización "Solercia" con el usuario `admin@solercia.com` SIN condición, en cada arranque. Los miembros demo (`ana@`, `carlos@`, `diana@`) DEBEN crearse ÚNICAMENTE cuando `settings.SEED_DEMO_DATA` sea `true` (ver capability `data-maintenance`); con el flag en `false` (valor por defecto), la organización "Solercia" y el usuario `admin@solercia.com` existen, pero ningún miembro demo se crea ni se recrea en arranques sucesivos.
(Previously: "El seed inicial DEBE ser idempotente y crear la organización 'Solercia' con sus miembros demo" — sin distinguir compuerta alguna; los 3 miembros demo se creaban siempre.)

#### Scenario: Organización y admin incondicionales
- DADO una base de datos vacía
- CUANDO la aplicación arranca, sin importar el valor de `SEED_DEMO_DATA`
- ENTONCES existen la organización "Solercia" y `admin@solercia.com` como miembro

#### Scenario: Miembros demo condicionados al flag
- DADO `settings.SEED_DEMO_DATA = false`
- CUANDO la aplicación arranca
- ENTONCES NO se crean `ana@`, `carlos@` ni `diana@` como miembros de "Solercia"

#### Scenario: Restart no revive miembros demo tras la purga
- DADO una base purgada (sin miembros demo) con `settings.SEED_DEMO_DATA = false`
- CUANDO el backend reinicia
- ENTONCES `organization_members` de "Solercia" contiene únicamente a `admin@solercia.com`
