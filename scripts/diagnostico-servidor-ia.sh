#!/usr/bin/env bash
# Diagnóstico de solo lectura de un servidor Linux para estimar si puede correr un modelo de
# lenguaje local (Ollama/llama.cpp) en CPU junto a las aplicaciones que ya aloja.
#
# - No requiere sudo, no instala nada, no modifica archivos ni contenedores.
# - No lee variables de entorno, secretos ni configuraciones de aplicaciones.
# - Por defecto oculta el hostname y las direcciones IP (usar --sin-ocultar para mostrarlas).
#
# Uso:   bash diagnostico-servidor-ia.sh            > diagnostico.txt
#        bash diagnostico-servidor-ia.sh --sin-ocultar > diagnostico.txt
set -u

OCULTAR=1
[ "${1:-}" = "--sin-ocultar" ] && OCULTAR=0

ocultar() {
  if [ "$OCULTAR" -eq 1 ]; then
    sed -E -e "s/$(hostname 2>/dev/null | sed 's/[.[\*^$/]/\\&/g')/<host>/g" \
           -e 's/([0-9]{1,3}\.){3}[0-9]{1,3}/<ip>/g' \
           -e 's/([0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}/<ipv6>/g'
  else
    cat
  fi
}

seccion() { printf '\n===== %s =====\n' "$1"; }
existe() { command -v "$1" >/dev/null 2>&1; }

{
seccion "Fecha y sistema"
date -u '+%Y-%m-%dT%H:%M:%SZ'
uname -srm
[ -r /etc/os-release ] && grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
existe systemd-detect-virt && echo "virtualizacion: $(systemd-detect-virt 2>/dev/null)"
existe uptime && uptime

seccion "CPU"
if existe lscpu; then
  lscpu | grep -E '^(Architecture|CPU\(s\)|On-line CPU|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|Model name|CPU max MHz|CPU MHz|L2 cache|L3 cache|NUMA node\(s\)|Hypervisor vendor|Virtualization type)'
else
  grep -m1 'model name' /proc/cpuinfo; echo "nucleos: $(nproc)"
fi
echo "nproc (disponibles para este usuario): $(nproc)"
echo "Instrucciones relevantes para llama.cpp:"
for f in avx avx2 fma f16c avx512f avx512bw avx512vl avx512_vnni avx_vnni amx_tile sse4_2; do
  if grep -qw "$f" /proc/cpuinfo 2>/dev/null; then echo "  $f: si"; else echo "  $f: no"; fi
done

seccion "Memoria y swap"
existe free && free -h
grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree|HugePages_Total)' /proc/meminfo

seccion "Disco (sistema y Docker)"
df -h / 2>/dev/null
[ -d /var/lib/docker ] && df -h /var/lib/docker 2>/dev/null | tail -1
df -h /home 2>/dev/null | tail -1

seccion "GPU / aceleradores"
if existe nvidia-smi; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv 2>/dev/null
else
  echo "nvidia-smi: no disponible"
fi
existe lspci && lspci 2>/dev/null | grep -iE 'vga|3d|display|nvidia|amd/ati' || echo "lspci: sin GPU detectada o comando no disponible"
[ -e /dev/kfd ] && echo "/dev/kfd presente (ROCm)" || true

seccion "Carga actual (procesos que más CPU y memoria usan)"
ps -eo pid,comm,%cpu,%mem,rss --sort=-%mem 2>/dev/null | head -12
echo "--- promedio de carga y presión"
cat /proc/loadavg
[ -r /proc/pressure/cpu ] && { echo "presion cpu:"; cat /proc/pressure/cpu; }
[ -r /proc/pressure/memory ] && { echo "presion memoria:"; cat /proc/pressure/memory; }

seccion "Limites del entorno (cgroups / contenedor)"
[ -r /sys/fs/cgroup/cpu.max ] && echo "cpu.max: $(cat /sys/fs/cgroup/cpu.max)"
[ -r /sys/fs/cgroup/memory.max ] && echo "memory.max: $(cat /sys/fs/cgroup/memory.max)"
[ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ] && echo "cfs_quota_us: $(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)"
ulimit -a 2>/dev/null | grep -E 'open files|max user processes|virtual memory'

seccion "Docker"
if existe docker; then
  docker version --format 'cliente {{.Client.Version}} / servidor {{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})' 2>&1 | head -2
  docker compose version 2>/dev/null || docker-compose version 2>/dev/null | head -1
  docker info --format 'CPUs={{.NCPU}} Mem={{.MemTotal}} Driver={{.Driver}} Cgroup={{.CgroupVersion}} Runtime={{.DefaultRuntime}}' 2>&1 | head -1
  echo "--- contenedores en ejecucion (nombre, imagen, estado)"
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' 2>&1 | head -40
  echo "--- uso de recursos por contenedor (una muestra)"
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>&1 | head -40
else
  echo "docker: no disponible para este usuario"
fi

seccion "Runtimes de IA ya presentes"
for c in ollama llama-server llama-cli python3 nvidia-container-cli; do
  existe "$c" && echo "$c: $(command -v "$c")" || echo "$c: no"
done
existe ollama && ollama --version 2>/dev/null

seccion "Salida a internet (solo HEAD, para descargar modelos)"
if existe curl; then
  for u in https://registry.ollama.ai https://huggingface.co https://ghcr.io; do
    code=$(curl -s -o /dev/null -I -m 8 -w '%{http_code}' "$u" 2>/dev/null || echo "sin_conexion")
    echo "$u -> $code"
  done
else
  echo "curl: no disponible"
fi

seccion "Puertos en escucha (solo numeros, para elegir uno libre)"
if existe ss; then
  ss -ltnH 2>/dev/null | awk '{print $4}' | sed -E 's/.*:([0-9]+)$/\1/' | sort -n | uniq | tr '\n' ' '; echo
fi

seccion "Fin"
echo "Diagnostico completo. Revisa el archivo antes de compartirlo."
} 2>&1 | ocultar
