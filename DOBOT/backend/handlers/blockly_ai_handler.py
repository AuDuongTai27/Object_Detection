#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import urllib.request
import urllib.error
import tornado.web
from backend.context import BASE_DIR, robot

GEMINI_KEY_FILE = BASE_DIR / "gemini_api_key.json"

# Danh sách ứng viên dự phòng nếu không list được models từ API Key
FALLBACK_CANDIDATES = [
    ("v1beta", "gemini-2.5-flash"),
    ("v1beta", "gemini-2.0-flash"),
    ("v1beta", "gemini-2.0-flash-exp"),
    ("v1beta", "gemini-flash-latest"),
    ("v1beta", "gemini-1.5-flash-latest"),
    ("v1", "gemini-1.5-flash"),
    ("v1", "gemini-1.5-flash-latest"),
    ("v1beta", "gemini-1.5-flash"),
    ("v1beta", "gemini-1.5-pro-latest"),
    ("v1", "gemini-1.5-pro"),
    ("v1beta", "gemini-pro"),
    ("v1", "gemini-pro")
]

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
7. dobot_rail_move:
   - Fields: L (mm, từ 0 đến 1000), SPEED (mm/s, từ 10 đến 150, mặc định 50).
   - Dùng để di chuyển cụm cánh tay robot dọc theo hệ ray trượt tuyến tính 1.0m khi gắp thả giữa các trạm cách xa nhau hoặc mở rộng phạm vi làm việc.
8. dobot_rail_home:
   - Fields: {} (không có tham số, đưa ray trượt về công tắc cữ hành trình mốc L=0 mm).

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
- Khi làm việc với ray trượt (Sliding Rail 1000mm):
  + Tọa độ ray trượt: 0mm <= L <= 1000mm.
  + Chu trình điển hình: Trượt ray tới trạm gắp bằng dobot_rail_move, hạ gắp phôi an toàn, nhấc lên độ cao an toàn, trượt ray sang trạm thả bằng dobot_rail_move, hạ thả phôi, rồi kết thúc.

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

def extract_json_from_text(text):
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
    return json.loads(text)

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

def load_stored_model():
    if GEMINI_KEY_FILE.exists():
        try:
            with open(GEMINI_KEY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("model", "")
        except Exception:
            pass
    return ""

def save_stored_api_key(key, model=""):
    try:
        content = {"api_key": key.strip()}
        if model:
            content["model"] = model
        with open(GEMINI_KEY_FILE, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
        return True
    except Exception as e:
        print(f"[-] Lỗi lưu Gemini API Key: {e}")
        return False

def discover_gemini_models(api_key):
    """
    Tự động truy vấn danh sách model được cấp quyền bởi API Key từ Google AI Studio.
    Thử cả v1beta và v1 để lấy chính xác các model đang hoạt động.
    """
    discovered = []
    auth_errors = []

    for ver in ["v1beta", "v1"]:
        url = f"https://generativelanguage.googleapis.com/{ver}/models?key={api_key}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DobotStudio/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        m_name = m.get("name", "").replace("models/", "")
                        discovered.append((ver, m_name))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            # Bắt lỗi API key sai ngay lập tức
            if e.code in (400, 403) and ("API_KEY_INVALID" in err_body or "API key not valid" in err_body):
                raise ValueError("Google Gemini API Key không hợp lệ! Vui lòng kiểm tra lại key đã sao chép từ Google AI Studio.")
            auth_errors.append(f"{ver}: HTTP {e.code} {err_body[:120]}")
        except Exception as e:
            auth_errors.append(f"{ver}: {str(e)}")

    if discovered:
        # Xếp hạng ưu tiên: flash > version cao > stable
        def rank_model(item):
            ver, name = item
            score = 0
            n = name.lower()
            if "flash" in n:
                score += 100
            if "2.5" in n:
                score += 50
            elif "2.0" in n:
                score += 40
            elif "1.5" in n:
                score += 30
            if "exp" not in n:
                score += 10
            if ver == "v1beta":
                score += 5
            return score

        discovered.sort(key=rank_model, reverse=True)
        return discovered

    # Nếu không list được models (ví dụ hạn chế quyền), dùng danh sách dự phòng
    print(f"[*] Dùng danh sách fallback candidates do không list được models ({auth_errors})")
    return FALLBACK_CANDIDATES

def call_gemini_api(api_key, prompt, context_info=None):
    if not api_key:
        raise ValueError("Chưa cấu hình Google Gemini API Key!")

    full_user_content = f"Yêu cầu của người dùng: {prompt}"
    if context_info:
        full_user_content += f"\n\nThông tin trạng thái hiện tại của robot:\n{json.dumps(context_info, ensure_ascii=False)}"

    # 1. Tìm các model khả dụng
    cached_model = load_stored_model()
    candidates = []
    if cached_model:
        # Đưa model đã lưu lên đầu danh sách thử
        for ver in ["v1beta", "v1"]:
            candidates.append((ver, cached_model))

    discovered = discover_gemini_models(api_key)
    for item in discovered:
        if item not in candidates:
            candidates.append(item)

    last_err = None
    for ver, model_name in candidates:
        url = f"https://generativelanguage.googleapis.com/{ver}/models/{model_name}:generateContent?key={api_key}"
        
        # Thử payload chuẩn (v1beta hỗ trợ systemInstruction + responseMimeType)
        if ver == "v1beta":
            payload = {
                "contents": [{"role": "user", "parts": [{"text": full_user_content}]}],
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json"
                }
            }
        else:
            # v1: inline system prompt vào contents
            combined_prompt = f"{SYSTEM_PROMPT}\n\nCHÚ Ý: Bắt buộc chỉ trả về DUY NHẤT chuỗi JSON hợp lệ, không giải thích ngoài JSON.\n\n{full_user_content}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": combined_prompt}]}],
                "generationConfig": {"temperature": 0.2}
            }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates_list = res_data.get("candidates", [])
                if candidates_list:
                    parts = candidates_list[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        parsed = extract_json_from_text(text)
                        # Lưu lại model hoạt động tốt nhất
                        save_stored_api_key(api_key, model=model_name)
                        return model_name, parsed
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_err = f"Model {model_name} ({ver}) HTTP {e.code}: {err_body[:200]}"
            print(f"[!] Gemini {model_name} ({ver}) lỗi: {last_err}")
            continue
        except Exception as e:
            last_err = f"Model {model_name} ({ver}) exception: {e}"
            print(f"[!] Gemini {model_name} ({ver}) exception: {last_err}")
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
            model_used, test_res = call_gemini_api(key, test_prompt)
            masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
            self.write({
                "status": "ok",
                "message": f"Đã lưu và xác thực Google Gemini API Key thành công! (Model: {model_used})",
                "model": model_used,
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

            model_used, result = call_gemini_api(api_key, prompt, context_info)
            if isinstance(result, dict):
                result["model_used"] = model_used
            self.write(result)
        except Exception as e:
            self.set_status(500)
            self.write({
                "status": "error",
                "message": f"Lỗi sinh khối AI: {str(e)}"
            })
