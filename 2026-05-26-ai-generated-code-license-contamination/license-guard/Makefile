.PHONY: up down seed demo test build-cli install-cli logs reset

# Start all services
up:
	docker compose up -d --build
	@echo ""
	@echo "✅ LicenseGuard is running!"
	@echo "   Dashboard:  http://localhost:3000"
	@echo "   API Docs:   http://localhost:8000/docs"
	@echo "   Job Queue:  http://localhost:9181"
	@echo ""
	@echo "Waiting for services to start (this may take a minute on first run)..."
	@sleep 10
	@docker compose logs backend --tail=20

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

# Reset database and restart
reset:
	docker compose down -v
	docker compose up -d --build

# Quick scan demo via CLI (requires running services and built CLI)
scan-demo:
	@echo "Running quick scan demo..."
	@echo 'def heappush(heap, item):\n    heap.append(item)\n    _siftdown(heap, 0, len(heap)-1)' | \
		./cli/bin/licenseguard scan --stdin --language python || true

# Check API health
health:
	curl -s http://localhost:8000/api/v1/health | python3 -m json.tool