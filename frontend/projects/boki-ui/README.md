# @boki/ui

Librería de componentes Angular con theming impulsado por JSON. La apariencia visual se controla editando un archivo `default.json`, sin tocar el código fuente. Compatible con Tailwind CSS a través de un preset incluido.

---

## Instalación

```bash
npm install @boki/ui
```

---

## Configuración rápida

### 1. Registrar el preset de Tailwind

En `tailwind.config.js` del proyecto consumidor:

```js
module.exports = {
  presets: [require('@boki/ui/tailwind-preset')],
  content: ['./src/**/*.{html,ts}'],
  // resto de tu config...
};
```

### 2. Registrar los proveedores en `app.config.ts`

```ts
import { ApplicationConfig } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideTheme, provideBokiLogger, provideBokiErrors, LogLevel } from '@boki/ui';

export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(),
    provideTheme(),            // carga assets/themes/default.json al iniciar
    provideBokiLogger({ minLevel: LogLevel.WARN }),
    provideBokiErrors(),
  ],
};
```

### 3. Usar un componente

```ts
import { CardComponent, ButtonComponent } from '@boki/ui';

@Component({
  standalone: true,
  imports: [CardComponent, ButtonComponent],
  template: `
    <bk-card [interactive]="true">
      <p>Contenido de la tarjeta</p>
      <bk-button variant="primary">Guardar</bk-button>
    </bk-card>
  `,
})
export class MiComponente {}
```

---

## Theming

El aspecto visual se define en `assets/themes/default.json` (modo claro y oscuro). El `ThemeService` convierte los valores hexadecimales a canales RGB e inyecta variables CSS `--sp-*` en tiempo de ejecución.

Para cambiar el tema, edita el JSON:

```json
{
  "light": {
    "color": {
      "brand": "#4F46E5"
    }
  },
  "dark": {
    "color": {
      "brand": "#6366F1"
    }
  }
}
```

El aspecto completo (colores, radios, sombras, tipografía, movimiento) está controlado por tokens `--sp-*`.

---

## API pública

| Exportación | Tipo | Descripción |
|---|---|---|
| `ThemeService` | Servicio | Carga y aplica el tema JSON |
| `provideTheme()` | Provider | Inicializa el tema al arrancar |
| `ThemeFile`, `ThemeConfig` | Interfaces | Tipos del modelo de tema |
| `DEFAULT_THEME` | Constante | Tema por defecto como objeto TypeScript |
| `BokiLogger` | Servicio | Logger estructurado con niveles |
| `LogLevel` | Enum | DEBUG / INFO / WARN / ERROR / NONE |
| `provideBokiLogger()` | Provider | Configura el logger |
| `BOKI_LOGGER_CONFIG` | Token | Token de inyección para la configuración |
| `provideBokiErrors()` | Provider | Cablea `ErrorHandler` + interceptor HTTP |
| `BokiErrorHandler` | Clase | Captura errores no controlados |
| `bokiHttpErrorInterceptor` | Función | Interceptor HTTP funcional |
| `AppError` | Clase | Error tipado con código y mensaje de usuario |
| `CardComponent` | Componente | Contenedor con borde y sombra, selector `bk-card` |
| `ButtonComponent` | Componente | Botón temático con variantes, selector `bk-button` |

---

## Licencia

Copyright © 2026 Camilo Calderón. Todos los derechos reservados. Consulta el archivo `LICENSE` para más información.
