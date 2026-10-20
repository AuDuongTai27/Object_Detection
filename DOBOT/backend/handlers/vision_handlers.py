#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import json
import tornado.web
import tornado.websocket
from backend.context import (
    robot, BASE_DIR, PROJECT_ROOT, MODELS_DIR, HAS_WEB_STUDIO, tool_manager, vision_engine
)
try:
    from web_vision_engine import WebVisionEngine
except ImportError:
    WebVisionEngine = None

class VideoWsHandler(tornado.websocket.WebSocketHandler):
    """WebSocket stream camera frames (JPEG binary) - đáng tin cậy hơn MJPEG HTTP."""

    def check_origin(self, origin):
        return True  # Cho phép mọi origin

    def open(self):
        mode = self.get_argument("mode", "raw")
        self._mode = mode
        self._running = True
        tornado.ioloop.IOLoop.current().spawn_callback(self._push_frames)

    async def _push_frames(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            return

        # 1. Gửi ngay khung hình hiện có đầu tiên để Client không bị trễ/màn hình đen
        try:
            _, initial_jpeg = vision_engine.get_jpeg_with_id(self._mode)
            if initial_jpeg and self._running:
                await self.write_message(initial_jpeg, binary=True)
        except Exception:
            pass

        # 2. Vòng lặp đẩy các khung hình mới liên tục (~30 FPS)
        last_id = -1
        while self._running:
            try:
                cur_id, jpeg = vision_engine.get_jpeg_with_id(self._mode)
                if jpeg and cur_id != last_id:
                    last_id = cur_id
                    await self.write_message(jpeg, binary=True)
                await tornado.gen.sleep(0.033)  # ~30 fps
            except tornado.websocket.WebSocketClosedError:
                break
            except Exception:
                break
        self._running = False

    def on_message(self, message):
        pass  # Không nhận message từ client

    def on_close(self):
        self._running = False
class ApiVisionStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO and vision_engine:
            self.write(vision_engine.get_status())
        else:
            self.write({"camera_online": False})


class ApiVisionPickHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            self.write({"success": False, "error": "Vision Engine chưa khởi động"})
            return

        try:
            data = json.loads(self.request.body)
            pick_x = data.get("pick_x") or data.get("dobot_x")
            pick_y = data.get("pick_y") or data.get("dobot_y")
            cube_name = data.get("cube_name") or data.get("class_name", "cube")

            # Nếu gửi tọa độ pixel nhấp chuột (x, y)
            if pick_x is None and "x" in data and "y" in data:
                px = float(data["x"])
                py = float(data["y"])
                
                # Tìm xem pixel này có nằm trong bbox của vật thể nào không
                matched_cube = None
                with vision_engine.lock:
                    for c in vision_engine.detected_cubes:
                        bbox = c.get("bbox", [])
                        if len(bbox) == 4:
                            x1, y1, x2, y2 = bbox
                            if x1 <= px <= x2 and y1 <= py <= y2:
                                matched_cube = c
                                break

                if matched_cube and matched_cube.get("dobot_coord", {}).get("x") is not None:
                    pick_x = matched_cube["dobot_coord"]["x"]
                    pick_y = matched_cube["dobot_coord"]["y"]
                    cube_name = matched_cube.get("class_name", cube_name)
                else:
                    # Nếu không trúng bbox, thử chuyển pixel sang dobot bằng Homography trực tiếp
                    dx, dy = vision_engine.pixel_to_dobot(px, py)
                    if dx is not None and dy is not None:
                        pick_x = dx
                        pick_y = dy
                    else:
                        self.write({"success": False, "message": "Không thể đổi tọa độ pixel sang tọa độ Dobot (chưa nạp Calib)"})
                        return

            if pick_x is None or pick_y is None:
                self.write({"success": False, "message": "Thiếu tọa độ gắp Dobot"})
                return

            res = vision_engine.execute_pick_and_place(float(pick_x), float(pick_y), str(cube_name))
            self.write(res)
        except Exception as e:
            self.write({"success": False, "message": str(e)})


class ApiVisionAutoSortHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            self.write({"success": False, "error": "Vision Engine chưa khởi động"})
            return

        try:
            data = json.loads(self.request.body) if self.request.body else {}
            enable = data.get("enable", None)
            res = vision_engine.toggle_auto_sort(enable)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


# ==============================================================================
# KÊNH RIÊNG CHO TAB 6 (CỬ CHỈ TAY) ➔ dobot_auto_sort.py
# Các API của Tab 4 (/pick, /auto_sort, /status) giữ nguyên, không đi qua kênh này.
# ==============================================================================
SHARED_STATE_FILE = BASE_DIR / ".detected_cubes.json"
AUTO_SORT_CMD_FILE = BASE_DIR / ".auto_sort_cmd.json"
SHARED_STATE_MAX_AGE = 4.0


def read_auto_sort_state():
    """Trả về trạng thái do dobot_auto_sort.py ghi ra, hoặc None nếu tool không chạy."""
    try:
        with open(SHARED_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) < SHARED_STATE_MAX_AGE:
            return data
    except Exception:
        pass
    return None


def send_auto_sort_cmd(cmd):
    """Gửi lệnh sang dobot_auto_sort.py (kèm timestamp để tool bỏ qua lệnh cũ)."""
    cmd = dict(cmd, ts=time.time())
    tmp = AUTO_SORT_CMD_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    os.replace(tmp, AUTO_SORT_CMD_FILE)


TOOL_NOT_RUNNING_MSG = "Công cụ Auto Sort (Tab 4) chưa chạy! Hãy bấm 'Khởi chạy Auto Sort' trước."


class ApiGestureStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        state = read_auto_sort_state()
        if state is None:
            self.write({"tool_alive": False, "auto_sort_enabled": False, "is_picking": False, "task_status": None})
            return
        self.write({
            "tool_alive": True,
            "auto_sort_enabled": bool(state.get("auto_sort_enabled", False)),
            "is_picking": bool(state.get("is_busy", False)),
            "task_status": state.get("task_status"),
            "detected_count": len(state.get("cubes", []))
        })


class ApiGestureAutoSortHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            state = read_auto_sort_state()
            if state is None:
                self.write({"success": False, "error": TOOL_NOT_RUNNING_MSG})
                return

            enable = data.get("enable", None)
            if enable is None:
                enable = not bool(state.get("auto_sort_enabled", False))
            enable = bool(enable)

            send_auto_sort_cmd({"action": "toggle_auto", "enable": enable})
            self.write({"success": True, "auto_sort_enabled": enable})
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiVisionPickColorHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            color = str(data.get("color", "")).strip().lower()

            color_map = {
                "red": ("cube_red", "Đỏ"),
                "cube_red": ("cube_red", "Đỏ"),
                "green": ("cube_green", "Xanh Lục"),
                "cube_green": ("cube_green", "Xanh Lục"),
                "blue": ("cube_blue", "Xanh Dương"),
                "cube_blue": ("cube_blue", "Xanh Dương"),
                "yellow": ("cube_yellow", "Vàng"),
                "cube_yellow": ("cube_yellow", "Vàng"),
            }
            if color not in color_map:
                self.write({"success": False, "error": f"Màu không hợp lệ: '{color}'"})
                return
            target_class, color_vn = color_map[color]

            state = read_auto_sort_state()
            if state is None:
                self.write({"success": False, "error": TOOL_NOT_RUNNING_MSG})
                return

            if state.get("is_busy"):
                self.write({"success": False, "error": "Robot đang bận gắp thả, thử lại sau!"})
                return

            if not any(c.get("class_name") == target_class for c in state.get("cubes", [])):
                self.write({"success": False, "error": f"Camera AI chưa thấy khối {color_vn} trên bàn!"})
                return

            send_auto_sort_cmd({"action": "pick_color", "color": target_class})
            self.write({
                "success": True,
                "message": f"Đang gắp khối {color_vn}...",
                "color_name": color_vn
            })
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiVisionModelsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        try:
            candidates = []
            # Ưu tiên các mô hình ONNX siêu nhẹ trước
            if (PROJECT_ROOT / "yolov8n.onnx").exists() and "yolov8n.onnx" not in candidates:
                candidates.append("yolov8n.onnx")
            if MODELS_DIR.exists():
                for f in sorted(MODELS_DIR.glob("*.onnx")):
                    if f.name not in candidates:
                        candidates.append(f.name)
                # Sau đó mới đến các file .pt dự phòng nếu chưa có onnx tương ứng
                for f in sorted(MODELS_DIR.glob("*.pt")):
                    if f.with_suffix(".onnx").name not in candidates and f.name not in candidates:
                        candidates.append(f.name)

            model_objs = []
            for name in candidates:
                p = MODELS_DIR / name
                if not p.exists() and (PROJECT_ROOT / name).exists():
                    p = PROJECT_ROOT / name
                size_mb = round(p.stat().st_size / (1024 * 1024), 1) if p.exists() else 0.0
                is_onnx = name.lower().endswith(".onnx")
                tag = "⚡ ONNX Siêu Nhẹ" if is_onnx else "PyTorch"
                if "best_trained" in name:
                    label = f"Mô hình vừa Train ({name}) [{tag}]"
                elif "more_augmentation" in name:
                    label = f"Mô hình Augmented ({name}) [{tag}]"
                elif name.startswith("yolov8n"):
                    label = f"YOLOv8 Nano ({name}) [{tag}]"
                else:
                    label = f"{name} [{tag}]"

                model_objs.append({
                    "name": name,
                    "label": label,
                    "size_mb": size_mb,
                    "is_onnx": is_onnx,
                    "exists": p.exists()
                })
            active = vision_engine.active_model_name if HAS_WEB_STUDIO and vision_engine else (candidates[0] if candidates else "")
            self.write({
                "status": "ok",
                "models": model_objs,
                "current_model": active,
                "active_model": active
            })
        except Exception as e:
            print(f"[VisionHandler] ❌ Lỗi lấy danh sách models: {e}")
            self.write({
                "status": "error",
                "models": [],
                "current_model": "",
                "active_model": "",
                "error": str(e)
            })

    def post(self):
        try:
            data = json.loads(self.request.body)
            model_name = data.get("model", "")
            target_path = MODELS_DIR / model_name
            if not target_path.exists() and (PROJECT_ROOT / model_name).exists():
                target_path = PROJECT_ROOT / model_name
            if target_path.exists() and HAS_WEB_STUDIO and vision_engine:
                ok = vision_engine.load_best_yolo_model(target_path)
                self.write({"status": "ok", "success": ok, "active_model": vision_engine.active_model_name, "message": f"Đã nạp mô hình {vision_engine.active_model_name}"})
            else:
                self.write({"status": "error", "success": False, "error": "Không tìm thấy file model", "message": "Không tìm thấy file model"})
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiCalibInfoHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        calib_file = BASE_DIR / "homography_dobot.json"
        if calib_file.exists():
            try:
                with open(calib_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.write({"status": "ok", "calibrated": True, "data": data})
                return
            except Exception as e:
                self.write({"status": "error", "calibrated": False, "error": str(e)})
                return
        self.write({"status": "ok", "calibrated": False, "message": "Chưa có file homography_dobot.json"})


class ApiDropTargetsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        drop_file = BASE_DIR / "drop_targets.json"
        if drop_file.exists():
            try:
                with open(drop_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.write({"status": "ok", "data": data})
                return
            except Exception:
                pass
        default_data = {
            "mode": "all",
            "default": {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Mặc Định"},
            "by_color": {
                "cube_red":    {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Đỏ"},
                "cube_green":  {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Xanh Lục"},
                "cube_blue":   {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Xanh Dương"},
                "cube_yellow": {"x": 49.2, "y": -230.1, "z": -44.0, "l": 0.0, "rail_l": 0.0, "name": "Khay Vàng"}
            }
        }
        self.write({"status": "ok", "data": default_data})

    def post(self):
        try:
            data = json.loads(self.request.body)
            drop_file = BASE_DIR / "drop_targets.json"
            with open(drop_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            if HAS_WEB_STUDIO and vision_engine:
                try:
                    import web_vision_engine
                    web_vision_engine.load_drop_targets()
                    if "calib_rail_l" in data:
                        vision_engine.calib_rail_l = float(data["calib_rail_l"])
                except Exception:
                    pass
            print(f"[LiveServer] 💾 Đã lưu cấu hình khay thả: {drop_file}")
            self.write({"status": "ok", "message": "Đã lưu vị trí thả đồ thành công!"})
        except Exception as e:
            self.write({"status": "error", "message": str(e)})


class ApiVoiceConfigHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        cfg_file = BASE_DIR / "voice_config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.write({"status": "ok", "data": data})
                return
            except Exception:
                pass
        self.write({"status": "ok", "data": {"confirm_required": True, "tts_enabled": True}})

    def post(self):
        try:
            data = json.loads(self.request.body)
            cfg_file = BASE_DIR / "voice_config.json"
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            print(f"[LiveServer] 💾 Đã lưu cấu hình Voice AI: {data}")
            self.write({"status": "ok", "message": "Đã lưu cấu hình Voice AI!"})
        except Exception as e:
            self.write({"status": "error", "message": str(e)})

