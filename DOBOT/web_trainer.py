"""
Module Huấn luyện AI (AI Training Worker) cho FabLab AI & Dobot Web Studio:
- Chạy ngầm tiến trình huấn luyện YOLOv8 / YOLO11
- Tự động chuẩn bị tập dữ liệu (gọi generate_yolo_dataset.py)
- Cập nhật tiến độ Epoch, Loss, mAP50 thời gian thực
- Tạo gói zip để xuất lên Google Colab
"""

import os
import sys
import time
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


class WebYOLOTrainer:
    def __init__(self):
        self.lock = threading.Lock()
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
        self.train_thread = None
        self.stop_requested = False

    def log(self, text: str):
        print(f"[AI Trainer] {text}")
        with self.lock:
            self.state["logs"].append(f"[{time.strftime('%H:%M:%S')}] {text}")
            if len(self.state["logs"]) > 200:
                self.state["logs"] = self.state["logs"][-200:]

    def get_status(self) -> dict:
        with self.lock:
            return dict(self.state)

    def stop(self):
        with self.lock:
            if self.state["status"] in ("preparing", "training"):
                self.stop_requested = True
                self.state["status"] = "stopped"
                self.state["message"] = "Đã nhận lệnh dừng huấn luyện."
                self.log("Dừng huấn luyện theo yêu cầu của người dùng.")

    def start(self, base_model="yolov8n.pt", epochs=30, batch=16):
        with self.lock:
            if self.state["status"] in ("preparing", "training"):
                return {"success": False, "error": "Đang có một tiến trình huấn luyện chạy ngầm!"}

            self.stop_requested = False
            self.state["status"] = "preparing"
            self.state["progress"] = 0
            self.state["current_epoch"] = 0
            self.state["total_epochs"] = int(epochs)
            self.state["loss"] = 0.0
            self.state["map50"] = 0.0
            self.state["message"] = "Đang tự động chuẩn bị tập dữ liệu YOLO..."
            self.state["logs"] = []
            self.state["started_at"] = time.time()

        self.train_thread = threading.Thread(
            target=self._run_training_worker,
            args=(base_model, int(epochs), int(batch)),
            daemon=True
        )
        self.train_thread.start()
        return {"success": True, "message": "Bắt đầu huấn luyện!"}

    def _run_training_worker(self, base_model: str, epochs: int, batch: int):
        try:
            self.log(f"Khởi động tiến trình: Base Model={base_model}, Epochs={epochs}, Batch={batch}")

            # 1. Tự động sinh tập dữ liệu YOLO từ dataset_raw
            gen_script = PROJECT_ROOT / "generate_yolo_dataset.py"
            if gen_script.exists():
                self.log("Đang gán nhãn và chia tập Train/Val từ dataset_raw/...")
                res = subprocess.run(
                    [sys.executable, str(gen_script)],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    encoding="utf-8"
                )
                if res.returncode != 0:
                    self.log(f"Lỗi khi chuẩn bị dataset: {res.stderr}")
                    with self.lock:
                        self.state["status"] = "error"
                        self.state["message"] = f"Lỗi sinh dataset: {res.stderr[:100]}"
                    return
                self.log("Chuẩn bị dữ liệu thành công! File data.yaml sẵn sàng.")

            data_yaml = YOLO_DATASET_DIR / "data.yaml"
            if not data_yaml.exists():
                raise FileNotFoundError(f"Không tìm thấy {data_yaml}")

            if self.stop_requested:
                return

            with self.lock:
                self.state["status"] = "training"
                self.state["message"] = "Đang nạp mô hình Ultralytics YOLO..."

            # 2. Import YOLO
            from ultralytics import YOLO
            self.log(f"Nạp mô hình gốc: {base_model}")
            model = YOLO(base_model)

            # Callback để theo dõi tiến độ từng epoch
            trainer_ref = self

            def on_train_epoch_end(trainer):
                if trainer_ref.stop_requested:
                    raise KeyboardInterrupt("Người dùng dừng huấn luyện")

                ep = trainer.epoch + 1
                total = trainer.epochs
                pct = int((ep / total) * 100)

                # Lấy loss từ trainer
                loss = 0.0
                try:
                    loss = float(trainer.loss_items[0]) if hasattr(trainer, 'loss_items') and trainer.loss_items is not None else 0.0
                except Exception:
                    pass

                elapsed = time.time() - trainer_ref.state["started_at"]
                eta = int((elapsed / max(1, ep)) * (total - ep))

                with trainer_ref.lock:
                    trainer_ref.state["current_epoch"] = ep
                    trainer_ref.state["progress"] = pct
                    trainer_ref.state["loss"] = round(loss, 4)
                    trainer_ref.state["eta_seconds"] = eta
                    trainer_ref.state["message"] = f"Đang huấn luyện Epoch {ep}/{total} ({pct}%) - Loss: {loss:.4f}"

                trainer_ref.log(f"Epoch {ep}/{total} hoàn tất | Loss: {loss:.4f} | Còn lại ~{eta}s")

            def on_fit_epoch_end(trainer):
                try:
                    metrics = trainer.metrics
                    if metrics and "metrics/mAP50(B)" in metrics:
                        val = float(metrics["metrics/mAP50(B)"])
                        with trainer_ref.lock:
                            trainer_ref.state["map50"] = round(val, 4)
                except Exception:
                    pass

            model.add_callback("on_train_epoch_end", on_train_epoch_end)
            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

            # 3. Chạy huấn luyện
            self.log("Bắt đầu vòng lặp huấn luyện chính...")
            results = model.train(
                data=str(data_yaml),
                epochs=epochs,
                imgsz=640,
                batch=batch,
                name="web_studio_train",
                exist_ok=True,
                verbose=False
            )

            # 4. Lưu kết quả tốt nhất
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            trained_best = PROJECT_ROOT / "runs" / "detect" / "web_studio_train" / "weights" / "best.pt"
            dest_best = MODELS_DIR / "best_trained.pt"

            if trained_best.exists():
                shutil.copy2(str(trained_best), str(dest_best))
                self.log(f"Đã lưu mô hình tốt nhất vào: {dest_best}")

            with self.lock:
                self.state["status"] = "completed"
                self.state["progress"] = 100
                self.state["best_model"] = str(dest_best)
                self.state["message"] = "🎉 Huấn luyện thành công! Mô hình đã sẵn sàng gắp thả."
            self.log("Huấn luyện thành công 100%!")

        except KeyboardInterrupt:
            self.log("Đã dừng tiến trình huấn luyện.")
            with self.lock:
                self.state["status"] = "stopped"
                self.state["message"] = "Tiến trình đã được dừng."
        except Exception as e:
            self.log(f"Lỗi trong quá trình train: {e}")
            with self.lock:
                self.state["status"] = "error"
                self.state["message"] = f"Lỗi: {str(e)[:120]}"

    def export_colab_zip(self) -> dict:
        """Nén thư mục yolo_dataset thành file zip sẵn sàng tải về."""
        try:
            # Chạy generate_yolo_dataset trước nếu cần
            gen_script = PROJECT_ROOT / "generate_yolo_dataset.py"
            if gen_script.exists():
                subprocess.run([sys.executable, str(gen_script)], cwd=str(PROJECT_ROOT), capture_output=True)

            if not YOLO_DATASET_DIR.exists():
                return {"success": False, "error": "Chưa có dữ liệu yolo_dataset!"}

            # Nén thành file zip
            zip_base = str(PROJECT_ROOT / "yolo_dataset")
            shutil.make_archive(zip_base, "zip", root_dir=str(YOLO_DATASET_DIR))

            if COLAB_ZIP_PATH.exists():
                size_mb = COLAB_ZIP_PATH.stat().st_size / (1024 * 1024)
                return {
                    "success": True,
                    "filename": "yolo_dataset.zip",
                    "path": str(COLAB_ZIP_PATH),
                    "size_mb": round(size_mb, 2)
                }
            return {"success": False, "error": "Không tạo được file zip"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton instance
web_trainer = WebYOLOTrainer()
