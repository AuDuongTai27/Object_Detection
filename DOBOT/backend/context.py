#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

from backend.driver.dobot_controller import DobotController
from backend.services.tool_manager import ToolProcessManager

# Import các phân hệ Web Studio
try:
    from web_vision_engine import WebVisionEngine
    from web_dataset_manager import (
        get_dataset_stats, save_captured_frame, delete_captured_image,
        add_new_class, get_recent_captures, DATASET_RAW_DIR
    )
    from web_trainer import web_trainer, COLAB_ZIP_PATH, MODELS_DIR
    try:
        from kaggle_trainer import kaggle_trainer
    except Exception as e_k:
        kaggle_trainer = None
        print(f"[!] Cảnh báo nạp module Kaggle Trainer: {e_k}")
    HAS_WEB_STUDIO = True
except Exception as e:
    HAS_WEB_STUDIO = False
    kaggle_trainer = None
    print(f"[!] Cảnh báo nạp module Web Studio: {e}")

# Khởi tạo đối tượng Singleton dùng chung
robot = DobotController()
vision_engine = WebVisionEngine(robot_controller=robot) if HAS_WEB_STUDIO else None
tool_manager = ToolProcessManager()
connected_clients = set()

poll_counter = 0

def poll_robot_pose():
    global poll_counter
    # 1. Cập nhật chuyển động ray trượt nội suy nếu đang di chuyển
    if robot.rail_motion.get("active", False):
        now = time.time()
        elapsed = now - robot.rail_motion["start_time"]
        dur = robot.rail_motion["duration"]
        if elapsed >= dur:
            robot.rail_motion["active"] = False
            robot.rail_is_moving = False
            robot._save_rail_state(robot.rail_motion["target_pos"])
        else:
            prog = min(1.0, max(0.0, elapsed / dur))
            interp = robot.rail_motion["start_pos"] + prog * (robot.rail_motion["target_pos"] - robot.rail_motion["start_pos"])
            robot.rail_current_pos = round(interp, 2)

    if not connected_clients:
        return

    poll_counter += 1
    # 2. Đọc trạng thái switch cữ hành trình định kỳ mỗi 20 chu kỳ (~1s) khi KHÔNG di chuyển ray
    if robot.connected and (poll_counter % 20 == 0):
        if not robot.rail_is_moving and not robot.rail_is_homing:
            robot.get_rail_switch()

    rail_telemetry = {
        "mode": robot.is_rail_mode,
        "pos": round(robot.rail_current_pos, 1),
        "switch": robot.rail_switch_active,
        "is_homing": robot.rail_is_homing,
        "is_moving": robot.rail_is_moving,
    }

    if robot.connected:
        # Nếu ray trượt đang chạy homing/jogging, hạn chế gửi GetPose liên tục để tránh nghẽn bus serial
        if robot.rail_is_moving or robot.rail_is_homing:
            pose = robot.last_pose
        else:
            pose = robot.get_pose()
        alarms = robot.cached_alarms
        if poll_counter % 10 == 0:
            if not robot.rail_is_moving and not robot.rail_is_homing:
                alarms = robot.get_alarms()
        has_alarm = bool(alarms and len(alarms) > 0)
        msg = json.dumps({
            "type": "pose",
            "connected": True,
            "port": robot.port,
            "data": pose or robot.last_pose,
            "alarms": alarms,
            "has_alarm": has_alarm,
            "rail": rail_telemetry,
            "safety": robot.safety_limits
        })
    else:
        # Nếu đang di chuyển ray hoặc homing (kể cả mô phỏng), gửi liên tục mỗi chu kỳ 50ms; nếu nghỉ thì gửi mỗi 20 chu kỳ (~1s)
        if not robot.rail_is_moving and not robot.rail_is_homing and (poll_counter % 20 != 0):
            return
        msg = json.dumps({
            "type": "pose",
            "connected": False,
            "port": "Chưa kết nối",
            "alarms": [],
            "has_alarm": False,
            "rail": rail_telemetry,
            "safety": robot.safety_limits
        })

    for client in list(connected_clients):
        try:
            client.write_message(msg)
        except Exception:
            connected_clients.discard(client)

        if HAS_WEB_STUDIO and poll_counter % 10 == 0:
            tr_stat = web_trainer.get_status()
            if tr_stat.get("status") in ("preparing", "training", "completed"):
                tr_msg = json.dumps({"type": "train_status", "data": tr_stat})
                for client in list(connected_clients):
                    try:
                        client.write_message(tr_msg)
                    except Exception:
                        pass


# ==============================================================================
# BỘ QUẢN LÝ TIẾN TRÌNH CÔNG CỤ CHUYÊN DỤNG (CAPTURE & AUTO SORT NATIVE TOOLS)
# ==============================================================================
