#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

NEO4J_IMAGE="neo4j:5.26"
CONTAINER_NAME="kg-rag-neo4j"
BACKUP_DIR="$PROJECT_DIR/backup"

usage() {
    echo "Usage: $0 {export|import}"
    echo ""
    echo "  export  — 停止 Neo4j → 导出 dump 到 backup/ → 重启"
    echo "  import  — 停止 Neo4j → 从 backup/ 恢复 dump → 重启"
    exit 1
}

ensure_backup_dir() {
    mkdir -p "$BACKUP_DIR"
    chmod a+rwx "$BACKUP_DIR"
}

wait_neo4j_ready() {
    echo "等待 Neo4j 就绪..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if docker exec "$CONTAINER_NAME" neo4j status 2>/dev/null | grep -q "running"; then
            echo "Neo4j 已就绪"
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    echo "警告: Neo4j 未在超时时间内就绪，请手动检查"
}

do_export() {
    ensure_backup_dir
    echo "==> 停止 Neo4j 容器..."
    docker compose stop neo4j 2>/dev/null || true

    echo "==> 导出数据库到 $BACKUP_DIR ..."
    docker run --rm \
        -v "$PROJECT_DIR/.docker/neo4j/data:/data" \
        -v "$BACKUP_DIR:/backup" \
        "$NEO4J_IMAGE" \
        neo4j-admin database dump neo4j --to-path=/backup/ --overwrite-destination

    echo "==> 重启 Neo4j..."
    docker compose up -d neo4j
    wait_neo4j_ready

    echo "==> 导出完成: $BACKUP_DIR/neo4j.dump"
}

do_import() {
    if [ ! -f "$BACKUP_DIR/neo4j.dump" ]; then
        echo "错误: $BACKUP_DIR/neo4j.dump 不存在，请先运行 export"
        exit 1
    fi

    echo "==> 停止 Neo4j 容器..."
    docker compose stop neo4j 2>/dev/null || true

    echo "==> 从 $BACKUP_DIR 恢复数据库..."
    docker run --rm \
        -v "$PROJECT_DIR/.docker/neo4j/data:/data" \
        -v "$BACKUP_DIR:/backup" \
        "$NEO4J_IMAGE" \
        neo4j-admin database load neo4j --from-path=/backup/ --overwrite-destination

    echo "==> 重启 Neo4j..."
    docker compose up -d neo4j
    wait_neo4j_ready

    echo "==> 恢复完成"
}

case "${1:-}" in
    export) do_export ;;
    import) do_import ;;
    *)      usage ;;
esac
