#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import serial
import serial.tools.list_ports
import tornado.web
import tornado.websocket
from backend.context import robot, connected_clients, BASE_DIR

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        connected_clients.add(self)
        print(f"[+] Web Client kết nối: {self.request.remote_ip} (Tổng: {len(connected_clients)})")

    def on_message(self, message):
        try:
            cmd = json.loads(message)
            action = cmd.get("action")
            if action == "clear_alarms":
                robot.clear_alarms()
                self.write_message(json.dumps({"type": "feedback", "msg": "✅ Đã xóa cờ lỗi & khôi phục hàng đợi lệnh Dobot!"}))
            elif action in ("recover_pose", "safe_retract"):
                ok = robot.recover_to_safe_pose()
                self.write_message(json.dumps({"type": "feedback", "msg": "🛡️ Đã thu gọn an toàn & khôi phục trạng thái sẵn sàng!"}))
            elif action == "emergency_stop":
                robot.emergency_stop()
                self.write_message(json.dumps({"type": "feedback", "msg": "🛑 Đã Dừng Khẩn Cấp & Xóa Hàng Đợi"}))
            elif action == "home":
                ok = robot.home()
                if ok:
                    self.write_message(json.dumps({"type": "feedback", "msg": "🏠 Robot đang tự động chạy Homing về gốc tọa độ chuẩn..."}))
                else:
                    self.write_message(json.dumps({"type": "feedback", "msg": "❌ Không thể gửi lệnh Homing (Robot chưa kết nối)"}))
            elif action == "suction":
                val = bool(cmd.get("value", False))
                robot.set_suction(val)
                self.write_message(json.dumps({"type": "feedback", "msg": f"Giác hút: {'BẬT' if val else 'TẮT'}"}))
            elif action == "jog":
                axis = cmd.get("axis", "z").lower()
                step = float(cmd.get("step", 10.0))
                dx = step if axis == "x" else 0.0
                dy = step if axis == "y" else 0.0
                dz = step if axis == "z" else 0.0
                dr = step if axis == "r" else 0.0
                ok, msg = robot.move_relative(dx, dy, dz, dr)
                self.write_message(json.dumps({"type": "feedback", "msg": msg}))
            elif action == "teleop_stream":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                mode = int(cmd.get("mode", 1))
                fast = bool(cmd.get("fast", False))
                robot.teleop_move(x, y, z, r, mode=mode, fast=fast)
            elif action == "move_xyz":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                mode = int(cmd.get("mode", 1))
                robot.move_to_xyz(x, y, z, r, mode=mode)
                self.write_message(json.dumps({"type": "feedback", "msg": f"🚀 Đang di chuyển tới X={x:.0f}, Y={y:.0f}, Z={z - 59.5:.0f}"}))
            elif action == "safe_jump":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                safe_z = cmd.get("safe_z", None)
                if safe_z is not None:
                    safe_z = float(safe_z)
                robot.move_safe_jump(x, y, z, r, safe_z=safe_z)
                self.write_message(json.dumps({"type": "feedback", "msg": f"📦 Đang Safe Jump tới X={x:.0f}, Y={y:.0f}, Z={z - 59.5:.0f}"}))
            elif action == "move_joint":
                j1 = float(cmd.get("j1", 0))
                j2 = float(cmd.get("j2", 0))
                j3 = float(cmd.get("j3", 0))
                j4 = float(cmd.get("j4", 0))
                mode = int(cmd.get("mode", 4))
                robot.move_joint(j1, j2, j3, j4, mode=mode)
                self.write_message(json.dumps({"type": "feedback", "msg": f"🔄 Đang xoay khớp: J1={j1:.1f}°, J2={j2:.1f}°, J3={j3:.1f}°"}))
            # --- CÁC LỆNH ĐIỀU KHIỂN RAY TRƯỢT & VÙNG AN TOÀN ---
            elif action == "rail_jog":
                dist = float(cmd.get("dist", 10.0))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                def _do_jog():
                    ok, res_msg = robot.rail_jog(dist, speed)
                    for c in list(connected_clients):
                        try:
                            c.write_message(json.dumps({"type": "feedback", "msg": res_msg}))
                        except Exception:
                            pass
                threading.Thread(target=_do_jog, daemon=True).start()
                self.write_message(json.dumps({"type": "feedback", "msg": f"🛤️ Đang jog ray {dist:+.1f} mm..."}))
            elif action == "rail_move":
                pos = float(cmd.get("pos") if cmd.get("pos") is not None else cmd.get("l", 0.0))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                def _do_move():
                    ok, res_msg = robot.rail_move_to(pos, speed)
                    for c in list(connected_clients):
                        try:
                            c.write_message(json.dumps({"type": "feedback", "msg": res_msg}))
                        except Exception:
                            pass
                threading.Thread(target=_do_move, daemon=True).start()
                self.write_message(json.dumps({"type": "feedback", "msg": f"🛤️ Ray trượt đang di chuyển tới L={pos:.1f} mm..."}))
            elif action == "rail_home":
                def _do_home():
                    ok, res_msg = robot.rail_home()
                    for c in list(connected_clients):
                        try:
                            c.write_message(json.dumps({"type": "feedback", "msg": res_msg}))
                        except Exception:
                            pass
                threading.Thread(target=_do_home, daemon=True).start()
                self.write_message(json.dumps({"type": "feedback", "msg": "🏠 Bắt đầu dò gốc Home cho ray trượt..."}))
            elif action == "rail_stop":
                ok = robot.rail_stop()
                self.write_message(json.dumps({"type": "feedback", "msg": "🛑 Đã phát lệnh dừng khẩn cấp ray trượt!"}))
            elif action == "set_rail_mode":
                val = bool(cmd.get("enabled", True))
                robot.set_rail_mode(val)
                self.write_message(json.dumps({"type": "feedback", "msg": f"Chế độ: {'Ray trượt 1000mm' if val else 'Để bàn độc lập'}"}))
            elif action == "update_safety_limits":
                limits = cmd.get("limits", {})
                robot.update_safety_limits(limits)
                self.write_message(json.dumps({"type": "feedback", "msg": "💾 Đã cập nhật & lưu thông số vùng an toàn!"}))
            elif action in ("recover_pose", "safe_retract"):
                threading.Thread(target=robot.recover_to_safe_pose, daemon=True).start()
                self.write_message(json.dumps({"type": "feedback", "msg": "🛡️ Đang kích hoạt cơ chế thu gọn an toàn & xóa lỗi đèn đỏ..."}))
        except Exception as e:
            print("[-] Lỗi xử lý lệnh từ client:", e)

    def on_close(self):
        connected_clients.discard(self)
        print(f"[-] Web Client ngắt kết nối (Còn lại: {len(connected_clients)})")


class ApiCmdHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()

    def get(self):
        pose = robot.get_pose() or robot.last_pose or {}
        if isinstance(pose, dict):
            pose["l"] = robot.rail_current_pos
        alarms = robot.cached_alarms
        has_alarm = bool(alarms and len(alarms) > 0)
        self.write({
            "status": "ok",
            "pose": pose,
            "connected": robot.connected,
            "alarms": alarms,
            "has_alarm": has_alarm,
            "is_rail_mode": robot.is_rail_mode,
            "rail_pos": robot.rail_current_pos,
            "rail": {
                "mode": robot.is_rail_mode,
                "pos": robot.rail_current_pos,
                "switch": robot.rail_switch_active,
                "is_homing": robot.rail_is_homing,
                "is_moving": robot.rail_is_moving,
            },
            "safety": robot.safety_limits
        })

    def post(self):
        try:
            cmd = json.loads(self.request.body)
            action = cmd.get("action")
            if action == "teleop_stream":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                mode = int(cmd.get("mode", 1))
                fast = bool(cmd.get("fast", False))
                ok = robot.teleop_move(x, y, z, r, mode=mode, fast=fast)
                self.write({"status": "ok" if ok else "fail"})
                return
            if action == "move_xyz":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                mode = int(cmd.get("mode", 1))
                target_l = cmd.get("l", cmd.get("rail_l"))
                if target_l is not None and robot.is_rail_mode:
                    try:
                        target_l = float(target_l)
                        if abs(target_l - robot.rail_current_pos) > 1.0:
                            robot.rail_move_to(target_l)
                    except Exception as e:
                        print(f"[ApiCmd] Lỗi di chuyển ray: {e}")
                ok = robot.move_to_xyz(x, y, z, r, mode=mode)
                self.write({"status": "ok" if ok else "fail"})
            elif action == "safe_jump":
                x = float(cmd.get("x", 200))
                y = float(cmd.get("y", 0))
                z = float(cmd.get("z", 100))
                r = float(cmd.get("r", 0))
                safe_z = cmd.get("safe_z")
                if safe_z is not None:
                    safe_z = float(safe_z)
                target_l = cmd.get("l", cmd.get("rail_l"))
                if target_l is not None and robot.is_rail_mode:
                    try:
                        target_l = float(target_l)
                        if abs(target_l - robot.rail_current_pos) > 1.0:
                            robot.rail_move_to(target_l)
                    except Exception as e:
                        print(f"[ApiCmd] Lỗi di chuyển ray trong safe_jump: {e}")
                ok = robot.move_safe_jump(x, y, z, r, safe_z=safe_z)
                self.write({"status": "ok" if ok else "fail"})
            elif action == "suction":
                val = bool(cmd.get("value", False))
                robot.set_suction(val)
                self.write({"status": "ok", "suction": val})
            elif action == "clear_alarms":
                robot.clear_alarms()
                self.write({"status": "ok"})
            elif action in ("recover_pose", "safe_retract"):
                ok = robot.recover_to_safe_pose()
                self.write({"status": "ok" if ok else "fail", "msg": "Đã thu gọn cánh tay và khôi phục an toàn"})
            elif action == "home":
                ok = robot.home()
                self.write({"status": "ok" if ok else "fail"})
            elif action == "rail_jog":
                dist = float(cmd.get("dist", 10.0) or cmd.get("delta", 0.0))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                threading.Thread(target=robot.rail_jog, args=(dist, speed), daemon=True).start()
                self.write({"status": "ok", "msg": f"Đang jog ray {dist:+.1f} mm"})
            elif action in ("rail_move", "rail_move_to"):
                pos = float(cmd.get("pos", cmd.get("target_mm", cmd.get("l", 0.0))))
                speed = float(cmd.get("speed", DEFAULT_SPEED_MM_S))
                threading.Thread(target=robot.rail_move_to, args=(pos, speed), daemon=True).start()
                self.write({"status": "ok", "msg": f"Đang di chuyển ray tới L={pos:.1f} mm"})
            elif action == "rail_home":
                threading.Thread(target=robot.rail_home, daemon=True).start()
                self.write({"status": "ok", "msg": "Homing ray trượt đã bắt đầu"})
            elif action == "rail_stop":
                ok = robot.rail_stop()
                self.write({"status": "ok" if ok else "fail"})
            elif action == "set_rail_mode":
                val = bool(cmd.get("enabled", True))
                robot.set_rail_mode(val)
                self.write({"status": "ok", "is_rail_mode": robot.is_rail_mode})
            elif action == "update_safety_limits":
                limits = cmd.get("limits", {})
                updated = robot.update_safety_limits(limits)
                self.write({"status": "ok", "limits": updated})
            else:
                self.write({"status": "error", "msg": f"Unknown action: {action}"})
        except Exception as e:
            self.set_status(400)
            self.write({"status": "error", "error": str(e)})


class ApiWorkspaceSafetyHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()

    def get(self):
        cur_pose = robot.get_pose() or robot.last_pose or {}
        self.write({
            "status": "ok",
            "is_rail_mode": robot.is_rail_mode,
            "rail_pos": round(robot.rail_current_pos, 1),
            "current_pose": cur_pose,
            "limits": robot.safety_limits
        })

    def post(self):
        try:
            data = json.loads(self.request.body)
            if "is_rail_mode" in data:
                robot.set_rail_mode(bool(data["is_rail_mode"]))
            if "limits" in data:
                robot.update_safety_limits(data["limits"])
            self.write({
                "status": "ok",
                "is_rail_mode": robot.is_rail_mode,
                "limits": robot.safety_limits,
                "message": "Cập nhật vùng an toàn thành công!"
            })
        except Exception as e:
            self.set_status(400)
            self.write({"status": "error", "error": str(e)})


class ApiRobotConnectHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            target_port = data.get("port", None)
            ok = robot.connect(port=target_port)
            if ok:
                self.write({"success": True, "connected": True, "port": robot.port, "message": f"Kết nối Dobot thành công ({robot.port})"})
            else:
                self.write({"success": False, "connected": False, "error": "Không tìm thấy Dobot Magician qua cổng USB. Vui lòng cắm cáp và bấm thử lại!"})
        except Exception as e:
            self.write({"success": False, "connected": False, "error": str(e)})


class ApiRobotDisconnectHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def post(self):
        robot.disconnect()
        self.write({"success": True, "connected": False, "message": "Đã ngắt kết nối Dobot"})


class ApiRobotPortsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        self.write({"ports": ports, "connected": robot.connected, "current_port": robot.port})
