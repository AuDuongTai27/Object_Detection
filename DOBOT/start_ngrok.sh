#!/usr/bin/env bash
# Script 1-click chạy Dobot Live Server + ngrok với domain cố định

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

DOMAIN="rebuild-thinner-spur.ngrok-free.dev"

# 1. Khởi động Dobot Live Server nếu chưa chạy
if ! lsof -i :8080 >/dev/null 2>&1 && ! ss -tlpn | grep -q ":8080"; then
    echo "[+] Đang khởi động Dobot Live Server (port 8080)..."
    python3 "$DIR/dobot_live_server.py" > "$DIR/server_local.log" 2>&1 &
    SERVER_PID=$!
    sleep 2
else
    echo "[+] Dobot Live Server đã đang hoạt động trên port 8080."
fi

cleanup() {
    echo -e "\n[!] Đang đóng ngrok..."
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "========================================================================"
echo "  🎉 ĐƯỜNG HẦM CỐ ĐỊNH ĐÃ SẴN SÀNG!"
echo ""
echo "  👉 Link điều khiển từ xa duy nhất & cố định vĩnh viễn:"
echo "     https://$DOMAIN"
echo ""
echo "  💡 Bạn chỉ cần lưu link này vào điện thoại để điều khiển bất cứ lúc nào!"
echo "========================================================================"

ngrok http --domain="$DOMAIN" 8080
