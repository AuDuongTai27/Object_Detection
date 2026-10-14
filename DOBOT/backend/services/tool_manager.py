#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import subprocess
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class ToolProcessManager:
    """Quản lý các công cụ Native GUI độc lập (capture_from_camera.py, dobot_auto_sort.py)."""
    def __init__(self):
        self.proc = None
        self.active_tool = None
        self.lock = threading.Lock()

    def launch(self, tool_name, **kwargs):
        with self.lock:
            # Nếu tool cũ còn đang chạy
            if self.proc and self.proc.poll() is None:
                return {
                    "success": False,
                    "error": f"Công cụ '{self.active_tool}' đang chạy! Vui lòng dừng công cụ này trước để giải phóng camera.",
                    "active_tool": self.active_tool
                }

            cmd = [sys.executable]
            if tool_name == "capture":
                script = PROJECT_ROOT / "capture_from_camera.py"
                cmd.append(str(script))
                cls_name = kwargs.get("class_name", "cube_red")
                cmd.extend(["--class", str(cls_name)])
                cmd.extend(["--output", "dataset_raw"])
                if "cam_id" in kwargs and kwargs["cam_id"] is not None:
                    cmd.extend(["--camera", str(kwargs["cam_id"])])

            elif tool_name == "sort":
                script = BASE_DIR / "dobot_auto_sort.py"
                cmd.append(str(script))
                if "cam_id" in kwargs and kwargs["cam_id"] is not None:
                    cmd.extend(["--cam", str(kwargs["cam_id"])])
                if "model" in kwargs and kwargs["model"]:
                    cmd.extend(["--model", str(kwargs["model"])])

            elif tool_name == "calib":
                script = BASE_DIR / "calibrate_camera_to_dobot.py"
                cmd.append(str(script))
                if "cam_id" in kwargs and kwargs["cam_id"] is not None:
                    cmd.extend(["--cam", str(kwargs["cam_id"])])

            else:
                return {"success": False, "error": f"Không hỗ trợ công cụ '{tool_name}'"}

            try:
                creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                self.proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), creationflags=creationflags)
                self.active_tool = tool_name
                print(f"[ToolManager] 🚀 Đã mở công cụ '{tool_name}' (PID: {self.proc.pid})")
                return {"success": True, "active_tool": tool_name, "pid": self.proc.pid}
            except Exception as e:
                print(f"[ToolManager] ❌ Lỗi khởi chạy: {e}")
                return {"success": False, "error": str(e)}

    def stop(self, tool_name=None):
        with self.lock:
            if not self.proc:
                self.proc = None
                self.active_tool = None
                return {"success": True, "message": "Không có công cụ nào đang chạy"}

            try:
                pid = self.proc.pid
                tool_label = self.active_tool
                if sys.platform == "win32":
                    # taskkill /F /T /PID tiêu diệt toàn bộ cây tiến trình (console window + python + opencv)
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                else:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()

                print(f"[ToolManager] ⏹️ Đã dừng công cụ '{tool_label}' (PID: {pid}) và giải phóng Camera thành công!")
                self.proc = None
                self.active_tool = None
                return {"success": True, "message": "Đã đóng công cụ & giải phóng camera thành công"}
            except Exception as e:
                print(f"[ToolManager] ❌ Lỗi khi dừng công cụ: {e}")
                return {"success": False, "error": str(e)}

    def get_status(self):
        with self.lock:
            if self.proc:
                if self.proc.poll() is None:
                    return {"is_running": True, "active_tool": self.active_tool, "pid": self.proc.pid}
                else:
                    self.proc = None
                    self.active_tool = None
            return {"is_running": False, "active_tool": None}

tool_manager = ToolProcessManager()
