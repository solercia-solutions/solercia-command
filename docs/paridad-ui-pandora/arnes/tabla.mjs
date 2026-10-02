// Imprime la tabla Markdown del README a partir de resultados.json.
// Uso: node tabla.mjs <ruta a resultados.json>
import fs from 'node:fs';

const { resultados } = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const pct = (valor) => `${valor.toFixed(2).replace('.', ',')} %`;
const ETIQUETAS = { dialogo: 'diálogo', 'menu-inferior': 'menú inferior' };
const region = ([clave, r]) => {
  const nombre = ETIQUETAS[clave] ?? clave;
  if (r.soloEn) return `${nombre}: solo en ${r.soloEn}`;
  const tamano = String(r.pandora) === String(r.command) ? '' : ` (común ${pct(r.pctAreaComun)}; ${r.pandora.join('×')} / ${r.command.join('×')})`;
  return `${nombre} ${pct(r.pct)}${tamano}`;
};

console.log('| Escena | Viewport | Modo | Estado | Página completa | Por región |');
console.log('|---|---|---|---|---|---|');
for (const f of resultados) {
  const viewport = f.viewport === 'd1440' ? '1440×900' : '390×844';
  if (f.estado !== 'comparada en vivo') {
    console.log(`| ${f.titulo} | ${viewport} | ${f.modo} | ${f.estado} | — | ${f.motivo} |`);
    continue;
  }
  const regiones = Object.entries(f.regiones).map(region).join(' · ');
  console.log(`| ${f.titulo} | ${viewport} | ${f.modo} | ${f.estado} | ${pct(f.pagina.pct)} | ${regiones} |`);
}
