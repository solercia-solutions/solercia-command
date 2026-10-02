// Arnés de paridad visual: shell Angular de PANDORA frente a Solercia Command.
//
// Los dos frontends se sirven en local sin backend. Toda petición de API se intercepta en el
// navegador y se resuelve con `simulacion.mjs`; cualquier salida que no sea localhost se bloquea,
// salvo las fuentes de Google que declara el tema. Ver README.md para el método y los parámetros.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { DATOS, sesionCommand, simuladorCommand, simuladorPandora } from './simulacion.mjs';

const env = (nombre, porDefecto) => process.env[nombre] ?? porDefecto;
const exigir = (nombre) => {
  if (!process.env[nombre]) throw new Error(`Falta la variable de entorno ${nombre}.`);
  return process.env[nombre];
};

const DEPS = exigir('DEPS'); // carpeta con node_modules de playwright-core, pixelmatch y pngjs
const OUT = exigir('OUT'); // carpeta de salida (capturas, diferencias, resultados.json)
const CHROME = exigir('CHROME'); // ejecutable de Chromium
const PANDORA_FRONT = exigir('PANDORA_FRONT'); // raíz del repo pandora_front (solo lectura)
const ORIGEN = {
  pandora: env('PANDORA_URL', 'http://localhost:54312'),
  command: env('COMMAND_URL', 'http://localhost:54311'),
};
const ONLY = process.env.ONLY ? new RegExp(process.env.ONLY) : null;

/** Importa una dependencia instalada fuera del repo (ESM no resuelve `NODE_PATH`). */
async function dep(nombre) {
  const dir = path.join(DEPS, 'node_modules', nombre);
  const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
  const raiz = pkg.exports?.['.'];
  const entrada = (typeof raiz === 'string' ? raiz : raiz?.import ?? raiz?.default) ?? pkg.main ?? 'index.js';
  return import(pathToFileURL(path.join(dir, entrada)).href);
}

const { chromium } = await dep('playwright-core');
const { PNG } = (await dep('pngjs')).default;
const pixelmatch = (await dep('pixelmatch')).default;

const TEMA = JSON.parse(fs.readFileSync(path.join(PANDORA_FRONT, 'src/assets/themes/idartes.json'), 'utf8'));
const LOGO = fs.readFileSync(path.join(PANDORA_FRONT, 'src/assets/branding/pandora-logo.png'));
const FUENTES_PERMITIDAS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);
const VIEWPORTS = { d1440: { width: 1440, height: 900 }, m390: { width: 390, height: 844 } };
const MODOS = ['claro', 'oscuro'];
const LADOS = ['pandora', 'command'];
const SIDEBAR_KEY = { pandora: 'pandora.sidebar.collapsed', command: 'sp-sidebar-collapsed' };
const RUTAS = {
  pandora: { tabla: '/modulos/administrador/gestionar-usuarios', migas: '/modulos/administrador/roles', error: '/prohibido' },
  command: { tabla: '/admin/users', migas: '/admin/roles', error: '/prohibido', estudio: '/settings/appearance' },
};

for (const carpeta of ['capturas', 'diferencias']) fs.mkdirSync(path.join(OUT, carpeta), { recursive: true });
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const incidencias = { sinSimular: new Set(), bloqueadas: new Set(), consola: new Set() };

// ------------------------------------------------------------------ contexto

