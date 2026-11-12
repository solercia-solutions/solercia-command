# Controles de privacidad para IA en Solercia Command

**Estado: propuesta técnica documental; no es política institucional, concepto jurídico ni certificación de cumplimiento.** BYOK (aportar una clave propia), contratar un plan privado o ejecutar un modelo local no autoriza el tratamiento de información institucional. Hasta demostrar la habilitación del caso de uso, los datos y el destino, la propuesta es **denegar la salida de información** y conservar una alternativa sin IA.

## Evidencia local y alcance

Se consultaron exclusivamente las copias locales indicadas por el solicitante, sin modificar originales, instalar dependencias, consultar proveedores ni descargar documentos. La vigencia actual y la autenticidad de publicación no se verificaron en línea.

| ID | Fuente y versión observada | Estado y cobertura |
| --- | --- | --- |
| A | `Acuerdo 003 de 2025 Alcaldía Mayor de Bogotá, D.C. - Comisión Distrital de Transformación Digital.pdf` | Copia informativa de 6 páginas. P. 1: expedición 26/12/2025, entrada en vigencia 31/12/2025 y Registro Distrital 8488 del 30/12/2025. P. 4: aprobación en sesión del 10/12/2025, Acta 04. Leído el texto extraíble de pp. 1–5; p. 6 sin texto ni objetos detectados por el extractor, sin comprobación visual. No acredita ausencia de modificaciones posteriores. |
| D | `Decálogo Uso Cotidiano de IA en el Distrito_2026.pdf` | Material de orientación distrital, 6 páginas leídas. El año 2026 figura en el nombre del archivo; el contenido no presenta control de versión ni acto de aprobación propio. Remite al Acuerdo 003, pero no reemplaza su anexo. |
| M | `Lineamientos para Sistemas con IA.pdf` | Título interior: *Lineamientos de Seguridad y Privacidad de la Información para Sistemas de Inteligencia Artificial*, MinTIC, Dirección de Gobierno Digital. P. 2: versión 1, 22/04/2026, V 1.0. Leído el texto extraíble de las 60 páginas, incluidos índices y bibliografía. Documento técnico nacional; no se verificó un acto específico de adopción de esta copia. **No es el anexo distrital del Acuerdo 003.** |
| P | `GT-PLT-3_V4_POLITICA_PRIVACIDAD_DATOS_AJUSTADO.docx` | Propuesta V4 pendiente de aprobación CIGD según su control de cambios. Lectura contextual del numeral 14 completo (párrafos XML 571–684), numeral 9.8 (450–474), definiciones 146, 158 y 194 y control de cambios 747–752. No se revisó íntegramente el resto del DOCX. El nombre `01_VERSION_FINAL` no acredita aprobación. |

**Localizadores:** A, D y M están en `LINEAMIENTOS EXTERNOS/`, dentro de la carpeta institucional local `2026/`. P está en `REVISIÓN DOCUMENTOS/SALIDA_DOCUMENTOS/ENTREGABLES/MODIFICACIONES/GT-PLT-3_POLITICA_PRIVACIDAD_V4/01_VERSION_FINAL/`, bajo esa misma carpeta. Los nombres se muestran normalizados con tildes; el sistema de archivos puede representarlas como caracteres combinados. No se incorporan copias ni datos personales al repositorio.

**Método de cita:** páginas PDF contadas desde 1, incluida la portada. En P, `XML ¶n` es el n-ésimo elemento `w:p` de `word/document.xml`, recorrido en orden documental, incluidos párrafos vacíos y de tablas; no equivale a una página de Word. Se concatenaron sus nodos `w:t`. Se detectaron 767 párrafos, sin elementos de inserción o eliminación controlada en ese XML. No se inspeccionaron comentarios, adjuntos, encabezados ni otros componentes del DOCX. Extracción en memoria con `pdfplumber` instalado y ZIP/XML de Python, con máximo de 5.000 caracteres por salida; sin OCR ni renderizado visual. La extracción de tablas o diagramas no demuestra fidelidad visual completa.

## Citas textuales verificadas

Estas citas son evidencia, no una interpretación jurídica:

- **A, artículo 3, p. 5:** «contenidos en el ANEXO LINEAMIENTOS TÉCNICOS Y ÉTICOS EN IA PARA EL DISTRITO CAPITAL DE BOGOTÁ y sus herramientas». Ese anexo no estaba entre los tres PDF revisados.
- **D, pregunta 5, p. 4:** «Datos personales o sensibles.» y «Documentos oficiales no publicados.» son elementos de la lista precedida por «No. Está prohibido ingresar:» en herramientas abiertas. La misma lista incluye información clasificada o reservada, estratégica, contractual o financiera, archivos confidenciales y parámetros de sistemas críticos.
- **D, pregunta 6, p. 4:** «Solo puede hacerse en entornos cerrados, seguros y aprobados institucionalmente». El contexto exige autorización del proyecto por TI y licencia del proveedor, protocolos de anonimización o seudonimización y registro en el expediente.
- **P, control de cambios, XML ¶751:** «[pendiente de aprobación CIGD]».
- **P, definiciones, XML ¶194:** «los datos seudonimizados siguen siendo datos personales». El párrafo define un proceso reversible con información adicional separada y controles de acceso.
- **P, definición de entorno aprobado, XML ¶158:** «No tienen esta condición las herramientas de IA de acceso público o gratuito, ni las contratadas o instaladas a título personal.» Esta es una disposición del borrador, no una aprobación institucional vigente demostrada.
- **M, §11.4.6, p. 34:** «identifiquen a individuos a partir de datos aparentemente anónimos» describe un riesgo de inferencias de los sistemas de IA.
- **M, tabla 4, p. 42:** «No incluir información sensible en los prompts del sistema.»

