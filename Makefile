# Makefile — punto de entrada de Solercia Command.
#
# El flujo real de desarrollo lo resuelve ./gestion.sh (backend y datos en Docker,
# front con ng serve en el host para tener recarga en caliente). Este Makefile es
# la fachada estable sobre ese script, más los objetivos de calidad del frontend.
#
# Puertos, elegidos para no pisarse con los otros productos de Solercia:
#
#   Solercia Command   front 4242   ·  API 8081  ·  Postgres 5434   ·  Redis 6380
#   solercia_flows     front 4200   ·  API 3000  ·  IA   8000       ·  Postgres 5433
#   solercia_security  web   14200  ·  API 18000 ·  Postgres 15432  ·  test-pg 5432
#
# Uso rápido:  make on   →  abre http://localhost:4242   →  make off

SHELL := /bin/bash
ROOT_DIR := $(shell cd "$(dir $(lastword $(MAKEFILE_LIST)))" && pwd)
FRONT_DIR := $(ROOT_DIR)/frontend
GESTION := $(ROOT_DIR)/gestion.sh
FRONT_PORT := 4242
API_PORT := 8081

.DEFAULT_GOAL := help

.PHONY: help on off status restart front tunel rebuild logs logs-front logs-backend \
        install build lint test verify up down ps

## ── Ciclo de vida (delegado en gestion.sh) ──────────────────────────────────

help: ## Muestra esta ayuda
	@echo ""
	@echo "  Solercia Command — objetivos disponibles"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Front: http://localhost:$(FRONT_PORT)   ·   API: http://localhost:$(API_PORT)/docs"
	@echo ""

on: ## Enciende todo: Docker (postgres, redis, backend) + front + túnel
	@"$(GESTION)" on

off: ## Apaga todo (los volúmenes de base de datos se conservan)
	@"$(GESTION)" off

status: ## Estado de cada pieza con sus URLs
	@"$(GESTION)" status

restart: ## Apaga y vuelve a encender
	@"$(GESTION)" restart

front: ## Enciende solo el front (ng serve en el host)
	@"$(GESTION)" front

tunel: ## Enciende solo el túnel público (devtunnel)
	@"$(GESTION)" tunel

rebuild: ## Reconstruye la imagen del backend con el código actual
	@"$(GESTION)" rebuild

logs: logs-front ## Alias de logs-front

logs-front: ## Sigue los logs del front
	@"$(GESTION)" logs front

logs-backend: ## Sigue los logs del backend
	@"$(GESTION)" logs backend

## ── Calidad del frontend ────────────────────────────────────────────────────

install: ## Instala las dependencias del frontend
	@cd "$(FRONT_DIR)" && npm ci

build: ## Compila el frontend en modo producción
	@cd "$(FRONT_DIR)" && npm run build

lint: ## Pasa ESLint sobre el frontend
	@cd "$(FRONT_DIR)" && npm run lint

test: ## Ejecuta las pruebas del frontend (si el proyecto las tiene configuradas)
	@cd "$(FRONT_DIR)" && \
	if node -e "process.exit(require('./package.json').scripts.test ? 0 : 1)"; then \
		npm test; \
	else \
		echo "  [test] El frontend todavía no define un script de pruebas; nada que ejecutar."; \
	fi

verify: lint test build ## Puerta de calidad completa: lint + pruebas + build

## ── Docker directo (sin gestion.sh) ─────────────────────────────────────────

up: ## Levanta todos los servicios del compose en primer plano
	@docker compose up --build

down: ## Detiene y elimina los contenedores
	@docker compose down

ps: ## Estado de los contenedores
	@docker compose ps
