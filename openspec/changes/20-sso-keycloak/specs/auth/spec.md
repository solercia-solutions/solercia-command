# Delta for auth

## MODIFIED Requirements

### Requirement: R4 — Verificación de contraseñas con bcrypt

Las contraseñas DEBEN verificarse con bcrypt directo (truncamiento a 72 bytes). Si `hashed_password` es NULL (usuario solo-SSO, sin contraseña local), el login por credenciales DEBE rechazarse con el mismo mensaje genérico de credenciales inválidas.
(Previously: no contemplaba usuarios sin `hashed_password`; se asumía que toda cuenta tenía contraseña.)

#### Scenario: Usuario solo-SSO intenta login local

- Dado un usuario con `hashed_password` NULL (creado o enlazado únicamente por SSO)
- Cuando envía `POST /auth/login` con cualquier contraseña
- Entonces responde 401 con el mismo mensaje genérico de credenciales inválidas

## ADDED Requirements

### Requirement: R6 — Convergencia de emisión de JWT tras SSO

Un login SSO exitoso DEBE emitir el mismo JWT propio que el login local: access token Bearer (30 min) y cookie de refresh httpOnly (7 días), con los roles RBAC locales vigentes del usuario en el momento de la emisión.

#### Scenario: Emisión de JWT tras callback SSO exitoso

- Dado un usuario correctamente autenticado vía IdP y resuelto/enlazado localmente
- Cuando el callback SSO completa la validación
- Entonces el sistema emite access token (30 min) y cookie de refresh (7 días, httpOnly) con los roles RBAC locales del usuario

### Requirement: R7 — Convivencia de login local y SSO

Un usuario con `hashed_password` definido Y una identidad federada enlazada DEBE poder autenticarse indistintamente por credenciales o por SSO; ningún método deshabilita al otro.

#### Scenario: Login dual por ambos métodos

- Dado un usuario con contraseña local vigente y una identidad SSO enlazada
- Cuando inicia sesión por `POST /auth/login` o por el flujo SSO
- Entonces ambos métodos autentican exitosamente y devuelven un JWT propio válido