## Requisitos propuestos e interpretación técnica

Lo siguiente es **análisis propio y propuesta de diseño**, no texto oficial ni capacidad implementada. Las referencias P aportan requisitos candidatos sujetos a aprobación; no sustituyen fuentes vigentes. Las aprobaciones humanas de una operación no pueden levantar prohibiciones institucionales.

| Control | Requisito para el diseño | Fundamento y límite |
| --- | --- | --- |
| C1. Finalidad y clasificación | Resolver entidad, cuenta, finalidad, categorías de información y autorización antes de preparar una petición. Información desconocida, mezclada entre entidades o sin clasificación: denegar. Evitar que el LLM determine permisos. | D pp. 3–5; M §§10.4, 11 y 12.4.1; P ¶602–606 y 642–653. |
| C2. Destino aprobado | Separar proveedor abierto/no autorizado, nube institucional aprobada y ejecución local institucional aprobada. Ninguno queda autorizado por su etiqueta comercial. Exigir evidencia del entorno y del proyecto, contrato/licencia aplicable, ubicación del tratamiento, subencargados, retención, uso para entrenamiento y alcance autorizado. Sin evidencia suficiente: denegar. | D p. 4; P ¶158, 457–473 y 642–653. BYOK solo aporta autenticación/facturación; no constituye permiso de tratamiento. |
| C3. Información protegida | No enviar a herramientas abiertas o no autorizadas datos personales, sensibles, clasificados o reservados, documentos oficiales no publicados, archivos confidenciales ni parámetros críticos. No habilitar por inferencia información estratégica, contractual o financiera. | D pregunta 5. P ¶595 introduce una precisión sobre carácter público que no debe usarse para relajar el Decálogo mientras sea borrador y no exista resolución competente. |
| C4. Minimización y anonimización | Preparar una copia derivada con solo los datos necesarios; evaluar identificadores directos, indirectos, combinaciones y riesgo de reidentificación. Quitar nombres no prueba anonimización. Los seudónimos reversibles siguen siendo datos personales; la tabla de correspondencia debe quedar separada y fuera del contexto del modelo. | M pp. 21, 34 y 47–49; P ¶146, 194 y 645–650, 679. Anonimizar no elimina por sí solo reserva documental, confidencialidad ni restricciones de finalidad. |
| C5. Superficie completa | Aplicar controles al texto, historial, adjuntos y sus nombres, propiedades, comentarios, cambios controlados, hojas ocultas, imágenes, OCR, vínculos, resultados de herramientas, contexto recuperado y salidas del modelo. Si una parte no puede inspeccionarse de manera segura, no enviarla. | Extensión técnica de la protección de datos y defensa en profundidad de M pp. 40–54; no es una lista literal de los documentos. Un resultado de herramienta no hereda permiso para salir al proveedor. |
| C6. Secretos | Nunca incluir claves API, contraseñas, cookies, tokens, credenciales ni configuraciones críticas en prompts, archivos preparados o registros. Resolver secretos mediante referencias a almacenamiento seguro, fuera del contenido del modelo y sin fallback a texto plano. | D p. 4; M p. 42; P ¶597; decisiones de plataforma §§3.3 y 4.4. Detectar patrones no demuestra ausencia de secretos: ante duda, bloquear. |
| C7. Barrera de salida | Autorizar el destino exacto y la copia final antes de cada llamada, también en reintentos, herramientas y cambios de proveedor. Sin fallback automático a nube. El contenido de documentos o instrucciones del modelo no modifica la política. | Propuesta determinista basada en M §§12.1–12.2 y las fronteras del ADR. El procesamiento local reduce exposición de red solo si se comprueban telemetría, sincronización, registros, cachés y llamadas auxiliares; no evade gobernanza. |
| C8. Revisión humana | Mantener la IA como apoyo. No habilitar con IA cotidiana decisiones administrativas, conceptos jurídicos, interpretación normativa, asignación de recursos o prioridades ni automatización decisoria. Revisar antes de adoptar, publicar, radicar o comunicar resultados. | D preguntas 3–4 y 8–10; P ¶587, 612 y 616–626. Un visto bueno posterior no subsana un uso prohibido. Este documento es un insumo técnico para responsables humanos, no un concepto institucional. |
| C9. Correo | Separar generación de borrador y envío. Confirmar cuenta y canal de la entidad, destinatarios verificados, duplicados en enviados y vista previa completa; exigir aprobación explícita del envío. Si falta el canal correcto, entregar texto y detenerse. | Regla operativa del solicitante y del arnés; no se atribuye a los PDF. Además, respetar identidad canónica y rutas oficiales del ADR: ninguna excepción implícita por correo o por aprobación humana. |
| C10. Auditoría sin fuga | Registrar decisión, razón, versión de política, destino, categorías, referencia de autorización y responsable en un registro protegido y mínimo; no copiar cargas, secretos ni datos sensibles a logs, trazas, errores, analítica o memoria de agentes. Definir acceso, retención y eliminación antes de habilitar. | D pregunta 7; M pp. 21, 33, 49–52 y 56; P ¶652–653. Conciliar trazabilidad con minimización; no convertir registros de razonamiento en un depósito de información protegida. |
| C11. Originales e incidentes | Mantener los originales intactos en su ubicación institucional. Tratar copias derivadas, cachés, índices y embeddings como activos sujetos a controles. Definir conservación según instrumentos aplicables y procedimiento de incidentes; suspender ante fuga o pérdida de control. | P ¶634, 651 y 680; M §§12.2.2.7 y 12.4.1.6. Este trabajo no elimina ni modifica archivos institucionales. |

