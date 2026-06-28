.PHONY: up down logs ps

# Build and start all services in the foreground.
up:
	docker compose up --build

# Stop and remove all containers.
down:
	docker compose down

# Tail logs from all services.
logs:
	docker compose logs -f

# Show the status of all services.
ps:
	docker compose ps
