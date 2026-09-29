"""
Module Huấn luyện AI (AI Training Worker) cho FabLab AI & Dobot Web Studio:
- Chạy ngầm tiến trình huấn luyện YOLOv8 / YOLO11 qua SUBPROCESS riêng biệt (train_worker.py)
- Hoàn toàn độc lập với luồng chính của Tornado Web Server
- Khi người dùng ấn Dừng (Stop), kill sạch tiến trình và các DataLoader con mà KHÔNG làm đơ hay tắt server
- Tự động chuẩn bị tập dữ liệu (gọi generate_yolo_dataset.py) nếu chưa có data.yaml
- Cập nhật tiến độ Epoch, Loss, mAP50 thời gian thực
- Tạo gói zip để xuất lên Google Colab
"""

import os
import sys
import time
import json
import shutil
import threading
import subprocess
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
MODELS_DIR = PROJECT_ROOT / "models"
YOLO_DATASET_DIR = PROJECT_ROOT / "yolo_dataset"
COLAB_ZIP_PATH = PROJECT_ROOT / "yolo_dataset.zip"
TRAIN_WORKER_SCRIPT = BASE_DIR / "train_worker.py"


class WebYOLOTrainer:
    def __init__(self):
        self.lock = threading.RLock()
        self.state = {
            "status": "idle",       # idle, preparing, training, completed, error, stopped
            "progress": 0,          # 0 - 100
            "current_epoch": 0,
            "total_epochs": 30,
            "loss": 0.0,
            "map50": 0.0,
            "message": "Hệ thống sẵn sàng huấn luyện.",
            "logs": [],
            "best_model": "",
            "started_at": 0,
            "eta_seconds": 0
        }
        self.process = None
        self.worker_thread = None
        self.stop_requested = False

    def log(self, text: str):
        print(f"[AI Trainer] {text}", flush=True)
        with self.lock:
            self.state["logs"].append(f"[{time.strftime('%H:%M:%S')}] {text}")
            if len(self.state["logs"]) > 200:
                self.state["logs"] = self.state["logs"][-200:]

    def get_status(self) -> dict:
        with self.lock:
            st = dict(self.state)
            st["progress_pct"] = st.get("progress", 0)
            st["current_loss"] = st.get("loss", 0.0)
            st["current_map50"] = st.get("map50", 0.0)
            eta_s = st.get("eta_seconds", 0)
            if eta_s > 0:
                mins = eta_s // 60
                secs = eta_s % 60
                st["eta"] = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            else:
                st["eta"] = "--"
            return st

    def stop(self):
        with self.lock:
            self.stop_requested = True
            proc = self.process
            if proc is not None and proc.poll() is None:
                self.state["status"] = "stopped"
                self.state["message"] = "Đang dừng tiến trình huấn luyện..."
                self.log("Nhận lệnh dừng huấn luyện từ người dùng.")
                try:
                    if sys.platform == "win32":
                        # taskkill /F /T tiêu diệt toàn bộ cây tiến trình (bao gồm các DataLoader con của PyTorch)
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                            timeout=5
                        )
                    else:
                        proc.terminate()
                except Exception as e:
                    self.log(f"Lỗi khi dừng tiến trình: {e}")
                
                self.state["message"] = "Đã dừng tiến trình huấn luyện thành công."
                self.log("Đã dừng tiến trình huấn luyện thành công!")
                self.process = None
            else:
                self.state["status"] = "stopped"
                self.state["message"] = "Tiến trình huấn luyện không hoạt động."
                self.process = None

    def start(self, base_model="yolov8n.pt", epochs=30, batch=16):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return {"success": False, "error": "Đang có một tiến trình huấn luyện chạy ngầm!"}

            self.stop_requested = False
            self.state["status"] = "preparing"
            self.state["progress"] = 0
            self.state["current_epoch"] = 0
            self.state["total_epochs"] = int(epochs)
            self.state["loss"] = 0.0
            self.state["map50"] = 0.0
            self.state["message"] = "Đang kiểm tra và chuẩn bị dữ liệu YOLO..."
            self.state["logs"] = []
            self.state["started_at"] = time.time()
            self.state["eta_seconds"] = 0

        self.worker_thread = threading.Thread(
            target=self._run_training_pipeline,
            args=(base_model, int(epochs), int(batch)),
            daemon=True
        )
        self.worker_thread.start()
        return {"success": True, "message": "Bắt đầu huấn luyện!"}

    def _run_training_pipeline(self, base_model: str, epochs: int, batch: int):
        try:
            self.log(f"Khởi động tiến trình: Base Model={base_model}, Epochs={epochs}, Batch={batch}")

            # 1. Tự động sinh tập dữ liệu YOLO từ dataset_raw nếu chưa có
            data_yaml = YOLO_DATASET_DIR / "data.yaml"
            gen_script = PROJECT_ROOT / "generate_yolo_dataset.py"

            if not data_yaml.exists() and gen_script.exists():
                self.log("Đang gán nhãn và chia tập Train/Val từ dataset_raw/...")
                with self.lock:
                    self.state["message"] = "Đang tự động gán nhãn và tạo data.yaml..."

                gen_proc = subprocess.Popen(
                    [sys.executable, str(gen_script), "--train-count", "200", "--val-count", "50"],
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8"
                )
                self.process = gen_proc

                for line in iter(gen_proc.stdout.readline, ''):
                    if not line:
                        break
                    l = line.strip()
                    if l:
                        self.log(f"[Dataset] {l}")
                    if self.stop_requested:
                        try:
                            if sys.platform == "win32":
                                subprocess.run(["taskkill", "/F", "/T", "/PID", str(gen_proc.pid)], capture_output=True)
                            else:
                                gen_proc.terminate()
                        except Exception:
                            pass
                        return

                gen_proc.wait()
                if gen_proc.returncode != 0:
                    self.log(f"Lỗi khi chuẩn bị dataset (exit code {gen_proc.returncode})")
                    with self.lock:
                        if self.state["status"] != "stopped":
                            self.state["status"] = "error"
                            self.state["message"] = "Lỗi khi sinh dataset YOLO"
                    return
                self.log("Chuẩn bị dữ liệu thành công! File data.yaml sẵn sàng.")
            else:
                self.log("Tập dữ liệu data.yaml đã có sẵn.")

            if self.stop_requested:
                return

            if not data_yaml.exists():
                raise FileNotFoundError(f"Không tìm thấy file {data_yaml}")

            with self.lock:
                self.state["status"] = "training"
                self.state["message"] = "Khởi chạy tiến trình Train Worker độc lập..."

            # 2. Khởi chạy standalone train_worker.py dưới dạng subprocess riêng
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            dest_best = MODELS_DIR / "best_trained.pt"

            cmd = [
                sys.executable, "-u", str(TRAIN_WORKER_SCRIPT),
                "--base-model", str(base_model),
                "--epochs", str(epochs),
                "--batch", str(batch),
                "--data-yaml", str(data_yaml),
                "--output-model", str(dest_best),
                "--project-root", str(PROJECT_ROOT)
            ]

            self.log(f"Chạy lệnh Subprocess: {' '.join(cmd)}")
            train_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                cwd=str(PROJECT_ROOT)
            )
            self.process = train_proc

            # Đọc log và JSON_STATUS theo thời gian thực từ stdout của worker
            for raw_line in iter(train_proc.stdout.readline, ''):
                if not raw_line:
                    break
                line = raw_line.strip()
                if not line:
                    continue

                if line.startswith("JSON_STATUS:"):
                    try:
                        data = json.loads(line[len("JSON_STATUS:"):])
                        st_type = data.get("type")
                        with self.lock:
                            if st_type == "epoch":
                                self.state["current_epoch"] = data.get("epoch", self.state["current_epoch"])
                                self.state["total_epochs"] = data.get("total_epochs", self.state["total_epochs"])
                                self.state["progress"] = data.get("progress", self.state["progress"])
                                self.state["loss"] = data.get("loss", self.state["loss"])
                                self.state["eta_seconds"] = data.get("eta_seconds", 0)
                                if "message" in data:
                                    self.state["message"] = data["message"]
                            elif st_type == "metrics":
                                self.state["map50"] = data.get("map50", self.state["map50"])
                            elif st_type == "status":
                                self.state["message"] = data.get("message", self.state["message"])
                            elif st_type == "completed":
                                self.state["status"] = "completed"
                                self.state["progress"] = 100
                                self.state["best_model"] = data.get("best_model", str(dest_best))
                                self.state["message"] = data.get("message", "Huấn luyện thành công!")
                            elif st_type == "error":
                                if self.state["status"] != "stopped":
                                    self.state["status"] = "error"
                                    self.state["message"] = data.get("message", "Lỗi huấn luyện")
                    except Exception as e:
                        pass
                else:
                    self.log(line)

            ret_code = train_proc.wait()
            self.log(f"Tiến trình Train Worker kết thúc với mã {ret_code}.")

            with self.lock:
                if self.state["status"] == "stopped" or self.stop_requested:
                    self.state["status"] = "stopped"
                    self.state["message"] = "Đã dừng tiến trình huấn luyện."
                elif ret_code == 0:
                    self.state["status"] = "completed"
                    self.state["progress"] = 100
                    self.state["best_model"] = str(dest_best)
                    self.state["message"] = "🎉 Huấn luyện thành công! Mô hình đã sẵn sàng gắp thả."
                else:
                    if self.state["status"] != "error":
                        self.state["status"] = "error"
                        self.state["message"] = f"Tiến trình huấn luyện kết thúc với mã lỗi ({ret_code})"

        except Exception as e:
            self.log(f"Lỗi ngoài dự kiến trong worker pipeline: {e}")
            with self.lock:
                if self.state["status"] != "stopped":
                    self.state["status"] = "error"
                    self.state["message"] = f"Lỗi: {str(e)[:120]}"
        finally:
            with self.lock:
                self.process = None

    def export_colab_zip(self) -> dict:
        """Nén thư mục yolo_dataset thành file zip sẵn sàng tải về."""
        try:
            # Chỉ sinh dataset nếu chưa có data.yaml
            data_yaml = YOLO_DATASET_DIR / "data.yaml"
            gen_script = PROJECT_ROOT / "generate_yolo_dataset.py"
            if not data_yaml.exists() and gen_script.exists():
                subprocess.run([sys.executable, str(gen_script), "--train-count", "500", "--val-count", "100"], cwd=str(PROJECT_ROOT), capture_output=True)

            if not YOLO_DATASET_DIR.exists():
                return {"success": False, "status": "error", "error": "Chưa có dữ liệu yolo_dataset!", "message": "Chưa có dữ liệu yolo_dataset!"}

            # Nén thành file zip
            zip_base = str(PROJECT_ROOT / "yolo_dataset")
            shutil.make_archive(zip_base, "zip", root_dir=str(YOLO_DATASET_DIR))

            if COLAB_ZIP_PATH.exists():
                size_mb = COLAB_ZIP_PATH.stat().st_size / (1024 * 1024)
                return {
                    "success": True,
                    "status": "ok",
                    "filename": "yolo_dataset.zip",
                    "zip_name": "yolo_dataset.zip",
                    "download_url": "/api/train/download_zip",
                    "path": str(COLAB_ZIP_PATH),
                    "size_mb": round(size_mb, 2)
                }
            return {"success": False, "status": "error", "error": "Không tạo được file zip", "message": "Không tạo được file zip"}
        except Exception as e:
            return {"success": False, "status": "error", "error": str(e), "message": str(e)}


# Singleton instance
web_trainer = WebYOLOTrainer()