## Alineación con las decisiones de plataforma

El [registro aceptado de decisiones de plataforma](../decisions/2026-08-23-solercia-platform-decisions.md), especialmente §§3–5, mantiene la autenticación oficial, la identidad observada antes de leer, los secretos fuera de prompts/logs y las decisiones de integración en código determinista. BYOK no cambia esas fronteras. El gestor seguro de tokens de producción figura allí como trabajo pendiente: no se presenta como implementado.

El futuro control debe operar antes del adaptador de IA y mantenerse separado de la adquisición de hechos de Connect. Este documento no autoriza cambios en conectores, servicios, bases de datos, proveedores o arquitectura, ni permite reemplazar los contratos deterministas por instrucciones de prompt.

## Decisiones pendientes de las autoridades competentes

1. **Vigencia y jerarquía:** obtener el anexo distrital adoptado, confirmar versiones oficiales vigentes y aprobación/publicación de P. No equiparar M con el anexo faltante ni el nombre de archivo final con una política aprobada.
2. **Habilitación concreta:** TI, seguridad, protección de datos y Jurídica deben resolver caso de uso, base de tratamiento, evaluación de impacto, naturaleza del receptor y transmisión/transferencia internacional, contratos y subencargados. No se certifica conformidad a partir de estas copias.
3. **Anonimización:** revisar GT-GU-4 y fijar evidencia y criterios de riesgo aceptables por caso. No se ha leído esa guía ni se afirma un umbral universal, suficiencia de expresiones regulares o anonimización garantizada.
4. **Tensiones documentales:** resolver la precisión de P ¶595 frente a D pregunta 5; conciliar las recomendaciones de M tabla 4, p. 44, sobre registros de razonamiento con confidencialidad, minimización y capacidades reales del proveedor. No registrar contenido sensible para cumplir una recomendación de trazabilidad.
5. **Operación:** aprobar inventario de destinos, categorías permitidas, conservación, acceso a auditoría, tratamiento de incidentes y evidencia de controles locales/nube. Hasta resolver cada requisito aplicable, mantener denegada la salida afectada.

## Siguiente paso: contrato del control previo a la salida

Diseñar, sin conectarse a proveedores, una tabla de decisión determinista con entradas de entidad/cuenta verificadas, finalidad, clasificación, autorización vigente, destino y evidencia de transformación. Salida: **permitir o denegar con razón verificable**; faltar información equivale a denegar. La aprobación debe quedar vinculada a la copia exacta y al destino, no a una conversación abierta.

Casos mínimos para la futura especificación: BYOK sin aprobación, modelo local personal, datos seudonimizados, adjunto no inspeccionable, secreto en resultado de herramienta, metadatos identificables, cambio de destino tras aprobar, mezcla de entidades, inyección de instrucciones y fallo del control. En todos ellos, demostrar ausencia de llamadas y de contenido sensible en registros. Ninguna de estas pruebas ni controles está implementada por este documento.

## Identidad de las copias consultadas

SHA-256 calculado localmente; identifica la copia, no acredita autenticidad ni vigencia:

| Fuente | SHA-256 |
| --- | --- |
| A | `b1c9ff9808213d5c33517356018efc37874a3045f7fe188c6b61f104f032835c` |
| D | `9d50405f11f5b5e0e323f1095642697169e129fed0c86225036d2363b15189d7` |
| M | `0f5762a0d28fb4af71524e324d039c1e7b8e523c88ecfdfc4405258d22a33edd` |
| P | `f0423e0420e7a98b441f95604402d95d5fceff742bf49301de6cbccfbdafcf6b` |
