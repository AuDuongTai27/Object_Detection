#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import tornado.web
from backend.context import (
    HAS_WEB_STUDIO, web_trainer, kaggle_trainer,
    COLAB_ZIP_PATH, MODELS_DIR
)

class ApiTrainStartHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not HAS_WEB_STUDIO:
            self.write({"success": False, "error": "Module huấn luyện chưa sẵn sàng"})
            return

        try:
            data = json.loads(self.request.body)
            model_name = data.get("model") or data.get("model_name", "yolov8n.pt")
            epochs = int(data.get("epochs", 30))
            batch = int(data.get("batch", 16))
            output_model_name = data.get("output_model_name") or data.get("output_name") or "best_trained.pt"
            res = web_trainer.start(base_model=model_name, epochs=epochs, batch=batch, output_model_name=output_model_name)
            res["status"] = "ok" if res.get("success") else "error"
            self.write(res)
        except Exception as e:
            self.write({"status": "error", "success": False, "error": str(e), "message": str(e)})


class ApiTrainStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if HAS_WEB_STUDIO:
            self.write(web_trainer.get_status())
        else:
            self.write({"status": "idle"})


class ApiTrainStopHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def post(self):
        if HAS_WEB_STUDIO:
            web_trainer.stop()
            self.write({"status": "ok", "success": True, "message": "Đã gửi lệnh dừng tiến trình huấn luyện thành công!"})
        else:
            self.write({"status": "error", "success": False, "message": "Chưa hỗ trợ"})


class ApiTrainExportColabHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    async def post(self):
        if HAS_WEB_STUDIO:
            loop = tornado.ioloop.IOLoop.current()
            res = await loop.run_in_executor(None, web_trainer.export_colab_zip)
            if res.get("success"):
                res["status"] = "ok"
                res["download_url"] = "/api/train/download_zip"
                res["zip_name"] = res.get("filename", "yolo_dataset.zip")
            else:
                res["status"] = "error"
                res["message"] = res.get("error", "Lỗi tạo file zip")
            self.write(res)
        else:
            self.write({"status": "error", "success": False, "message": "Chưa hỗ trợ"})


class ApiTrainDownloadZipHandler(tornado.web.RequestHandler):
    def get(self):
        if COLAB_ZIP_PATH.exists():
            self.set_header('Content-Type', 'application/zip')
            self.set_header('Content-Disposition', 'attachment; filename="yolo_dataset.zip"')
            with open(COLAB_ZIP_PATH, 'rb') as f:
                self.write(f.read())
        else:
            self.set_status(404)
            self.write("Chưa có file zip. Hãy bấm xuất gói trước.")


class ApiKaggleCredsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def get(self):
        if kaggle_trainer:
            self.write(kaggle_trainer.get_credentials())
        else:
            self.write({"configured": False, "error": "Module Kaggle chưa sẵn sàng"})

    def post(self):
        if not kaggle_trainer:
            self.write({"success": False, "error": "Module Kaggle chưa sẵn sàng"})
            return
        try:
            data = json.loads(self.request.body)
            username = data.get("username", "")
            key = data.get("key", "")
            res = kaggle_trainer.save_credentials(username, key)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiKaggleStartHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        if not kaggle_trainer:
            self.write({"success": False, "error": "Module Kaggle chưa sẵn sàng"})
            return
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            model_name = data.get("model") or data.get("model_name", "yolo11n.pt")
            epochs = int(data.get("epochs", 30))
            batch = int(data.get("batch", 16))
            output_model_name = data.get("output_model_name") or data.get("output_name") or "best_trained.pt"
            res = kaggle_trainer.start(base_model=model_name, epochs=epochs, batch=batch, output_model_name=output_model_name)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiKaggleStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        if kaggle_trainer:
            self.write(kaggle_trainer.get_status())
        else:
            self.write({"status": "idle"})


class ApiKaggleStopHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def post(self):
        if kaggle_trainer:
            kaggle_trainer.stop()
            self.write({"success": True, "message": "Đã gửi lệnh dừng tiến trình Cloud GPU!"})
        else:
            self.write({"success": False, "error": "Chưa hỗ trợ"})
