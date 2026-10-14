#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import urllib.request
import urllib.error
import tornado.web
from backend.context import BASE_DIR, robot

GEMINI_KEY_FILE = BASE_DIR / "gemini_api_key.json"
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

SYSTEM_PROMPT = """Bạn là DOBOT AI COPILOT - Trợ lý AI chuyên biệt cho cánh tay robot Dobot Magician tại FabLab EIU.
NHIỆM VỤ DUY NHẤT CỦA BẠN: Lập trình điều khiển cánh tay robot Dobot Magician thông qua các khối lệnh Blockly (Visual Blocks).

DANH SÁCH KHỐI LỆNH BLOCKLY HỖ TRỢ:
1. dobot_move_xyz:
   - Fields: X (mm, từ 140 đến 330), Y (mm, từ -330 đến 330), Z (mm, từ -65 đến 165), R (độ, từ -180 đến 180), MODE ("safe" hoặc "direct").
   - "safe": Nhấc an toàn (Safe Jump - nhấc lên độ cao an toàn, bay ngang, rồi hạ xuống, chống va chạm phôi). ƯU TIÊN DÙNG CHO GẮP THẢ VÀ TIẾP CẬN.
   - "direct": Bay thẳng trực tiếp. Dùng cho thao tác tinh chỉnh hoặc vẽ đường thẳng.
2. dobot_move_joint:
   - Fields: J1 (-90 đến 90 độ), J2 (0 đến 85 độ), J3 (-10 đến 85 độ), J4 (-90 đến 90 độ).
   - Dùng để quay các khớp xoay, vẫy chào, đổi tư thế.
3. dobot_move_relative:
   - Fields: DX (-100 đến 100), DY (-100 đến 100), DZ (-100 đến 100), DR (-180 đến 180).
4. dobot_suction:
   - Fields: STATE ("ON" để bật giác hút, "OFF" để tắt/nhả giác hút).
5. dobot_wait:
   - Fields: TIME (số giây dừng chờ, ví dụ 0.5, 1.0). Sau khi BẬT giác hút NÊN chờ 0.5s để áp suất chân không đạt đỉnh.
6. dobot_home:
   - Fields: {} (không có tham số, đưa robot về tư thế chuẩn Home X=250, Y=0, Z=50, R=0).

QUY TẮC AN TOÀN BẮT BUỘC (SAFETY ENVELOPE):
- Bán kính làm việc ngang: R_horiz = sqrt(X^2 + Y^2) PHẢI nằm trong khoảng 140mm <= R_horiz <= 330mm. Tránh quá gần đế robot (<140mm) và quá xa (>330mm).
- Cao độ đầu hút Z: -65mm <= Z <= 165mm.
- Khi gắp phôi:
  + Luôn dùng dobot_move_xyz (MODE: "safe") để tiếp cận điểm gắp.
  + Bật giác hút: dobot_suction (STATE: "ON").
  + Dừng chờ: dobot_wait (TIME: 0.5) để hút chắc.
  + Di chuyển sang vị trí thả bằng dobot_move_xyz (MODE: "safe").
  + Tắt giác hút: dobot_suction (STATE: "OFF").
  + Dừng chờ: dobot_wait (TIME: 0.3) để phôi nhả hoàn toàn.
  + Kết thúc hành trình bằng dobot_home để đưa tay về vị trí an toàn.

QUY TẮC GUARDRAIL (TỪ CHỐI THÂN THIỆN):
- Nếu người dùng hỏi những câu hỏi ngoài lề (như thời tiết, thơ văn, lập trình web, lịch sử, toán ngoài lề, tán gẫu không liên quan tới điều khiển robot Dobot):
  + Đặt "status": "refusal".
  + Đặt "steps": [].
  + Trả lời bằng "reply_text" cực kỳ thân thiện, hóm hỉnh, xưng "Em là Dobot AI Assistant tại FabLab EIU" và nhắc khéo người dùng hãy giao các nhiệm vụ gắp thả, tuần tra, vẽ hình, hoặc điều khiển robot.

ĐỊNH DẠNG JSON ĐẦU RA BẮT BUỘC:
{
  "status": "success" hoặc "refusal",
  "reply_text": "Lời chào và mô tả ngắn gọn kế hoạch hành động hoặc lời từ chối thân thiện...",
  "thought": "Phân tích tư duy logic: Kiểm tra an toàn tọa độ, giải thích chiến lược quy hoạch quỹ đạo...",
  "steps": [
    {
      "block_type": "dobot_move_xyz",
      "fields": { "X": 220, "Y": 0, "Z": -20, "R": 0, "MODE": "safe" },
      "explanation": "Giải thích ngắn gọn lý do chọn bước này..."
    }
  ]
}
"""

