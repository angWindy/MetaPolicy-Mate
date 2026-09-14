#!/bin/bash
# p234-server.sh — Convenience script to manage PolicyMeta AI demo deployment.
# Use on the server: bash p234-server.sh [up|down|restart|status|logs|rebuild]
set -euo pipefail

COMPOSE_FILE="docker-compose.server.yml"
PROJECT_DIR="$HOME/p234"

cmd="${1:-status}"

case "$cmd" in
    up)
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" up -d
        ;;
    down)
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" down
        ;;
    restart)
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" restart
        ;;
    status)
        cd "$PROJECT_DIR"
        echo "=== Containers ==="
        docker compose -f "$COMPOSE_FILE" ps
        echo ""
        echo "=== Health checks ==="
        echo -n "Backend  (8000): "; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/health
        echo -n "Frontend (3000): "; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3000/
        echo -n "Qdrant   (6333): "; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:6333/
        echo -n "Redis    (6379): "; docker exec rag-redis redis-cli ping 2>/dev/null || echo "DOWN"
        ;;
    logs)
        cd "$PROJECT_DIR"
        service="${2:-}"
        if [[ -n "$service" ]]; then
            docker compose -f "$COMPOSE_FILE" logs -f --tail=100 "$service"
        else
            docker compose -f "$COMPOSE_FILE" logs -f --tail=100
        fi
        ;;
    rebuild)
        cd "$PROJECT_DIR"
        service="${2:-}"
        if [[ -n "$service" ]]; then
            docker compose -f "$COMPOSE_FILE" build "$service"
            docker compose -f "$COMPOSE_FILE" up -d "$service"
        else
            docker compose -f "$COMPOSE_FILE" build
            docker compose -f "$COMPOSE_FILE" up -d
        fi
        ;;
    clean)
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" down
        docker image prune -af
        docker builder prune -af
        ;;
    *)
        echo "Usage: $0 {up|down|restart|status|logs [service]|rebuild [service]|clean}"
        exit 1
        ;;
esac