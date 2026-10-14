#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import tornado.web
from backend.context import (
    HAS_WEB_STUDIO, vision_engine, get_dataset_stats, save_captured_frame,
    delete_captured_image, add_new_class, get_recent_captures,
    DATASET_RAW_DIR
)

class ApiCameraHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        # Trả về ngay danh sách camera khả dụng mà không mở lại thiết bị đang quay
        if HAS_WEB_STUDIO and vision_engine:
            devices = vision_engine.get_camera_devices()
            status = vision_engine.get_status()
            active_cam = vision_engine.cam_id if devices else None
            is_cam_open = status.get("camera_online", False)
        else:
            devices = []
            active_cam = None
            is_cam_open = False

        self.write({
            "status": "ok",
            "success": True,
            "devices": devices,
            "available_cameras": devices,
            "active_cam": active_cam,
            "current_cam": active_cam,
            "camera_online": is_cam_open,
            "is_opened": is_cam_open
        })

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            if data.get("refresh", False) and HAS_WEB_STUDIO and vision_engine:
                # Quét lại danh sách camera
                cams = vision_engine.scan_cameras()
                self.write({"status": "ok", "success": True, "devices": cams, "available_cameras": cams})
            elif "cam_id" in data and HAS_WEB_STUDIO and vision_engine:
                ok = vision_engine.start_camera(int(data["cam_id"]))
                self.write({"status": "ok", "success": ok, "cam_id": vision_engine.cam_id})
            else:
                self.write({"status": "error", "success": False, "error": "Tham số không hợp lệ"})
        except Exception as e:
            self.write({"status": "error", "success": False, "error": str(e)})


class ApiDatasetStatsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO:
            self.write(get_dataset_stats())
        else:
            self.write({"classes": {}, "total_images": 0})


class ApiDatasetCaptureHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO or not vision_engine:
            self.write({"success": False, "error": "Vision Engine chưa khởi động"})
            return

        try:
            data = json.loads(self.request.body)
            class_name = data.get("class_name", "cube_red")
            frame = vision_engine.get_raw_frame()
            if frame is None:
                self.write({"success": False, "error": "Chưa nhận được frame từ Camera"})
                return

            res = save_captured_frame(class_name, frame)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiDatasetDeleteHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body)
            res = delete_captured_image(data.get("class_name", ""), data.get("filename", ""))
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiDatasetAddClassHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body)
            res = add_new_class(data.get("class_name", ""))
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiDatasetRecentHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO:
            self.write({"images": get_recent_captures(limit=16)})
        else:
            self.write({"images": []})


class DatasetImageHandler(tornado.web.RequestHandler):
    def get(self, path):
        full_path = os.path.join(str(DATASET_RAW_DIR), path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            self.set_header("Content-Type", "image/jpeg")
            with open(full_path, "rb") as f:
                self.write(f.read())
        else:
            self.set_status(404)
