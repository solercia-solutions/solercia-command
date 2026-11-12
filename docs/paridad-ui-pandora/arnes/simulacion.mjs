// Respuestas sintéticas equivalentes para los dos frontends. Ninguna petición de API llega a un
// backend: `capture.mjs` las intercepta en el navegador y las resuelve con estas funciones.
//
// Los datos neutros viven en `datos/sintetico.json`; aquí solo se traducen al contrato de cada lado.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const DATOS = JSON.parse(fs.readFileSync(path.join(HERE, 'datos', 'sintetico.json'), 'utf8'));

const json = (body, status = 200) => ({
  status,
  contentType: 'application/json',
  body: JSON.stringify(body),
});
const vacio = () => ({ status: 204, body: '' });
const HTML_EN_BLANCO = {
  status: 200,
  contentType: 'text/html',
  body: '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Sintético</title></head><body></body></html>',
};

/** Tema de comparación (`idartes.json` de PANDORA) con el color primario opcionalmente cambiado. */
function temaCon(temaBase, primario) {
  const tema = structuredClone(temaBase);
  if (primario) tema.modes.light.semantic.color.primary = primario;
  return tema;
}

/** Estado del tema por contexto de navegador: el tema vigente y su historial de solo inserción. */
function crearEstadoTema(temaBase) {
  const nombre = `${DATOS.persona.nombres} ${DATOS.persona.apellidos}`;
  const versiones = DATOS.versiones.map((v) => ({ ...v, usuario: nombre, tema: temaCon(temaBase, v.primario) }));
  return {
    vigente: structuredClone(temaBase),
    versiones,
    aplicar(tema, origen) {
      const id = Math.max(...this.versiones.map((v) => v.id)) + 1;
      this.vigente = tema;
      const version = { id, fecha: DATOS.instante, capturaInicial: false, origen, usuario: nombre, tema };
      this.versiones.unshift(version);
      return version;
    },
    pagina(antes) {
      const lista = antes ? this.versiones.filter((v) => v.id < antes) : this.versiones;
      const corte = lista.slice(0, 20);
      return { corte, siguiente: lista.length > 20 ? corte.at(-1).id : null };
    },
  };
}

// ---------------------------------------------------------------- PANDORA

function actividadPandora(nodo, padre) {
  return {
    i_pk_id: nodo.id,
    title: nodo.etiqueta,
    description: '',
    url: nodo.hijos ? '#' : nodo.urlPandora,
    icon: nodo.iconoPandora,
    access: true,
    i_fk_id_modulo: DATOS.modulo.id,
    i_fk_id_padre: padre,
    submenu: (nodo.hijos ?? []).map((hijo) => actividadPandora(hijo, nodo.id)),
  };
}

function usuarioPandora(u) {
  const dependencia = DATOS.dependencias.find((d) => d.id === u.dependencia);
  const [primerApellido, ...resto] = u.apellidos.split(' ');
  return {
    id: u.id,
    vc_estado: u.activo ? 1 : 0,
    area: { i_pk_id: dependencia.id, vc_parametro_detalle: dependencia.nombre },
    i_fk_tipo_documento: 1,
    i_cedula: u.documento,
    name: u.nombres,
    vc_segundo_nombre: null,
    vc_primer_apellido: primerApellido,
    vc_segundo_apellido: resto.join(' ') || null,
    full_name: `${u.nombres} ${u.apellidos}`,
    dt_fecha_nacimiento: u.nacimiento,
    email: u.correo,
    vc_telefono: u.telefono,
    i_fk_area: dependencia.id,
    i_fk_ciudad: 1,
    i_fk_genero: 1,
  };
}

const versionPandora = (v) => ({
  id: v.id,
  usuario: v.usuario,
  usuario_id: DATOS.persona.id,
  fecha: v.fecha,
  captura_inicial: v.capturaInicial,
  version_origen: v.origen,
});

/**
 * Devuelve la función que resuelve una petición del shell de PANDORA, o `null` si la ruta no está
 * simulada (el arnés la registra y responde 404).
 */