def load_stored_api_key():
    if GEMINI_KEY_FILE.exists():
        try:
            with open(GEMINI_KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("api_key", "").strip()
        except Exception:
            pass
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    return ""

def save_stored_api_key(key):
    try:
        with open(GEMINI_KEY_FILE, "w", encoding="utf-8") as f:
            json.dump({"api_key": key.strip()}, f, indent=2)
        return True
    except Exception as e:
        print(f"[-] Lỗi lưu Gemini API Key: {e}")
        return False

def call_gemini_api(api_key, prompt, context_info=None):
    if not api_key:
        raise ValueError("Chưa cấu hình Google Gemini API Key!")

    full_user_content = f"Yêu cầu của người dùng: {prompt}"
    if context_info:
        full_user_content += f"\n\nThông tin trạng thái hiện tại của robot:\n{json.dumps(context_info, ensure_ascii=False)}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_user_content}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    last_err = None
    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        return json.loads(text)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_err = f"Model {model_name} HTTP {e.code}: {err_body[:200]}"
            print(f"[!] Gemini {model_name} lỗi: {last_err}")
            continue
        except Exception as e:
            last_err = f"Model {model_name} lỗi: {e}"
            print(f"[!] Gemini {model_name} exception: {last_err}")
            continue

    raise RuntimeError(f"Không thể gọi Gemini API: {last_err}")


class ApiBlocklyAiCredsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        key = load_stored_api_key()
        masked = ""
        if key:
            masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
        self.write({
            "status": "ok",
            "has_key": bool(key),
            "masked_key": masked
        })

    def post(self):
        try:
            data = json.loads(self.request.body)
            key = data.get("api_key", "").strip()
            if not key:
                self.set_status(400)
                self.write({"status": "error", "message": "API key không được để trống!"})
                return

            # Thử ping Gemini với API Key này
            test_prompt = "Chào robot"
            test_res = call_gemini_api(key, test_prompt)
            save_stored_api_key(key)
            masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
            self.write({
                "status": "ok",
                "message": "Đã lưu và xác thực Google Gemini API Key thành công!",
                "masked_key": masked
            })
        except Exception as e:
            self.set_status(400)
            self.write({
                "status": "error",
                "message": f"Xác thực API Key thất bại: {str(e)}"
            })


class ApiBlocklyAiGenerateHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body)
            prompt = data.get("prompt", "").strip()
            if not prompt:
                self.set_status(400)
                self.write({"status": "error", "message": "Nội dung yêu cầu (prompt) không được để trống!"})
                return

            api_key = data.get("api_key", "").strip() or load_stored_api_key()
            if not api_key:
                self.set_status(400)
                self.write({
                    "status": "error",
                    "need_key": True,
                    "message": "Chưa có Google Gemini API Key! Vui lòng bấm nút '🔑 Cài đặt API Key' để nhập key miễn phí."
                })
                return

            context_info = data.get("context", {})
            if not context_info and robot:
                context_info = {
                    "last_pose": robot.last_pose,
                    "safety_limits": robot.safety_limits,
                    "is_rail_mode": robot.is_rail_mode,
                    "rail_current_pos": robot.rail_current_pos
                }

            result = call_gemini_api(api_key, prompt, context_info)
            self.write(result)
        except Exception as e:
            self.set_status(500)
            self.write({
                "status": "error",
                "message": f"Lỗi sinh khối AI: {str(e)}"
            })
