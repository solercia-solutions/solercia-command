// Ruido de captura: compara las mismas capturas de dos corridas del arnés, lado por lado.
// Uso: DEPS=<carpeta con node_modules> A=<salida 1> B=<salida 2> node ruido.mjs
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const { DEPS, A, B } = process.env;
if (!DEPS || !A || !B) throw new Error('Faltan DEPS, A o B.');
const dep = (nombre, entrada) => import(pathToFileURL(path.join(DEPS, 'node_modules', nombre, entrada)).href);
const { PNG } = (await dep('pngjs', 'lib/png.js')).default;
const pixelmatch = (await dep('pixelmatch', 'index.js')).default;

const filas = [];
for (const archivo of fs.readdirSync(path.join(A, 'capturas')).sort()) {
  const otro = path.join(B, 'capturas', archivo);
  if (!archivo.endsWith('.png') || archivo.includes('__fallo') || !fs.existsSync(otro)) continue;
  const a = PNG.sync.read(fs.readFileSync(path.join(A, 'capturas', archivo)));
  const b = PNG.sync.read(fs.readFileSync(otro));
  const mismoTamano = a.width === b.width && a.height === b.height;
  const distintos = mismoTamano ? pixelmatch(a.data, b.data, null, a.width, a.height, { threshold: 0.1 }) : null;
  filas.push({
    captura: archivo.replace(/\.png$/, ''),
    lado: archivo.includes('__pandora') ? 'pandora' : 'command',
    pct: mismoTamano ? Number(((distintos / (a.width * a.height)) * 100).toFixed(4)) : null,
    tamanos: mismoTamano ? undefined : [`${a.width}x${a.height}`, `${b.width}x${b.height}`],
  });
}

const resumen = {};
for (const lado of ['pandora', 'command']) {
  const propias = filas.filter((f) => f.lado === lado);
  const medidas = propias.filter((f) => f.pct !== null);
  resumen[lado] = {
    capturas: propias.length,
    identicas: medidas.filter((f) => f.pct === 0).length,
    maximoPct: Math.max(0, ...medidas.map((f) => f.pct)),
    cambiaronDeTamano: propias.filter((f) => f.pct === null).map((f) => `${f.captura} ${f.tamanos.join(' → ')}`),
    conRuido: medidas.filter((f) => f.pct > 0).map((f) => `${f.captura} ${f.pct} %`),
  };
}
console.log(JSON.stringify(resumen, null, 2));
if (process.env.OUT) fs.writeFileSync(path.join(process.env.OUT, 'ruido.json'), JSON.stringify(resumen, null, 2));