export function simuladorPandora({ temaBase, origen }) {
  const estado = crearEstadoTema(temaBase);
  const { persona, organizacion, modulo } = DATOS;
  const ahora = Math.floor(new Date(DATOS.instante).getTime() / 1000);
  const [primerApellido, ...restoApellidos] = persona.apellidos.split(' ');

  return (metodo, url, cuerpo) => {
    const ruta = url.pathname;
    if (ruta === '/assets/entities/idartes.json') {
      return json({
        entidad: 'idartes',
        nombreCorto: organizacion.nombreCorto,
        nombreCompleto: organizacion.nombre,
        hostnames: ['localhost'],
        legacyAdminOrigin: origen,
        logoUrl: 'assets/entities/idartes-logo-placeholder.svg',
        faviconUrl: 'assets/entities/idartes-favicon-placeholder.svg',
        colores: { primario: '#1a5276', primarioOscuro: '#154360', secundario: '#4ecdc4', acento: '#f4d03f' },
        keycloakHabilitado: false,
        authModeSugerido: 'local',
        pieDePagina: { texto: organizacion.nombre, urlSoporte: '' },
      });
    }
    if (ruta.startsWith('/__legado')) return HTML_EN_BLANCO;
    if (ruta === '/auth/me') {
      return json({
        sub: persona.correo,
        uid: String(persona.id),
        nombre: `${persona.nombres} ${persona.apellidos}`,
        ent: 'idartes',
        amr: ['pwd'],
        auth_method: 'local',
        auth_time: ahora,
        expires_at: ahora + 8 * 3600,
        modulos: [modulo.id],
        menu: [
          {
            i_pk_id: modulo.id,
            vc_modulo: `Módulo ${modulo.nombre}`,
            vc_redireccion: `${origen}/__legado/`,
            vc_imagen: modulo.iconoPandora,
            tx_descripcion: 'Módulo sintético del arnés de paridad',
            i_estado: 1,
            actividades: DATOS.menu.map((nodo) => actividadPandora(nodo, null)),
          },
        ],
      });
    }
    if (ruta === '/auth/config') return json({ mode: 'local', methods: ['password'], idle_minutes: 30 });
    if (ruta === '/auth/touch') return json({ expires_at: ahora + 8 * 3600 });
    if (ruta === '/bridge') return json({ action: `${origen}/__legado/entrada`, token: 'sintetico' });

    const api = ruta.replace(/^\/api\/admin\/v1/, '');
    if (api === ruta) return null;
    if (api === '/entidad/tema' && metodo === 'GET') return json({ data: { tema: estado.vigente }, message: 'ok' });
    if (api === '/entidad/tema' && metodo === 'PUT') {
      const { tema, version_origen: versionOrigen } = JSON.parse(cuerpo ?? '{}');
      estado.aplicar(tema, versionOrigen ?? null);
      return json({ data: { tema }, message: 'ok' });
    }
    if (api === '/entidad/tema/versiones') {
      const { corte, siguiente } = estado.pagina(Number(url.searchParams.get('antes')) || null);
      return json({ data: { versiones: corte.map(versionPandora), siguiente }, message: 'ok' });
    }
    const version = api.match(/^\/entidad\/tema\/versiones\/(\d+)$/);
    if (version) {
      const encontrada = estado.versiones.find((v) => v.id === Number(version[1]));
      return encontrada
        ? json({ data: { ...versionPandora(encontrada), tema: encontrada.tema }, message: 'ok' })
        : json({ message: 'No encontrada' }, 404);
    }
    if (api === '/entidad/principal') {
      return json({
        data: {
          i_pk_id: 1,
          vc_nombre: organizacion.nombre,
          vc_acronimo: organizacion.nombreCorto,
          vc_codigo: '000',
          vc_codigo_bogdata: '000',
          vc_nombre_responsable: '',
          vc_telefono_responsable: '',
          vc_correo_responsable: '',
          i_principal: 1,
          i_cabeza_sector: 0,
        },
        ambiente: null,
        message: 'ok',
      });
    }
    if (api === '/telemetria/configuracion') {
      return json({
        data: {
          capturaMenu: false,
          capturaInterna: false,
          capturaMigas: false,
          avisoPrivacidad: null,
          medicionTerceros: { activa: false, medicion: null, contenedor: null },
          capturaPermanencia: false,
          segundosInactividad: null,
        },
        message: 'ok',
      });
    }
    if (api.startsWith('/telemetria/')) return vacio();
    if (api === '/ayuda/mapa') {
      return json({
        data: {
          configuracion: {
            botonActivo: false,
            asistenteActivo: false,
            ocultaAyudaLegacy: false,
            maxCoincidenciasSelector: 0,
            urlSoporte: null,
            maxCaracteresMensaje: 0,
          },
          opciones: [],
          selectoresLegacy: [],
        },
        message: 'ok',
      });
    }
    if (api === `/usuario/${persona.id}/perfil`) {
      return json({
        data: {
          id: persona.id,
          i_fk_tipo_documento: 1,
          i_cedula: '1000000007',
          name: persona.nombres,
          vc_segundo_nombre: null,
          vc_primer_apellido: primerApellido,
          vc_segundo_apellido: restoApellidos.join(' ') || null,
          email: persona.correo,
          vc_telefono: null,
          vc_celular: null,
          vc_direccion: null,
          dt_fecha_nacimiento: null,
          tiene_password: true,
        },
        message: 'ok',
      });
    }
    const parametros = api.match(/^\/parametros\/(\d+)\/list$/);
    if (parametros) {
      const grupo = Number(parametros[1]);
      const lista =
        grupo === 6
          ? Object.fromEntries(DATOS.dependencias.map((d) => [String(d.id), d.nombre]))
          : { 1: 'Opción uno', 2: 'Opción dos' };
      return json({ data: lista, message: 'ok' });
    }
    if (api === '/usuarios' && metodo === 'GET') {
      return json({ data: DATOS.usuarios.map(usuarioPandora), message: 'ok' });
    }
    return null;
  };
}

// ---------------------------------------------------------------- Solercia Command

