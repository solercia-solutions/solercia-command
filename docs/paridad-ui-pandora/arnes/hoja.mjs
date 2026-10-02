// Une PANDORA | Command | diferencia en una sola imagen, para el conjunto reducido del repo.
// Uso: DEPS=<carpeta con node_modules> OUT=<salida del arnés> node hoja.mjs <captura> <destino.png> [alto] [h|v]
//   <captura> es el nombre sin lado ni extensión, p. ej. `shell__d1440__claro__sidebar`.
//   [alto] recorta cada parte a ese alto en píxeles; [h|v] las pone lado a lado o apiladas.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const { DEPS, OUT } = process.env;
if (!DEPS || !OUT) throw new Error('Faltan DEPS u OUT.');
const { PNG } = (await import(pathToFileURL(path.join(DEPS, 'node_modules/pngjs/lib/png.js')).href)).default;
const [captura, destino, altoMaximo = '900', sentido = 'h'] = process.argv.slice(2);

const leer = (carpeta, sufijo) => PNG.sync.read(fs.readFileSync(path.join(OUT, carpeta, `${captura}__${sufijo}.png`)));
const partes = [leer('capturas', 'pandora'), leer('capturas', 'command'), leer('diferencias', 'diff')];
const alto = (img) => Math.min(Number(altoMaximo), img.height);
const horizontal = sentido === 'h';
const SEPARADOR = 8;
const width = horizontal
  ? partes.reduce((suma, p) => suma + p.width + SEPARADOR, -SEPARADOR)
  : Math.max(...partes.map((p) => p.width));
const height = horizontal
  ? Math.max(...partes.map(alto))
  : partes.reduce((suma, p) => suma + alto(p) + SEPARADOR, -SEPARADOR);

const hoja = new PNG({ width, height });
for (let i = 0; i < hoja.data.length; i += 4) hoja.data.set([120, 120, 120, 255], i); // separador gris
let posicion = 0;
for (const parte of partes) {
  PNG.bitblt(parte, hoja, 0, 0, parte.width, alto(parte), horizontal ? posicion : 0, horizontal ? 0 : posicion);
  posicion += (horizontal ? parte.width : alto(parte)) + SEPARADOR;
}
fs.mkdirSync(path.dirname(destino), { recursive: true });
fs.writeFileSync(destino, PNG.sync.write(hoja, { deflateLevel: 9 }));
console.log(`${destino} ${width}x${height}`);
