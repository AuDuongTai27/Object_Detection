#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import tornado.web
from pathlib import Path
from backend.context import BASE_DIR

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Pragma", "no-cache")
        self.set_header("Expires", "0")
        file_path = os.path.join(BASE_DIR, "dobot_visualizer.html")
        with open(file_path, "r", encoding="utf-8") as f:
            self.write(f.read())


class StaticFileHandler(tornado.web.RequestHandler):
    def get(self, filename):
        file_path = os.path.join(BASE_DIR, filename)
        if os.path.exists(file_path):
            if filename.endswith(".js"):
                self.set_header("Content-Type", "application/javascript")
            elif filename.endswith(".css"):
                self.set_header("Content-Type", "text/css")
            elif filename.endswith(".ico"):
                self.set_header("Content-Type", "image/x-icon")
            elif filename.endswith(".png"):
                self.set_header("Content-Type", "image/png")
            elif filename.endswith(".svg"):
                self.set_header("Content-Type", "image/svg+xml")
            elif filename.endswith(".json"):
                self.set_header("Content-Type", "application/json")
            with open(file_path, "rb") as f:
                self.write(f.read())
        else:
            self.set_status(404)
