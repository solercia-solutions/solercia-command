# Delta for org-role-templates

## ADDED Requirements

### Requirement: La purga de datos demo preserva el catálogo de plantillas de sistema

La operación de mantenimiento que purga datos demo (capability `data-maintenance`) DEBE borrar el árbol de proyectos instanciado por una plantilla de sistema (sombrilla, ramas y equipos generados) y sus filas de `org_role_template_instantiations` correspondientes cuando ese árbol pertenece al alcance demo, pero NUNCA DEBE borrar una fila de `org_role_templates` ni de `org_role_template_nodes` (catálogo de sistema, `organization_id IS NULL`, `is_system=true`). Tras la purga, `ensure_system_templates` sigue re-sembrando el catálogo en cada arranque sin duplicarlo.

#### Scenario: La purga borra el árbol instanciado y el ledger, no el catálogo
- DADO un árbol OAP-TI instanciado en la organización demo, con sus 12 filas en `org_role_template_instantiations`
- CUANDO se ejecuta la purga con `--execute`
- ENTONCES los proyectos de ese árbol y sus filas de `org_role_template_instantiations` quedan en 0, y las 5 `org_role_templates` de sistema permanecen intactas

#### Scenario: El catálogo sigue disponible tras la purga
- DADO que la purga terminó y el backend reinicia (`ensure_system_templates` corre de nuevo)
- CUANDO se consulta `GET /org-role-templates`
- ENTONCES se siguen recibiendo las 5 plantillas de sistema, sin duplicados
