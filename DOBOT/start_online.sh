#!/usr/bin/env bash
# Script mở đường hầm Cloudflare Tunnel điều khiển Dobot Magician từ xa qua Internet

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "========================================================================"
echo "   🤖 DOBOT MAGICIAN 3D - KHỞI TẠO ĐIỀU KHIỂN TỪ XA QUA INTERNET"
echo "========================================================================"

# 1. Kiểm tra binary cloudflared
if [ ! -f "$DIR/cloudflared" ]; then
    echo "[*] Đang tải công cụ Cloudflare Tunnel (cloudflared)..."
    curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o "$DIR/cloudflared"
    chmod +x "$DIR/cloudflared"
fi

# 2. Khởi động server nội bộ nếu chưa chạy
PORT=8080
if lsof -i :8081 >/dev/null 2>&1 || ss -tlpn | grep -q ":8081"; then
    PORT=8081
    echo "[+] Dobot Live Server đã đang chạy trên port 8081."
elif lsof -i :8080 >/dev/null 2>&1 || ss -tlpn | grep -q ":8080"; then
    PORT=8080
    echo "[+] Dobot Live Server đã đang chạy trên port 8080."
else
    echo "[+] Khởi động Dobot Live Server (port 8080)..."
    python3 "$DIR/dobot_live_server.py" > "$DIR/server_local.log" 2>&1 &
    SERVER_PID=$!
    sleep 2
    if lsof -i :8081 >/dev/null 2>&1 || ss -tlpn | grep -q ":8081"; then
        PORT=8081
    fi
fi

# 3. Chạy Cloudflare Tunnel và lọc lấy URL
echo "[*] Đang kết nối mạng đám mây Cloudflare tới port $PORT..."
LOG_FILE="$DIR/tunnel.log"
rm -f "$LOG_FILE"

"$DIR/cloudflared" tunnel --url "http://localhost:$PORT" > "$LOG_FILE" 2>&1 &
TUNNEL_PID=$!

cleanup() {
    echo -e "\n[!] Đang đóng đường hầm Cloudflare..."
    kill "$TUNNEL_PID" 2>/dev/null
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

# Đợi lấy link URL trycloudflare.com
FOUND_URL=""
for i in {1..20}; do
    sleep 0.5
    if [ -f "$LOG_FILE" ]; then
        FOUND_URL=$(grep -o 'https://[-a-zA-Z0-9]*\.trycloudflare\.com' "$LOG_FILE" | head -n 1)
        if [ -n "$FOUND_URL" ]; then
            break
        fi
    fi
done

if [ -n "$FOUND_URL" ]; then
    echo ""
    echo "========================================================================"
    echo "  🎉 ĐƯỜNG HẦM ONLINE ĐÃ SẴN SÀNG!"
    echo ""
    echo "  👉 Link điều khiển từ xa (Mở trên điện thoại, 4G, bất kỳ đâu):"
    echo "     $FOUND_URL"
    echo ""
    echo "  💡 Bạn có thể gửi link này vào Zalo / mở trên iPhone/Android để điều"
    echo "     khiển cánh tay Dobot đang cắm ở nhà theo thời gian thực!"
    echo "========================================================================"
    echo "  (Bấm phím Ctrl + C trên cửa sổ này nếu muốn dừng chia sẻ)"
    echo "========================================================================"
else
    echo "[-] Chưa lấy được link tự động. Bạn xem log tại: $LOG_FILE"
fi

wait "$TUNNEL_PID"
