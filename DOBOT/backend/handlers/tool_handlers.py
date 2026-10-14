#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import tornado.web
from backend.context import tool_manager

class ApiToolLaunchHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            tool_name = data.get("tool", "capture")
            res = tool_manager.launch(tool_name, **data)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiToolStopHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def post(self):
        try:
            data = json.loads(self.request.body) if self.request.body else {}
            tool_name = data.get("tool", None)
            res = tool_manager.stop(tool_name)
            self.write(res)
        except Exception as e:
            self.write({"success": False, "error": str(e)})


class ApiToolStatusHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        self.write(tool_manager.get_status())


# ==============================================================================
# BỘ XỬ LÝ VIDEO & WEB STUDIO APIS (CAMERA, DATASET, TRAINER, AUTO SORT)
# ==============================================================================
