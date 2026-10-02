// Puente: el design system vive en el paquete @solercia/ui. La Wave B migra
// las vistas heredadas para que importen desde aquí (`@shared/ui`), sin acoplarlas
// al nombre del paquete. Por ahora es un re-export puro.
export * from '@solercia/ui';

// Bloque presentacional de error (código, título, mensaje y código de seguimiento copiable),
// reutilizable en páginas de error y dentro de paneles. Es el único componente app-local.
export * from './error-state';

// Sin más componentes app-local: `sol-drawer` vivía aquí mientras la librería no lo
// exponía (0.3.0). Desde 0.5.0 `SolDrawerComponent` llega por el re-export de
// arriba, así que el local se eliminó — mantener ambos dejaba el mismo símbolo
// exportado dos veces por este barril y el nombre quedaba ambiguo.
//
// Diferencias que absorbió la migración: el input `position="right"` es ahora
// `side="end"` (ningún consumidor lo usaba), y el input `blur` desapareció
// porque la librería resuelve el desenfoque con el token `--sol-overlay-blur`.