async function abrir(lado, viewport, modo, opciones = {}) {
  const context = await browser.newContext({
    viewport: VIEWPORTS[viewport],
    deviceScaleFactor: 1,
    locale: 'es-CO',
    timezoneId: 'America/Bogota',
    colorScheme: modo === 'oscuro' ? 'dark' : 'light',
  });
  await context.clock.setFixedTime(new Date(DATOS.instante));
  const simular =
    lado === 'pandora'
      ? simuladorPandora({ temaBase: TEMA, origen: ORIGEN.pandora })
      : simuladorCommand({ temaBase: TEMA, menuEnvuelto: opciones.menuEnvuelto });

  await context.route('**/*', (route) => {
    const peticion = route.request();
    const url = new URL(peticion.url());
    if (url.protocol === 'data:' || url.protocol === 'blob:') return route.continue();
    if (url.hostname !== 'localhost' && url.hostname !== '127.0.0.1') {
      if (FUENTES_PERMITIDAS.has(url.hostname)) return route.continue();
      incidencias.bloqueadas.add(`${lado}: ${url.origin}`);
      return route.abort();
    }
    // Mismo logo en los dos lados: el del tema, servido desde los assets de PANDORA.
    if (lado === 'command' && url.pathname === TEMA.meta.logo.url) {
      return route.fulfill({ status: 200, contentType: 'image/png', body: LOGO });
    }
    const respuesta = simular(peticion.method(), url, peticion.postData());
    if (respuesta) return route.fulfill(respuesta);
    if (/^\/(api|auth|internal|bridge)(\/|$)/.test(url.pathname) && peticion.resourceType() !== 'document') {
      incidencias.sinSimular.add(`${lado}: ${peticion.method()} ${url.pathname}`);
      return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Sin simular"}' });
    }
    return route.continue();
  });

  const almacen = {
    'sol-dark-mode': String(modo === 'oscuro'),
    [SIDEBAR_KEY[lado]]: opciones.sidebar === 'colapsado' ? '1' : '0',
    ...(lado === 'command' ? sesionCommand() : {}),
  };
  await context.addInitScript((valores) => {
    for (const [clave, valor] of Object.entries(valores)) localStorage.setItem(clave, valor);
  }, almacen);

  const page = await context.newPage();
  page.on('console', (mensaje) => {
    if (mensaje.type() === 'error') incidencias.consola.add(`${lado}: ${mensaje.text().slice(0, 140)}`);
  });
  return { context, page };
}

async function ir(page, lado, ruta) {
  await page.goto(`${ORIGEN[lado]}${ruta}`, { waitUntil: 'networkidle' });
  await page.addStyleTag({
    content:
      '*,*::before,*::after{animation-duration:0s !important;animation-delay:0s !important;' +
      'transition-duration:0s !important;transition-delay:0s !important;caret-color:transparent !important}',
  });
}

async function asentar(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(700);
}

/** El modo pedido debe ser el efectivo; si el tema impuso otro, se conmuta con el botón del header. */
async function asegurarModo(page, modo) {
  const oscuro = () => page.evaluate(() => document.documentElement.classList.contains('dark'));
  if ((await oscuro()) !== (modo === 'oscuro')) {
    await page.locator('sol-theme-toggle button').first().click();
    await page.waitForTimeout(300);
  }
  if ((await oscuro()) !== (modo === 'oscuro')) throw new Error(`No fue posible fijar el modo ${modo}.`);
}

// ------------------------------------------------------------------ pasos compartidos

async function abrirTabla(page, lado, modo, { consultar = true } = {}) {
  await ir(page, lado, RUTAS[lado].tabla);
  await asegurarModo(page, modo);
  if (lado === 'pandora') {
    await page.waitForSelector('.sol-gestion-usuarios');
    if (!consultar) return;
    // PANDORA exige elegir una dependencia antes de consultar; Command lista al entrar.
    await page.locator('.sol-gestion-usuarios__filtro-select .sol-select__display').click();
    await page.locator('.sol-select__option').first().click();
    await page.locator('.sol-gestion-usuarios__titulo').click(); // cierra la lista desplegada
    await page.waitForSelector('.sol-select__dropdown', { state: 'hidden' });
    await page.locator('.sol-gestion-usuarios__filtro-boton button').click();
  }
  await page.waitForSelector('sol-data-table .sol-data-table__tr, sol-data-table .sol-data-table__card');
}

async function abrirEstudio(page, lado, modo) {
  if (lado === 'pandora') {
    // Entrada por el menú de usuario para conservar el módulo activo (y con él el menú lateral).
    await abrirTabla(page, lado, modo, { consultar: false });
    await page.locator('.sol-user-menu__trigger').click();
    await page.locator('.sol-user-menu__panel .sol-user-menu__item', { hasText: 'Apariencia' }).click();
  } else {
    await ir(page, lado, RUTAS.command.estudio);
    await asegurarModo(page, modo);
  }
  await page.waitForSelector('.controls .control-card', { timeout: 30000 });
  const alto = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y <= alto; y += 300) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(30);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function abrirHistorial(page) {
  await page.locator('[data-testid="studio-history"] button').click();
  await page.waitForSelector('.history-list li');
}

