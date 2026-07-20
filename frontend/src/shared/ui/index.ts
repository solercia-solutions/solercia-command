// Puente: el design system vive en el paquete @solercia/ui. La Wave B migra
// las vistas heredadas para que importen desde aquí (`@shared/ui`), sin acoplarlas
// al nombre del paquete. Por ahora es un re-export puro.
export * from '@solercia/ui';

// Componentes app-local que complementan la lib (candidatos a subir a
// @solercia/ui cuando maduren). Mismo prefijo `sol-` y tokens `--sol-*`.
export * from './drawer/drawer.component';
