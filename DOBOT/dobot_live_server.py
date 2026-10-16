#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dobot Magician Live Digital Twin Server (Bản sao số 3D thời gian thực)
Kiến trúc Module Hóa Chuẩn (Modular Clean Architecture)
"""

import os
import sys
import webbrowser
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import tornado.ioloop
import tornado.web

# Nạp context Singleton & Hàm định kỳ
from backend.context import robot, poll_robot_pose, BASE_DIR

# Nạp các Handler theo module
from backend.handlers.base_handlers import MainHandler, StaticFileHandler
from backend.handlers.robot_handlers import (
    WebSocketHandler, ApiCmdHandler, ApiRobotConnectHandler,
    ApiRobotDisconnectHandler, ApiRobotPortsHandler, ApiWorkspaceSafetyHandler
)
from backend.handlers.tool_handlers import (
    ApiToolLaunchHandler, ApiToolStopHandler, ApiToolStatusHandler
)
from backend.handlers.dataset_handlers import (
    ApiCameraHandler, ApiDatasetStatsHandler, ApiDatasetCaptureHandler,
    ApiDatasetDeleteHandler, ApiDatasetAddClassHandler, ApiDatasetRecentHandler,
    DatasetImageHandler
)
from backend.handlers.training_handlers import (
    ApiTrainStartHandler, ApiTrainStatusHandler, ApiTrainStopHandler,
    ApiTrainExportColabHandler, ApiTrainDownloadZipHandler,
    ApiKaggleCredsHandler, ApiKaggleStartHandler, ApiKaggleStatusHandler,
    ApiKaggleStopHandler
)
from backend.handlers.vision_handlers import (
    VideoWsHandler, ApiVisionStatusHandler, ApiVisionPickHandler,
    ApiVisionAutoSortHandler, ApiVisionModelsHandler,
    ApiDropTargetsHandler, ApiCalibInfoHandler, ApiVoiceConfigHandler
)
from backend.handlers.blockly_ai_handler import (
    ApiBlocklyAiCredsHandler, ApiBlocklyAiGenerateHandler
)

def find_available_port(preferred_port=8080):
    import socket
    for p in [preferred_port, 8081, 8082, 8088]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', p))
            s.close()
            return p
        except OSError:
            continue
    return preferred_port


def main():
    preferred = int(os.environ.get("PORT", 8080))
    port = find_available_port(preferred)
    app = tornado.web.Application([
        (r"/", MainHandler),
        (r"/dobot_visualizer.html", MainHandler),
        (r"/index.html", MainHandler),
        (r"/ws", WebSocketHandler),
        (r"/api/cmd", ApiCmdHandler),
        (r"/api/state", ApiCmdHandler),
        (r"/api/robot/connect", ApiRobotConnectHandler),
        (r"/api/robot/disconnect", ApiRobotDisconnectHandler),
        (r"/api/robot/ports", ApiRobotPortsHandler),
        (r"/js/(.*)", tornado.web.StaticFileHandler, {"path": str(BASE_DIR / "js")}),
        (r"/css/(.*)", tornado.web.StaticFileHandler, {"path": str(BASE_DIR / "css")}),
        (r"/(.*\.(?:js|css|ico|png|svg|json))", StaticFileHandler),
        # Web Studio Streaming & APIs
        (r"/ws/video", VideoWsHandler),
        (r"/api/tool/launch", ApiToolLaunchHandler),
        (r"/api/tool/stop", ApiToolStopHandler),
        (r"/api/tool/status", ApiToolStatusHandler),
        (r"/api/camera", ApiCameraHandler),
        (r"/api/dataset/stats", ApiDatasetStatsHandler),
        (r"/api/dataset/capture", ApiDatasetCaptureHandler),
        (r"/api/dataset/delete", ApiDatasetDeleteHandler),
        (r"/api/dataset/add_class", ApiDatasetAddClassHandler),
        (r"/api/dataset/recent", ApiDatasetRecentHandler),
        (r"/api/dataset/image/(.*)", DatasetImageHandler),
        (r"/api/train/start", ApiTrainStartHandler),
        (r"/api/train/status", ApiTrainStatusHandler),
        (r"/api/train/stop", ApiTrainStopHandler),
        (r"/api/train/export_colab", ApiTrainExportColabHandler),
        (r"/api/train/download_zip", ApiTrainDownloadZipHandler),
        (r"/api/train/kaggle/creds", ApiKaggleCredsHandler),
        (r"/api/train/kaggle/start", ApiKaggleStartHandler),
        (r"/api/train/kaggle/status", ApiKaggleStatusHandler),
        (r"/api/train/kaggle/stop", ApiKaggleStopHandler),
        (r"/api/vision/status", ApiVisionStatusHandler),
        (r"/api/vision/pick", ApiVisionPickHandler),
        (r"/api/vision/auto_sort", ApiVisionAutoSortHandler),
        (r"/api/vision/models", ApiVisionModelsHandler),
        (r"/api/vision/drop_targets", ApiDropTargetsHandler),
        (r"/api/vision/voice_config", ApiVoiceConfigHandler),
        (r"/api/calib/info", ApiCalibInfoHandler),
        (r"/api/blockly/ai/creds", ApiBlocklyAiCredsHandler),
        (r"/api/blockly/ai/generate", ApiBlocklyAiGenerateHandler),
        (r"/api/workspace/safety", ApiWorkspaceSafetyHandler),
        (r"/dobot_description/(.*)", tornado.web.StaticFileHandler, {"path": str(BASE_DIR / "dobot_description")}),
    ])
    
    app.listen(port, address="0.0.0.0")
    print("=" * 60)
    print(f"  DOBOT MAGICIAN 3D LIVE DIGITAL TWIN SERVER")
    print(f"  Giao diện Web: http://localhost:{port}")
    print("=" * 60)
    print("[*] Dobot Magician: Chế độ kết nối qua Web UI (Bấm nút 'Kết Nối Dobot' khi cắm USB)")

    # Tần số đọc 50ms (~20 lần/giây)
    tornado.ioloop.PeriodicCallback(poll_robot_pose, 50).start()

    # Tự động mở trình duyệt web khi máy chủ đã sẵn sàng
    import webbrowser
    def _open_browser_auto():
        target_url = f"http://localhost:{port}/dobot_visualizer.html"
        print(f"[*] Dang tu dong mo trinh duyet: {target_url}")
        try:
            webbrowser.open(target_url)
        except Exception as e:
            print(f"[-] Khong the tu mo trinh duyet: {e}")

    tornado.ioloop.IOLoop.current().call_later(0.8, _open_browser_auto)

    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print("\n[!] Dừng server.")


if __name__ == "__main__":
    main()
