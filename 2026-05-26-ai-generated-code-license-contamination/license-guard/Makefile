.PHONY: up down seed demo test build-cli

# Start all services
up:
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@docker compose exec backend python scripts/seed_corpus.py
	@echo ""
	@echo "✅ LicenseGuard is running!"
	@echo "   Dashboard:  http://localhost:3000"
	@echo "   API Docs:   http://localhost:8000/docs"
	@echo "   Job Queue:  http://localhost:9181"

# Stop all services
down:
	docker compose down

# Seed corpus with FOSS snippets
seed:
	docker compose exec backend python scripts/seed_corpus.py

# Run end-to-end demo
demo:
	docker compose exec backend python scripts/demo.py

# Run backend tests
test:
	docker compose exec backend pytest tests/ -v

# Build CLI binary
build-cli:
	cd cli && go mod tidy && go build -o bin/licenseguard ./cmd/licenseguard/
	@echo "✅ CLI built: cli/bin/licenseguard"

# Install CLI globally
install-cli:
	cd cli && go install ./cmd/licenseguard/

# View logs
logs:
	docker compose logs -f backend worker

# Reset database
reset:
	docker compose down -v
	docker compose up -d