/** Navegación interna del enrutador de Angular, sin recargar la aplicación. */
async function navegarInterno(page, ruta) {
  await page.evaluate((destino) => {
    history.pushState({}, '', destino);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, ruta);
}

const ESTADO_ERROR = { pandora: '.sol-error-estado', command: '.sol-error-state' };
const ESTILOS_ERROR = ['', '__code', '__title', '__message', '__actions'].map((sufijo) => ({
  pandora: `.sol-error-estado${sufijo}`,
  command: `.sol-error-state${sufijo}`,
}));
const ambos = (selector) => ({ pandora: selector, command: selector });
const SIN_SIDEBAR_EN_MOVIL = { m390: 'A 390 px el sidebar no se pinta: lo reemplaza el menú inferior.' };
const SIN_MENU_INFERIOR_EN_ESCRITORIO = { d1440: 'A 1440 px el menú inferior no se pinta: navega el sidebar.' };

// ------------------------------------------------------------------ escenas

const ESCENAS = [
  {
    id: 'shell',
    titulo: 'Shell completo con tabla',
    async pasos(page, lado, modo) {
      await abrirTabla(page, lado, modo);
    },
    regiones: {
      encabezado: ambos('header.sol-header'),
      logo: ambos('sol-brand-logo'),
      sidebar: ambos('aside.sol-sidebar'),
      'menu-inferior': ambos('nav.sol-bottom-nav'),
      tabla: ambos('sol-data-table'),
    },
    estilos: [
      'header.sol-header', 'sol-brand-logo img', 'aside.sol-sidebar', '.sol-sidebar__item', '.sol-sidebar__label',
      '.sol-sidebar__toggle', '.sol-layout-main', '.sol-user-menu__trigger', '.sol-data-table__wrapper',
      '.sol-data-table__th', '.sol-data-table__td', '.sol-data-table__card', 'nav.sol-bottom-nav',
      '.sol-bottom-nav__item', '.sol-bottom-nav__label',
    ].map(ambos),
  },
  {
    id: 'sidebar-abierto',
    titulo: 'Sidebar abierto con tres niveles',
    noAplica: SIN_SIDEBAR_EN_MOVIL,
    async pasos(page, lado, modo) {
      await abrirTabla(page, lado, modo, { consultar: false });
      await page.locator('.sol-sidebar__item', { hasText: 'Reportes' }).click();
      await page.locator('.sol-sidebar__item', { hasText: 'Indicadores' }).click();
    },
    regiones: { sidebar: ambos('aside.sol-sidebar') },
    estilos: ['aside.sol-sidebar', '.sol-sidebar__item', '.sol-sidebar__children-inner .sol-sidebar__item', '.sol-sidebar__chevron'].map(ambos),
  },
  {
    id: 'sidebar-colapsado',
    titulo: 'Sidebar colapsado',
    noAplica: SIN_SIDEBAR_EN_MOVIL,
    opciones: { sidebar: 'colapsado' },
    async pasos(page, lado, modo) {
      await abrirTabla(page, lado, modo, { consultar: false });
    },
    regiones: { sidebar: ambos('aside.sol-sidebar') },
    estilos: ['aside.sol-sidebar', '.sol-sidebar__item', '.sol-layout-main'].map(ambos),
  },
  {
    id: 'menu-movil-mas',
    titulo: 'Menú móvil inferior y hoja «Más»',
    noAplica: SIN_MENU_INFERIOR_EN_ESCRITORIO,
    async pasos(page, lado, modo) {
      await abrirTabla(page, lado, modo, { consultar: false });
      await page.locator('[data-testid="bottom-nav-more"]').click();
      await page.waitForSelector('.sol-bottom-nav__sheet-item');
    },
    regiones: { 'menu-inferior': ambos('nav.sol-bottom-nav'), hoja: ambos('sol-bottom-nav sol-drawer [role="dialog"]') },
    estilos: ['.sol-bottom-nav__sheet-item', '.sol-bottom-nav__sheet-label', 'sol-bottom-nav sol-drawer [role="dialog"]'].map(ambos),
  },
  {
    id: 'menu-usuario',
    titulo: 'Menú de usuario abierto',
    async pasos(page, lado, modo) {
      await abrirTabla(page, lado, modo, { consultar: false });
      await page.locator('.sol-user-menu__trigger').click();
      await page.waitForSelector('.sol-user-menu__panel');
    },
    regiones: { disparador: ambos('.sol-user-menu__trigger'), panel: ambos('.sol-user-menu__panel') },
    estilos: [
      '.sol-user-menu__panel', '.sol-user-menu__header', '.sol-user-menu__header-name', '.sol-user-menu__badge',
      '.sol-user-menu__support-time', '.sol-user-menu__item', '.sol-user-menu__name-line', '.sol-user-menu__chevron',
    ].map(ambos),
  },
  {
    id: 'migas',
    titulo: 'Migas de pan',
    opciones: { menuEnvuelto: true },
    async pasos(page, lado, modo) {
      await ir(page, lado, RUTAS[lado].migas);
      await asegurarModo(page, modo);
      await page.waitForSelector('nav.sol-breadcrumb');
    },
    regiones: { migas: ambos('nav.sol-breadcrumb') },
    estilos: ['nav.sol-breadcrumb', '.sol-breadcrumb__item', '.sol-breadcrumb__link', '.sol-breadcrumb__current'].map(ambos),
  },
  {
    id: 'confirmacion',
    titulo: 'Diálogo de confirmación',
    async pasos(page, lado, modo, viewport) {
      await abrirTabla(page, lado, modo);
      if (viewport === 'm390') {
        // En tarjetas, las acciones de la fila aparecen al expandirla.
        const tarjeta = page.locator('.sol-data-table__card').first();
        if (await tarjeta.locator('.sol-data-table__card-chevron').count()) await tarjeta.locator('.sol-data-table__card-head').click();
      }
      const etiqueta = lado === 'pandora' ? /desactivar/i : /^elimina/i;
      await page.locator('sol-data-table').getByRole('button', { name: etiqueta }).first().click();
      await page.waitForSelector('.sol-confirm-panel');
    },
    regiones: { dialogo: ambos('.sol-confirm-panel') },
    estilos: [
      '.sol-confirm-overlay', '.sol-confirm-panel', '.sol-confirm-title', '.sol-confirm-message', '.sol-confirm-icon',
      '.sol-confirm-btn--danger', '.sol-confirm-btn--cancel',
    ].map(ambos),
  },
  {
    id: 'error-403',
    titulo: 'Página de error 403 (llegada desde el shell)',
    async pasos(page, lado, modo) {
      // Como llega una persona con sesión: el shell ya cargó el tema y la navegación es interna.
      await abrirTabla(page, lado, modo, { consultar: false });
      await navegarInterno(page, RUTAS[lado].error);
      await page.waitForSelector(ESTADO_ERROR[lado]);
    },
    regiones: { estado: ESTADO_ERROR },
    estilos: ESTILOS_ERROR,
  },
  {
    id: 'error-403-directa',
    titulo: 'Página de error 403 (carga directa)',
    sinReferencia: {
      oscuro:
        'En carga directa no hay botón de tema y el tema de PANDORA impone el modo claro; no hay captura oscura comparable.',
    },
    async pasos(page, lado) {
      await ir(page, lado, RUTAS[lado].error);
      await page.waitForSelector(ESTADO_ERROR[lado]);
    },
    regiones: { estado: ESTADO_ERROR },
    estilos: ESTILOS_ERROR,
  },
  {
    id: 'estudio-inicial',
    titulo: 'Theme Studio inicial',
    async pasos(page, lado, modo) {
      await abrirEstudio(page, lado, modo);
    },
    regiones: { estudio: ambos('sol-theme-studio') },
    estilos: ['.controls .control-card', '.controls', 'sol-theme-studio'].map(ambos),
  },
  {
    id: 'estudio-historial',
    titulo: 'Theme Studio con el historial abierto',
    async pasos(page, lado, modo) {
      await abrirEstudio(page, lado, modo);
      await abrirHistorial(page);
    },
    regiones: { historial: ambos('section.history-panel'), estudio: ambos('sol-theme-studio') },
    estilos: ['section.history-panel', '.history-list li'].map(ambos),
  },
  {
    id: 'estudio-restaurada',
    titulo: 'Theme Studio tras restaurar una versión',
    async pasos(page, lado, modo, viewport, capturarRegion) {
      await abrirEstudio(page, lado, modo);
      await abrirHistorial(page);
      await page
        .locator('.history-list li')
        .filter({ hasText: `Versión ${DATOS.versionRestaurada} ·` })
        .locator('sol-button button')
        .click();
      await page.waitForTimeout(400);
      const aplicar = viewport === 'm390' ? 'studio-apply-mobile' : 'studio-apply';
      await page.locator(`[data-testid="${aplicar}"] button`).click();
      await page.waitForSelector('.sol-confirm-panel');
      await capturarRegion('dialogo', '.sol-confirm-panel');
      await page.locator('.sol-confirm-panel .sol-confirm-btn').first().click();
      await page.waitForSelector('sol-alert-center [role="status"], sol-alert-center [role="alert"]');
      await capturarRegion('alerta', 'sol-alert-center [role="status"], sol-alert-center [role="alert"]');
      // La página se captura sin la alerta: dura 5 s y su instante de salida no es comparable.
      await page.waitForSelector('sol-alert-center [role="status"], sol-alert-center [role="alert"]', {
        state: 'detached',
        timeout: 15000,
      });
    },
    regiones: { estudio: ambos('sol-theme-studio'), historial: ambos('section.history-panel') },
    estilos: [],
  },
];

// ------------------------------------------------------------------ comparación

const PROPIEDADES = [
  'display', 'position', 'width', 'height', 'color', 'background-color', 'font-family', 'font-size', 'font-weight',
  'line-height', 'letter-spacing', 'text-transform', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'margin-top', 'margin-right', 'margin-bottom', 'margin-left', 'gap', 'border-top-width', 'border-top-color',
  'border-bottom-width', 'border-bottom-color', 'border-left-width', 'border-right-width', 'border-top-left-radius',
  'box-shadow', 'opacity', 'z-index',
];

const rutaCaptura = (nombre) => path.join(OUT, 'capturas', `${nombre}.png`);

function comparar(nombre) {
  const [a, b] = LADOS.map((lado) => PNG.sync.read(fs.readFileSync(rutaCaptura(`${nombre}__${lado}`))));
  // Tamaños distintos: se compara el área común (anclada arriba a la izquierda) y todo lo que
  // sobra de la unión cuenta como diferente. Así el porcentaje no depende del color de relleno
  // y es comparable entre claro y oscuro.
  const comun = { width: Math.min(a.width, b.width), height: Math.min(a.height, b.height) };
  const union = { width: Math.max(a.width, b.width), height: Math.max(a.height, b.height) };
  const recortar = (img) => {
    if (img.width === comun.width && img.height === comun.height) return img;
    const recorte = new PNG(comun);
    PNG.bitblt(img, recorte, 0, 0, comun.width, comun.height, 0, 0);
    return recorte;
  };
  const mapa = new PNG(comun);
  const enComun = pixelmatch(recortar(a).data, recortar(b).data, mapa.data, comun.width, comun.height, { threshold: 0.1 });
  const sobrante = union.width * union.height - comun.width * comun.height;
  const salida = new PNG(union);
  for (let i = 0; i < salida.data.length; i += 4) salida.data.set([255, 0, 0, 255], i); // sobrante en rojo
  PNG.bitblt(mapa, salida, 0, 0, comun.width, comun.height, 0, 0);
  fs.writeFileSync(path.join(OUT, 'diferencias', `${nombre}__diff.png`), PNG.sync.write(salida));
  const distintos = enComun + sobrante;
  return {
    pct: Number(((distintos / (union.width * union.height)) * 100).toFixed(4)),
    px: distintos,
    pctAreaComun: Number(((enComun / (comun.width * comun.height)) * 100).toFixed(4)),
    pandora: [a.width, a.height],
    command: [b.width, b.height],
  };
}

/** Un color de borde solo cuenta si ese borde se pinta en alguno de los dos lados. */
function propiedadVisible(propiedad, pandora, command) {
  const borde = propiedad.match(/^border-(top|bottom)-color$/);
  if (!borde) return true;
  const ancho = `border-${borde[1]}-width`;
  return pandora[ancho] !== '0px' || command[ancho] !== '0px';
}

async function leerEstilos(page, selector) {
  return page.evaluate(
    ([sel, propiedades]) => {
      const el = [...document.querySelectorAll(sel)].find((nodo) => nodo.getClientRects().length > 0);
      if (!el) return null;
      const estilo = getComputedStyle(el);
      return Object.fromEntries(propiedades.map((p) => [p, estilo.getPropertyValue(p)]));
    },
    [selector, PROPIEDADES],
  );
}

// ------------------------------------------------------------------ ejecución

const resultados = [];

for (const escena of ESCENAS) {
  for (const viewport of Object.keys(VIEWPORTS)) {
    for (const modo of MODOS) {
      const base = `${escena.id}__${viewport}__${modo}`;
      if (ONLY && !ONLY.test(base)) continue;
      const descartada = escena.noAplica?.[viewport]
        ? { estado: 'no aplica', motivo: escena.noAplica[viewport] }
        : escena.sinReferencia?.[modo]
          ? { estado: 'sin referencia', motivo: escena.sinReferencia[modo] }
          : null;
      if (descartada) {
        resultados.push({ escena: escena.id, titulo: escena.titulo, viewport, modo, ...descartada });
        continue;
      }
      const regionesTomadas = {};
      const estilos = {};
      const fuentes = {};
      let fallo = null;

      for (const lado of LADOS) {
        const { context, page } = await abrir(lado, viewport, modo, escena.opciones);
        const capturarRegion = async (region, selector) => {
          const destino = page.locator(selector).first();
          if (!(await destino.count()) || !(await destino.isVisible())) return;
          await destino.screenshot({ path: rutaCaptura(`${base}__${region}__${lado}`) });
          (regionesTomadas[region] ??= []).push(lado);
        };
        try {
          await escena.pasos(page, lado, modo, viewport, capturarRegion);
          await asentar(page);
          fuentes[lado] = await page.evaluate(() => document.fonts.check('14px Inter'));
          await page.screenshot({ path: rutaCaptura(`${base}__${lado}`), fullPage: true });
          for (const [region, selectores] of Object.entries(escena.regiones)) {
            await capturarRegion(region, selectores[lado]);
          }
          for (const selectores of escena.estilos) {
            (estilos[selectores.pandora] ??= {})[lado] = await leerEstilos(page, selectores[lado]);
          }
        } catch (error) {
          fallo = `${lado}: ${String(error).split('\n')[0]}`;
          await page.screenshot({ path: rutaCaptura(`${base}__${lado}__fallo`) }).catch(() => {});
        } finally {
          await context.close();
        }
        if (fallo) break;
      }

      const fila = { escena: escena.id, titulo: escena.titulo, viewport, modo };
      if (fallo) {
        resultados.push({ ...fila, estado: 'sin referencia', motivo: fallo });
        console.log(`${base}: FALLO ${fallo}`);
        continue;
      }
      fila.estado = 'comparada en vivo';
      fila.fuenteInter = fuentes;
      fila.pagina = comparar(base);
      fila.regiones = {};
      for (const [region, lados] of Object.entries(regionesTomadas)) {
        fila.regiones[region] =
          lados.length === LADOS.length ? comparar(`${base}__${region}`) : { soloEn: lados[0] };
      }
      fila.estilos = {};
      for (const [selector, porLado] of Object.entries(estilos)) {
        if (!porLado.pandora && !porLado.command) continue;
        if (!porLado.pandora || !porLado.command) {
          fila.estilos[selector] = { soloEn: porLado.pandora ? 'pandora' : 'command' };
          continue;
        }
        const distintas = PROPIEDADES.filter(
          (p) => porLado.pandora[p] !== porLado.command[p] && propiedadVisible(p, porLado.pandora, porLado.command),
        );
        fila.estilos[selector] = Object.fromEntries(distintas.map((p) => [p, [porLado.pandora[p], porLado.command[p]]]));
      }
      resultados.push(fila);
      const regiones = Object.entries(fila.regiones)
        .map(([region, r]) => `${region} ${r.pct ?? `solo ${r.soloEn}`}`)
        .join(' · ');
      console.log(`${base}: página ${fila.pagina.pct} % · ${regiones}`);
    }
  }
}

await browser.close();

const informe = {
  generado: new Date().toISOString(),
  umbralPixelmatch: 0.1,
  origenes: ORIGEN,
  incidencias: Object.fromEntries(Object.entries(incidencias).map(([clave, valores]) => [clave, [...valores].sort()])),
  resultados,
};
fs.writeFileSync(path.join(OUT, 'resultados.json'), JSON.stringify(informe, null, 2));
console.log(JSON.stringify(informe.incidencias, null, 2));
