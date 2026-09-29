"""
Module Huấn luyện AI (AI Training Worker) cho FabLab AI & Dobot Web Studio:
- Chạy ngầm tiến trình huấn luyện YOLOv8 / YOLO11 qua SUBPROCESS riêng biệt (train_worker.py)
- Hoàn toàn độc lập với luồng chính của Tornado Web Server
- Tự động đồng bộ đường dẫn path trong data.yaml trên mọi máy tính (laptop, máy GPU FabLab)
- Tự động nhận diện ảnh mới từ dataset_raw để sinh dataset cập nhật
- Hiển thị log súc tích, chuyên nghiệp: tổng quát 1 dòng sau mỗi Epoch
- Tự động nạp mô hình mới nhất vào Tab 4 (AI Vision) sau khi huấn luyện xong
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


def sync_data_yaml_path(data_yaml_path: Path):
    """Đồng bộ trường path: trong data.yaml theo thư mục máy tính hiện tại."""
    try:
        yaml_dir = data_yaml_path.parent.resolve().as_posix()
        lines = []
        path_found = False
        with open(data_yaml_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("path:"):
                    lines.append(f"path: {yaml_dir}\n")
                    path_found = True
                else:
                    lines.append(line)
        if not path_found:
            lines.insert(0, f"path: {yaml_dir}\n")
        with open(data_yaml_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"[AI Trainer] Lỗi đồng bộ data.yaml: {e}")


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
            "precision": 0.0,
            "recall": 0.0,
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
            if len(self.state["logs"]) > 100:
                self.state["logs"] = self.state["logs"][-100:]

    def get_status(self) -> dict:
        with self.lock:
            st = dict(self.state)
            st["progress_pct"] = st.get("progress", 0)
            st["current_loss"] = st.get("loss", 0.0)
            st["current_map50"] = st.get("map50", 0.0)
            st["current_precision"] = st.get("precision", 0.0)
            st["current_recall"] = st.get("recall", 0.0)
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
                self.log("🛑 Nhận lệnh dừng huấn luyện từ người dùng.")
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
                self.log("🛑 Đã dừng tiến trình huấn luyện thành công!")
                self.process = None
            else:
                self.state["status"] = "stopped"
                self.state["message"] = "Tiến trình huấn luyện không hoạt động."
                self.process = None

    def start(self, base_model="yolov8n.pt", epochs=30, batch=16, output_model_name="best_trained.pt"):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return {"success": False, "error": "Đang có một tiến trình huấn luyện chạy ngầm!"}

            # Chuẩn hóa tên file mô hình xuất ra
            clean_name = str(output_model_name).strip() if output_model_name else "best_trained.pt"
            clean_name = Path(clean_name).name
            if not clean_name.lower().endswith(".pt"):
                clean_name += ".pt"

            self.stop_requested = False
            self.state["status"] = "preparing"
            self.state["progress"] = 0
            self.state["current_epoch"] = 0
            self.state["total_epochs"] = int(epochs)
            self.state["loss"] = 0.0
            self.state["map50"] = 0.0
            self.state["output_model_name"] = clean_name
            self.state["message"] = f"Đang chuẩn bị dữ liệu (Mô hình: {clean_name})..."
            self.state["logs"] = []
            self.state["started_at"] = time.time()
            self.state["eta_seconds"] = 0

        self.worker_thread = threading.Thread(
            target=self._run_training_pipeline,
            args=(base_model, int(epochs), int(batch), clean_name),
            daemon=True
        )
        self.worker_thread.start()
        return {"success": True, "message": f"Bắt đầu huấn luyện (Lưu thành {clean_name})!"}

    def _run_training_pipeline(self, base_model: str, epochs: int, batch: int, output_model_name: str = "best_trained.pt"):
        try:
            self.log(f"🚀 Bắt đầu phiên huấn luyện: Model={base_model} | Epochs={epochs} | Batch={batch} | Lưu={output_model_name}")

            # 1. Tự động kiểm tra và đồng bộ tập dữ liệu YOLO từ dataset_raw
            data_yaml = YOLO_DATASET_DIR / "data.yaml"
            gen_script = PROJECT_ROOT / "generate_yolo_dataset.py"
            train_img_dir = YOLO_DATASET_DIR / "images" / "train"

            # Kiểm tra xem có cần sinh lại dataset hay không
            need_generate = (
                not data_yaml.exists()
                or not train_img_dir.exists()
                or len(list(train_img_dir.glob("*.jpg"))) == 0
            )

            # Kiểm tra nếu dataset_raw có ảnh mới chụp gần đây hơn file data.yaml
            if not need_generate and data_yaml.exists():
                try:
                    yaml_mtime = data_yaml.stat().st_mtime
                    raw_dir = PROJECT_ROOT / "dataset_raw"
                    if raw_dir.exists():
                        for p in raw_dir.rglob("*.jpg"):
                            if p.stat().st_mtime > yaml_mtime:
                                need_generate = True
                                self.log(f"📦 Phát hiện ảnh mới từ dataset_raw ({p.name}), đang cập nhật dataset...")
                                break
                except Exception:
                    pass

            if need_generate and gen_script.exists():
                self.log("📦 Đang tổng hợp ảnh huấn luyện (trộn nền, gán nhãn, tăng cường dữ liệu)...")
                with self.lock:
                    self.state["message"] = "Đang gán nhãn và tạo tập dữ liệu YOLO..."

                gen_proc = subprocess.Popen(
                    [sys.executable, str(gen_script), "--train-count", "300", "--val-count", "60"],
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
                    if l.startswith("[*] Đã") or l.startswith(" - Tổng ảnh"):
                        self.log(l)
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
                    self.log(f"❌ Lỗi khi chuẩn bị dataset (exit code {gen_proc.returncode})")
                    with self.lock:
                        if self.state["status"] != "stopped":
                            self.state["status"] = "error"
                            self.state["message"] = "Lỗi khi sinh dataset YOLO"
                    return
                self.log("✅ Chuẩn bị dữ liệu hoàn tất! Tập data.yaml đã sẵn sàng.")
            else:
                self.log("✅ Dữ liệu yolo_dataset đã sẵn sàng.")

            if self.stop_requested:
                return

            if not data_yaml.exists():
                raise FileNotFoundError(f"Không tìm thấy file {data_yaml}")

            # Đảm bảo đường dẫn data.yaml tương thích 100% với máy này
            sync_data_yaml_path(data_yaml)

            with self.lock:
                self.state["status"] = "training"
                self.state["message"] = "Khởi chạy tiến trình Train Worker..."

            # 2. Khởi chạy standalone train_worker.py dưới dạng subprocess riêng
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            dest_best = MODELS_DIR / output_model_name

            # Nếu mô hình đích đã tồn tại thì xóa trước để đảm bảo ghi đè
            if dest_best.exists():
                try:
                    dest_best.unlink()
                    self.log(f"🔄 Đã xóa mô hình cũ '{dest_best.name}' để ghi đè bản mới.")
                except Exception as e_del:
                    self.log(f"⚠️ Chú ý khi ghi đè file '{dest_best.name}': {e_del}")

            cmd = [
                sys.executable, "-u", str(TRAIN_WORKER_SCRIPT),
                "--base-model", str(base_model),
                "--epochs", str(epochs),
                "--batch", str(batch),
                "--data-yaml", str(data_yaml),
                "--output-model", str(dest_best),
                "--project-root", str(PROJECT_ROOT)
            ]

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
                            if st_type == "device":
                                dev_msg = data.get("message", "")
                                self.state["message"] = dev_msg
                                self.log(f"💻 {dev_msg}")

                            elif st_type == "epoch":
                                self.state["current_epoch"] = data.get("epoch", self.state["current_epoch"])
                                self.state["total_epochs"] = data.get("total_epochs", self.state["total_epochs"])
                                self.state["progress"] = data.get("progress", self.state["progress"])
                                self.state["loss"] = data.get("loss", self.state["loss"])
                                self.state["eta_seconds"] = data.get("eta_seconds", 0)
                                if "message" in data:
                                    self.state["message"] = data["message"]

                            elif st_type == "epoch_summary":
                                ep = data.get("epoch", self.state["current_epoch"])
                                tot = data.get("total_epochs", self.state["total_epochs"])
                                loss = data.get("loss", self.state["loss"])
                                map50 = data.get("map50", 0.0)
                                precision = data.get("precision", 0.0)
                                recall = data.get("recall", 0.0)
                                pct = data.get("progress", self.state["progress"])
                                eta_s = data.get("eta_seconds", 0)

                                self.state["current_epoch"] = ep
                                self.state["progress"] = pct
                                self.state["loss"] = loss
                                self.state["map50"] = map50
                                self.state["precision"] = precision
                                self.state["recall"] = recall
                                self.state["eta_seconds"] = eta_s

                                map_str = f"{map50 * 100:.1f}%" if map50 > 0 else "--"
                                p_str = f"{precision * 100:.1f}%" if precision > 0 else "--"
                                r_str = f"{recall * 100:.1f}%" if recall > 0 else "--"
                                summary_text = f"📊 [Epoch {ep}/{tot}] Loss: {loss:.4f} | mAP50: {map_str} | P: {p_str} | R: {r_str} | Tiến độ: {pct}%"
                                self.state["message"] = summary_text
                                self.log(summary_text)

                            elif st_type == "metrics":
                                self.state["map50"] = data.get("map50", self.state["map50"])

                            elif st_type == "status":
                                self.state["message"] = data.get("message", self.state["message"])

                            elif st_type == "completed":
                                self.state["status"] = "completed"
                                self.state["progress"] = 100
                                self.state["best_model"] = data.get("best_model", str(dest_best))
                                self.state["message"] = data.get("message", "Huấn luyện thành công!")
                                self.log(f"🎉 {data.get('message', 'Huấn luyện thành công!')}")

                            elif st_type == "error":
                                if self.state["status"] != "stopped":
                                    self.state["status"] = "error"
                                    self.state["message"] = data.get("message", "Lỗi huấn luyện")
                                    self.log(f"❌ {data.get('message')}")
                    except Exception:
                        pass
                else:
                    # Chỉ hiện các thông điệp quan trọng có tiền tố [*] hoặc [!]
                    # Bỏ qua toàn bộ thanh tiến trình nội bộ và log rác của PyTorch
                    if line.startswith("[*] Thiết bị") or line.startswith("[+] GPU"):
                        self.log(line)

            ret_code = train_proc.wait()

            with self.lock:
                if self.state["status"] == "stopped" or self.stop_requested:
                    self.state["status"] = "stopped"
                    self.state["message"] = "Đã dừng tiến trình huấn luyện."
                elif ret_code == 0:
                    self.state["status"] = "completed"
                    self.state["progress"] = 100
                    self.state["best_model"] = str(dest_best)
                    self.state["output_model_name"] = output_model_name
                    self.state["message"] = f"🎉 Huấn luyện thành công! Mô hình '{output_model_name}' đã sẵn sàng gắp thả."
                    self.log(f"🎉 [Hoàn thành] Đã lưu mô hình: {dest_best.name}")

                    # Tự động nạp mô hình mới vào Tab 4 (AI Vision)
                    try:
                        server_mod = sys.modules.get("dobot_live_server") or sys.modules.get("__main__")
                        if server_mod and hasattr(server_mod, "vision_engine") and server_mod.vision_engine:
                            ok = server_mod.vision_engine.load_best_yolo_model(str(dest_best))
                            if ok:
                                self.log(f"🤖 Đã tự động kích hoạt mô hình '{dest_best.name}' vào Tab 4 (AI Vision)!")
                    except Exception as e_engine:
                        self.log(f"Thông báo Vision Engine: {e_engine}")
                else:
                    if self.state["status"] != "error":
                        self.state["status"] = "error"
                        self.state["message"] = f"Tiến trình dừng với mã lỗi ({ret_code})"

        except Exception as e:
            self.log(f"❌ Lỗi ngoài dự kiến: {e}")
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
            data_yaml = YOLO_DATASET_DIR / "data.yaml"
            gen_script = PROJECT_ROOT / "generate_yolo_dataset.py"
            if not data_yaml.exists() and gen_script.exists():
                subprocess.run([sys.executable, str(gen_script), "--train-count", "500", "--val-count", "100"], cwd=str(PROJECT_ROOT), capture_output=True)

            if not YOLO_DATASET_DIR.exists():
                return {"success": False, "status": "error", "error": "Chưa có dữ liệu yolo_dataset!", "message": "Chưa có dữ liệu yolo_dataset!"}

            # Đảm bảo đường dẫn path trong data.yaml đúng chuẩn Colab hoặc relative
            sync_data_yaml_path(data_yaml)

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