function nodoCommand(nodo, orden) {
  return {
    id: `menu-${nodo.id}`,
    name: nodo.etiqueta,
    icon: nodo.iconoCommand,
    path: nodo.hijos ? null : nodo.rutaCommand,
    order: orden,
    children: (nodo.hijos ?? []).map(nodoCommand),
  };
}

const uuidDe = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

function usuarioCommand(u) {
  const [primerApellido, ...resto] = u.apellidos.split(' ');
  return {
    id: uuidDe(u.id),
    email: u.correo,
    primer_nombre: u.nombres,
    segundo_nombre: null,
    primer_apellido: primerApellido,
    segundo_apellido: resto.join(' ') || null,
    full_name: `${u.nombres} ${u.apellidos}`,
    dependency_id: uuidDe(u.dependencia),
    is_active: u.activo,
    organization_id: DATOS.organizacion.uuid,
    roles: [{ id: uuidDe(900), code: 'ADMIN', name: DATOS.persona.insignia }],
  };
}

const versionCommand = (v) => ({
  id: v.id,
  user_name: v.usuario,
  user_id: DATOS.persona.uuid,
  applied_at: v.fecha,
  initial_capture: v.capturaInicial,
  source_version_id: v.origen,
});

/**
 * Devuelve la función que resuelve una petición de Solercia Command. Con `menuEnvuelto` el árbol
 * cuelga de un nodo raíz con el nombre del módulo: en PANDORA el primer tramo de las migas es el
 * módulo (selector de módulos, fuera del alcance del porte), así que la escena de migas necesita
 * ese nivel para comparar el mismo camino.
 */
export function simuladorCommand({ temaBase, menuEnvuelto = false }) {
  const estado = crearEstadoTema(temaBase);
  const { persona, organizacion, modulo } = DATOS;
  const [primerApellido, ...restoApellidos] = persona.apellidos.split(' ');
  const rol = { id: uuidDe(900), code: 'ADMIN', name: persona.insignia };
  const arbol = DATOS.menu.map(nodoCommand);
  const menus = menuEnvuelto
    ? [{ id: 'menu-modulo', name: modulo.nombre, icon: modulo.iconoCommand, path: null, order: 0, children: arbol }]
    : arbol;

  return (metodo, url, cuerpo) => {
    const api = url.pathname.replace(/^\/api\/v1/, '');
    if (api === url.pathname) return null;
    if (api === '/auth/me') {
      return json({
        id: persona.uuid,
        email: persona.correo,
        full_name: `${persona.nombres} ${persona.apellidos}`,
        primer_nombre: persona.nombres,
        segundo_nombre: null,
        primer_apellido: primerApellido,
        segundo_apellido: restoApellidos.join(' ') || null,
        is_active: true,
        organization_id: organizacion.uuid,
        roles: [rol],
      });
    }
    if (api === '/auth/me/menus') return json({ data: menus });
    if (api === '/notifications/unread-count') return json({ data: { count: 0 } });
    if (api === '/organizations/mine') {
      return json({
        data: [
          {
            organization: {
              id: organizacion.uuid,
              name: organizacion.nombre,
              slug: organizacion.slug,
              is_active: true,
              created_at: DATOS.instante,
            },
            role: 'admin',
          },
        ],
      });
    }
    if (api === '/organizations/me/theme' && metodo === 'GET') return json({ data: estado.vigente });
    if (api === '/organizations/me/theme' && metodo === 'PUT') {
      const tema = JSON.parse(cuerpo ?? '{}');
      const origen = Number(url.searchParams.get('source_version_id')) || null;
      const version = estado.aplicar(tema, origen);
      return json({ data: tema, message: 'ok', meta: { version: versionCommand(version) } });
    }
    if (api === '/organizations/me/theme/versions') {
      const { corte, siguiente } = estado.pagina(Number(url.searchParams.get('before')) || null);
      return json({ data: { versions: corte.map(versionCommand), next: siguiente } });
    }
    const version = api.match(/^\/organizations\/me\/theme\/versions\/(\d+)$/);
    if (version) {
      const encontrada = estado.versiones.find((v) => v.id === Number(version[1]));
      return encontrada
        ? json({ data: { ...versionCommand(encontrada), theme: encontrada.tema } })
        : json({ detail: 'No encontrada' }, 404);
    }
    if (api === '/admin/users' && metodo === 'GET') {
      return json({ data: DATOS.usuarios.map(usuarioCommand), meta: { total: DATOS.usuarios.length } });
    }
    if (api === '/admin/dependencies') {
      return json({
        data: DATOS.dependencias.map((d) => ({
          id: uuidDe(d.id),
          organization_id: organizacion.uuid,
          name: d.nombre,
          code: null,
          is_active: true,
        })),
        meta: { total: DATOS.dependencias.length },
      });
    }
    if (api === '/admin/roles') {
      return json({
        data: [{ ...rol, organization_id: organizacion.uuid, is_active: true }],
        meta: { total: 1 },
      });
    }
    return null;
  };
}

/** Estado inicial del navegador de Command: sesión y organización activa sintéticas. */
export function sesionCommand() {
  return { 'sp-token': 'token-sintetico-del-arnes', 'sp-active-org': DATOS.organizacion.uuid };
}
