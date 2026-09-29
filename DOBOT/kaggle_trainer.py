"""
kaggle_trainer.py: Module Huấn luyện AI 1-Click trên Cloud GPU qua Kaggle API.
- Miễn phí 100% (Tận dụng 30 giờ GPU NVIDIA Tesla T4 / P100 mỗi tuần từ Kaggle).
- 1-Click đúng nghĩa: Tự động nén dataset, đẩy lên Kaggle, kích hoạt GPU và kéo model về.
- Đọc log theo dõi tiến trình thời gian thực từng Epoch.
- Tự động nạp model best_trained.pt vào Vision Engine sau khi hoàn thành.
"""

import os
import sys
import time
import json
import shutil
import zipfile
import threading
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
KAGGLE_WORK_DIR = PROJECT_ROOT / "kaggle_workspace"
KAGGLE_CONFIG_DIR = Path.home() / ".kaggle"
KAGGLE_JSON_PATH = KAGGLE_CONFIG_DIR / "kaggle.json"


class KaggleYOLOTrainer:
    def __init__(self):
        self.lock = threading.RLock()
        self.state = {
            "status": "idle",       # idle, preparing, uploading, queued, running, downloading, completed, error, stopped
            "progress": 0,          # 0 - 100
            "current_epoch": 0,
            "total_epochs": 30,
            "loss": 0.0,
            "map50": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "message": "Sẵn sàng huấn luyện trên Cloud GPU",
            "logs": [],
            "best_model": "",
            "cloud_status": "idle",
            "kernel_id": "",
            "username": "",
            "started_at": 0,
            "eta_seconds": 0,
            "is_cloud": True
        }
        self.worker_thread = None
        self.stop_requested = False
        self._init_credentials()

    def _sync_env_creds(self):
        """Đảm bảo ~/.kaggle/access_token và biến môi trường KAGGLE_API_TOKEN luôn đồng bộ."""
        KAGGLE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        username = os.environ.get("KAGGLE_USERNAME", "")
        key = os.environ.get("KAGGLE_KEY", "") or os.environ.get("KAGGLE_API_TOKEN", "")

        if KAGGLE_JSON_PATH.exists():
            try:
                with open(KAGGLE_JSON_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not username:
                        username = data.get("username", "")
                    if not key:
                        key = data.get("key", "")
            except Exception:
                pass

        access_token_file = KAGGLE_CONFIG_DIR / "access_token"
        if not key and access_token_file.exists():
            try:
                key = access_token_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        if key:
            # Luôn ghi access_token nếu key bắt đầu bằng KGAT hoặc là access token
            try:
                if not access_token_file.exists() or access_token_file.read_text(encoding="utf-8").strip() != key:
                    access_token_file.write_text(key, encoding="utf-8")
            except Exception:
                pass
            os.environ["KAGGLE_API_TOKEN"] = key
            os.environ["KAGGLE_KEY"] = key

        if username:
            os.environ["KAGGLE_USERNAME"] = username

        return username, key

    def _init_credentials(self):
        """Khởi tạo và kiểm tra thông tin tài khoản Kaggle."""
        username, key = self._sync_env_creds()
        with self.lock:
            self.state["username"] = username

    def get_credentials(self) -> dict:
        """Đọc thông tin xác thực từ ~/.kaggle/kaggle.json hoặc biến môi trường."""
        username, key = self._sync_env_creds()
        has_creds = bool(username and key)
        return {
            "configured": has_creds,
            "username": username,
            "key": key,
            "key_masked": f"{key[:4]}****{key[-4:]}" if len(key) >= 8 else ("****" if key else ""),
            "path": str(KAGGLE_JSON_PATH)
        }

    def save_credentials(self, username: str, key: str) -> dict:
        """Lưu file kaggle.json vào ~/.kaggle/ và xác thực kết nối."""
        username = username.strip()
        key = key.strip()

        if not username or not key:
            return {"success": False, "error": "Username và API Key không được để trống!"}

        try:
            KAGGLE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(KAGGLE_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump({"username": username, "key": key}, f, indent=2)

            access_token_path = KAGGLE_CONFIG_DIR / "access_token"
            with open(access_token_path, "w", encoding="utf-8") as f:
                f.write(key)

            os.environ["KAGGLE_API_TOKEN"] = key
            os.environ["KAGGLE_USERNAME"] = username
            os.environ["KAGGLE_KEY"] = key

            # Cấp quyền an toàn trên Linux/macOS nếu có
            if sys.platform != "win32":
                try:
                    os.chmod(KAGGLE_JSON_PATH, 0o600)
                except Exception:
                    pass

            # Kiểm tra đăng nhập
            from kaggle.api.kaggle_api_extended import KaggleApi
            api = KaggleApi()
            api.authenticate()

            with self.lock:
                self.state["username"] = username

            return {"success": True, "username": username, "message": f"Liên kết tài khoản Kaggle @{username} thành công!"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi xác thực Kaggle: {str(e)}"}

    def log(self, text: str):
        print(f"[Kaggle Cloud Trainer] {text}", flush=True)
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
            if self.state["status"] in ("preparing", "uploading", "queued", "running", "downloading"):
                self.state["status"] = "stopped"
                self.state["message"] = "Đã nhận lệnh hủy phiên huấn luyện Cloud GPU."
                self.log("🛑 Đã dừng theo dõi tiến trình huấn luyện Cloud.")

    def start(self, base_model="yolo11n.pt", epochs=30, batch=16, output_model_name="best_trained.pt"):
        with self.lock:
            if self.state["status"] in ("preparing", "uploading", "queued", "running", "downloading"):
                return {"success": False, "error": "Đang có một phiên huấn luyện Cloud chạy ngầm!"}

            creds = self.get_credentials()
            if not creds["configured"]:
                return {
                    "success": False,
                    "need_setup": True,
                    "error": "Chưa cài đặt API Key Kaggle! Vui lòng cài đặt file kaggle.json hoặc nhập token."
                }

            # Chuẩn hóa tên file mô hình xuất ra
            clean_name = str(output_model_name).strip() if output_model_name else "best_trained.pt"
            clean_name = Path(clean_name).name  # Chống path traversal
            if not clean_name.lower().endswith(".pt"):
                clean_name += ".pt"

            self.stop_requested = False
            self.state["status"] = "preparing"
            self.state["progress"] = 2
            self.state["current_epoch"] = 0
            self.state["total_epochs"] = int(epochs)
            self.state["loss"] = 0.0
            self.state["map50"] = 0.0
            self.state["precision"] = 0.0
            self.state["recall"] = 0.0
            self.state["output_model_name"] = clean_name
            self.state["message"] = f"Đang chuẩn bị gửi gói dữ liệu (Mô hình đích: {clean_name})..."
            self.state["logs"] = []
            self.state["started_at"] = time.time()
            self.state["eta_seconds"] = 180  # Dự kiến ~3 phút trên GPU T4

        self.worker_thread = threading.Thread(
            target=self._run_cloud_pipeline,
            args=(creds["username"], base_model, int(epochs), int(batch), clean_name),
            daemon=True
        )
        self.worker_thread.start()
        return {"success": True, "message": f"Đã khởi động tiến trình Cloud GPU (Lưu thành {clean_name})!"}

    def _run_cloud_pipeline(self, username: str, base_model: str, epochs: int, batch: int, output_model_name: str = "best_trained.pt"):
        import subprocess
        try:
            self.log(f"☁️ Khởi động Cloud GPU: Model={base_model} | Epochs={epochs} | Batch={batch} | Lưu={output_model_name} | @{username}")

            # 1. Đảm bảo biến môi trường và access_token cho Kaggle API
            self._sync_env_creds()
            from kaggle.api.kaggle_api_extended import KaggleApi
            api = KaggleApi()
            api.authenticate()

            # 2. Chuẩn bị tập dữ liệu zip
            with self.lock:
                self.state["status"] = "preparing"
                self.state["message"] = "Đang kiểm tra và nén tập dữ liệu yolo_dataset.zip..."

            data_yaml = YOLO_DATASET_DIR / "data.yaml"
            gen_script = PROJECT_ROOT / "generate_yolo_dataset.py"

            if not data_yaml.exists() and gen_script.exists():
                self.log("📦 Đang tự động gán nhãn và tạo dữ liệu YOLO từ dataset_raw/...")
                subprocess.run([sys.executable, str(gen_script), "--train-count", "300", "--val-count", "60"], cwd=str(PROJECT_ROOT), capture_output=True)

            if not YOLO_DATASET_DIR.exists():
                raise FileNotFoundError("Không tìm thấy thư mục yolo_dataset!")

            # Nén thành file zip
            zip_base = str(PROJECT_ROOT / "yolo_dataset")
            shutil.make_archive(zip_base, "zip", root_dir=str(YOLO_DATASET_DIR))

            if not COLAB_ZIP_PATH.exists():
                raise FileNotFoundError("Không tạo được file yolo_dataset.zip!")

            zip_size_mb = COLAB_ZIP_PATH.stat().st_size / (1024 * 1024)
            self.log(f"📦 Đã đóng gói yolo_dataset.zip ({zip_size_mb:.1f} MB)")

            if self.stop_requested:
                return

            # 3. Tạo thư mục kaggle_workspace
            KAGGLE_WORK_DIR.mkdir(parents=True, exist_ok=True)
            ds_upload_dir = KAGGLE_WORK_DIR / "dataset"
            ds_upload_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(COLAB_ZIP_PATH), str(ds_upload_dir / "yolo_dataset.zip"))

            # Ghi dataset-metadata.json
            dataset_slug = "dobot-yolo-dataset"
            dataset_id = f"{username}/{dataset_slug}"
            meta_ds = {
                "title": "Dobot YOLO Dataset",
                "id": dataset_id,
                "licenses": [{"name": "CC0-1.0"}]
            }
            with open(ds_upload_dir / "dataset-metadata.json", "w", encoding="utf-8") as f:
                json.dump(meta_ds, f, indent=2)

            with self.lock:
                self.state["status"] = "uploading"
                self.state["progress"] = 10
                self.state["message"] = "Đang tải dữ liệu lên Kaggle Dataset..."

            self.log(f"☁️ Đang đồng bộ Dataset lên Kaggle ({dataset_id})...")

            # Kiểm tra xem dataset đã tồn tại chưa
            is_existing = False
            try:
                ds_st = api.dataset_status(dataset_id)
                if ds_st:
                    is_existing = True
            except Exception:
                is_existing = False

            if is_existing:
                try:
                    api.dataset_create_version(
                        str(ds_upload_dir),
                        version_notes=f"Auto sync {time.strftime('%Y-%m-%d %H:%M:%S')}",
                        quiet=False
                    )
                    self.log("✅ Đồng bộ phiên bản Dataset mới thành công!")
                except Exception as e_ver:
                    self.log(f"Thông báo Version: {e_ver}")
            else:
                try:
                    self.log(f"Dataset chưa tồn tại, đang tạo mới trên Kaggle...")
                    api.dataset_create_new(str(ds_upload_dir), public=False, quiet=False)
                    self.log("✅ Tạo mới Kaggle Dataset thành công!")
                except Exception as e_new:
                    self.log(f"Thông báo Dataset: {e_new}")

            # Đợi Kaggle xử lý dataset sẵn sàng (tối đa 40s)
            for _ in range(8):
                if self.stop_requested:
                    return
                try:
                    ds_st = api.dataset_status(dataset_id)
                    if ds_st == "ready":
                        break
                except Exception:
                    pass
                time.sleep(5)

            if self.stop_requested:
                return

            with self.lock:
                self.state["progress"] = 20
                self.state["message"] = "Đang cấu hình máy ảo Cloud GPU (Tesla T4)..."

            # 4. Tạo thư mục Kernel và script huấn luyện
            kernel_upload_dir = KAGGLE_WORK_DIR / "kernel"
            kernel_upload_dir.mkdir(parents=True, exist_ok=True)
            kernel_slug = "dobot-yolo-cloud-train"
            kernel_id = f"{username}/{kernel_slug}"

            # Script chạy trực tiếp trên GPU Kaggle
            kernel_code = f"""# Kaggle Cloud GPU Training Script for Dobot
import os
import sys
import shutil
import zipfile
import time
from pathlib import Path

print("[Kaggle Cloud GPU] Starting training environment...")

# Xác định vị trí dữ liệu trong /tmp (không để trong /kaggle/working để tránh payload nặng khi tải về)
work_ds = Path("/tmp/yolo_dataset")
work_ds.mkdir(parents=True, exist_ok=True)

# Kaggle thường tự động giải nén dataset tải lên
data_yamls = list(Path("/kaggle/input").rglob("data.yaml"))
zips = list(Path("/kaggle/input").rglob("*.zip"))

if data_yamls:
    source_dir = data_yamls[0].parent
    print(f"[*] Found uncompressed dataset at: {{source_dir}}")
    shutil.copytree(str(source_dir), str(work_ds), dirs_exist_ok=True)
    print(f"[*] Synced dataset to: {{work_ds}}")
elif zips:
    print(f"[*] Found zip dataset at: {{zips[0]}}")
    with zipfile.ZipFile(str(zips[0]), 'r') as zip_ref:
        zip_ref.extractall(str(work_ds))
    print(f"[*] Unzipped dataset to: {{work_ds}}")
else:
    print("[!] Error: No data.yaml or zip found in /kaggle/input")
    sys.exit(1)

# Cập nhật data.yaml với path tuyệt đối trên Kaggle
data_yaml = work_ds / "data.yaml"
if data_yaml.exists():
    lines = []
    with open(data_yaml, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('path:'):
                lines.append(f"path: {{work_ds.as_posix()}}\\n")
            else:
                lines.append(line)
    with open(data_yaml, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"[*] Updated data.yaml: path = {{work_ds.as_posix()}}")

# Nạp Ultralytics YOLO
try:
    from ultralytics import YOLO
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics"])
    from ultralytics import YOLO

import torch
device = 0 if torch.cuda.is_available() else 'cpu'
dev_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'
print(f"[*] Device activated: GPU {{dev_name}}")

model = YOLO('{base_model}')

# Callback báo log từng epoch
def on_train_epoch_end(trainer):
    ep = trainer.epoch + 1
    total = trainer.epochs
    pct = int((ep / max(1, total)) * 100)
    loss = 0.0

    # Trích xuất tổng loss chuẩn xác từ Ultralytics (tloss là dict của box_loss, cls_loss, dfl_loss)
    if hasattr(trainer, "tloss") and trainer.tloss:
        try:
            if isinstance(trainer.tloss, dict):
                loss = float(sum(float(v) for v in trainer.tloss.values()))
            elif isinstance(trainer.tloss, (list, tuple)):
                loss = float(sum(float(v) for v in trainer.tloss))
            else:
                loss = float(trainer.tloss)
        except Exception:
            pass
    elif hasattr(trainer, "loss") and trainer.loss is not None:
        try:
            loss = float(trainer.loss)
        except Exception:
            pass
    elif hasattr(trainer, "loss_items") and trainer.loss_items is not None:
        try:
            if isinstance(trainer.loss_items, dict):
                loss = float(sum(float(v) for v in trainer.loss_items.values()))
            else:
                loss = float(sum(float(v) for v in trainer.loss_items))
        except Exception:
            pass

    print(f"[EPOCH_LOG] Epoch {{ep}}/{{total}} ({{pct}}%) | Loss: {{loss:.4f}}", flush=True)

def on_fit_epoch_end(trainer):
    try:
        metrics = getattr(trainer, "metrics", dict()) or dict()
        p = float(metrics.get("metrics/precision(B)", 0.0))
        r = float(metrics.get("metrics/recall(B)", 0.0))
        m50 = float(metrics.get("metrics/mAP50(B)", 0.0))
        if m50 > 0 or p > 0:
            print(f"[ACCURACY_METRICS] map50:{{m50:.4f}}|precision:{{p:.4f}}|recall:{{r:.4f}}", flush=True)
    except Exception:
        pass

model.add_callback("on_train_epoch_end", on_train_epoch_end)
model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

# Bắt đầu huấn luyện, lưu checkpoint tạm trong /tmp/runs
print("[*] Starting training on Tesla GPU...")
results = model.train(
    data=str(data_yaml),
    epochs={epochs},
    imgsz=640,
    batch={batch},
    device=device,
    project="/tmp/runs",
    name="dobot_cloud",
    exist_ok=True,
    verbose=False
)

# Trích xuất độ chính xác tổng kết sau khi train xong
try:
    rd = getattr(results, "results_dict", dict()) or dict()
    p_final = float(rd.get("metrics/precision(B)", 0.0))
    r_final = float(rd.get("metrics/recall(B)", 0.0))
    m50_final = float(rd.get("metrics/mAP50(B)", 0.0))
    print(f"[ACCURACY_METRICS] map50:{{m50_final:.4f}}|precision:{{p_final:.4f}}|recall:{{r_final:.4f}}", flush=True)
except Exception:
    pass

# Chỉ copy duy nhất 1 file best.pt ra /kaggle/working để tải về siêu tốc (<2s)
best_trained = Path("/tmp/runs/dobot_cloud/weights/best.pt")
dest_output = Path("/kaggle/working/best_trained.pt")

if best_trained.exists():
    shutil.copy2(str(best_trained), str(dest_output))
    print(f"[*] Training complete! Saved {{dest_output}}")
else:
    all_bests = list(Path("/tmp").rglob("best.pt"))
    if all_bests:
        shutil.copy2(str(all_bests[0]), str(dest_output))
        print(f"[*] Found and saved {{all_bests[0]}} -> {{dest_output}}")
    else:
        print("[!] Warning: best.pt not found")

# Dọn dẹp các thư mục thừa trong /kaggle/working nếu có
for it in Path("/kaggle/working").iterdir():
    if it != dest_output:
        if it.is_dir():
            shutil.rmtree(str(it), ignore_errors=True)
        else:
            try:
                it.unlink()
            except Exception:
                pass

print("[Kaggle Cloud GPU] Session finished successfully!")
"""

            with open(kernel_upload_dir / "kaggle_train.py", "w", encoding="utf-8") as f:
                f.write(kernel_code)

            # Metadata của kernel: Bật GPU Tesla T4/P100
            kernel_meta = {
                "id": kernel_id,
                "title": "dobot-yolo-cloud-train",
                "code_file": "kaggle_train.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": "true",
                "enable_gpu": "true",
                "enable_internet": "true",
                "dataset_sources": [dataset_id]
            }
            with open(kernel_upload_dir / "kernel-metadata.json", "w", encoding="utf-8") as f:
                json.dump(kernel_meta, f, indent=2)

            self.log(f"⚡ Đang đẩy lệnh huấn luyện lên Cloud GPU Kaggle ({kernel_id})...")
            api.kernels_push(str(kernel_upload_dir))

            with self.lock:
                self.state["status"] = "queued"
                self.state["kernel_id"] = kernel_id
                self.state["progress"] = 25
                self.state["message"] = "Đang chờ Kaggle cấp phát máy ảo GPU (Queued)..."

            self.log("⏳ Lệnh đã gửi! Đang chờ Kaggle cấp phát GPU Tesla...")

            # 5. Khởi động luồng đọc log Live qua Kaggle SSE Stream
            stop_stream = threading.Event()

            def process_log_line(raw_l: str):
                import re
                l = raw_l.strip()
                if not l:
                    return
                if "[EPOCH_LOG]" in l:
                    try:
                        parts = l[l.index("[EPOCH_LOG]") + len("[EPOCH_LOG]"):].strip().split("|")
                        ep_part = parts[0].strip()
                        ep_cur = int(ep_part.split()[1].split("/")[0])
                        loss_val = float(parts[1].split(":")[1].strip()) if len(parts) > 1 else 0.0
                        pct = min(95, 30 + int((ep_cur / max(1, epochs)) * 65))

                        with self.lock:
                            self.state["current_epoch"] = ep_cur
                            self.state["progress"] = pct
                            self.state["loss"] = loss_val
                            self.state["message"] = f"Cloud GPU: {ep_part} - Loss: {loss_val:.4f}"

                        self.log(f"📊 [Cloud GPU {ep_part}] Loss: {loss_val:.4f} | Tiến độ: {pct}%")
                    except Exception:
                        self.log(l)
                elif "[ACCURACY_METRICS]" in l:
                    try:
                        tail = l[l.index("[ACCURACY_METRICS]") + len("[ACCURACY_METRICS]"):].strip()
                        for item in tail.split("|"):
                            if ":" in item:
                                k, v = item.split(":", 1)
                                k = k.strip().lower()
                                val = float(v.strip())
                                with self.lock:
                                    if k == "map50":
                                        self.state["map50"] = val
                                    elif k == "precision":
                                        self.state["precision"] = val
                                    elif k == "recall":
                                        self.state["recall"] = val
                        with self.lock:
                            m_val = self.state["map50"]
                            p_val = self.state["precision"]
                            r_val = self.state["recall"]
                        self.log(f"🎯 [Chỉ Số AI] mAP50: {m_val*100:.1f}% | Precision: {p_val*100:.1f}% | Recall: {r_val*100:.1f}%")
                    except Exception:
                        pass
                else:
                    # Kiểm tra dòng bảng tổng kết validation chuẩn của YOLO: "all  127  250  0.994  0.98  0.985"
                    m_all = re.search(r"all\s+\d+\s+\d+\s+([0-1]?\.\d+)\s+([0-1]?\.\d+)\s+([0-1]?\.\d+)", l)
                    if m_all:
                        try:
                            p_val = float(m_all.group(1))
                            r_val = float(m_all.group(2))
                            map_val = float(m_all.group(3))
                            with self.lock:
                                self.state["precision"] = p_val
                                self.state["recall"] = r_val
                                self.state["map50"] = map_val
                            self.log(f"🎯 [Chỉ Số AI] mAP50: {map_val*100:.1f}% | Precision: {p_val*100:.1f}% | Recall: {r_val*100:.1f}%")
                        except Exception:
                            pass
                    elif any(k in l for k in ["[*]", "Device", "Starting", "Training", "Ultralytics", "Epoch", "complete"]):
                        self.log(l)

            def log_stream_worker():
                """Đọc log thời gian thực từng dòng qua SSE stream của Kaggle."""
                try:
                    for event in api.kernels_logs_stream(kernel_id):
                        if stop_stream.is_set() or self.stop_requested:
                            break
                        if isinstance(event, dict) and "data" in event:
                            for d_line in str(event["data"]).splitlines():
                                process_log_line(d_line)
                except Exception:
                    pass

            stream_thread = threading.Thread(target=log_stream_worker, daemon=True)
            stream_thread.start()

            # Vòng lặp theo dõi tiến độ thời gian thực
            poll_interval = 4
            max_wait_seconds = 1800  # 30 phút tối đa
            elapsed_total = 0

            def parse_status(resp):
                if hasattr(resp, "status"):
                    raw = resp.status
                    s = getattr(raw, "name", str(raw)).lower()
                    if "." in s:
                        s = s.split(".")[-1]
                    return s
                elif isinstance(resp, dict):
                    return str(resp.get("status", "")).lower()
                return str(resp).lower()

            while not self.stop_requested and elapsed_total < max_wait_seconds:
                time.sleep(poll_interval)
                elapsed_total += poll_interval

                try:
                    k_status_resp = api.kernels_status(kernel_id)
                    k_status = parse_status(k_status_resp)
                except Exception:
                    continue

                with self.lock:
                    self.state["cloud_status"] = k_status

                # Trạng thái đang xếp hàng chờ GPU
                if k_status in ("queued", "preparing"):
                    with self.lock:
                        self.state["status"] = "queued"
                        self.state["progress"] = min(30, 25 + int(elapsed_total / 4))
                        self.state["message"] = f"Đang khởi tạo máy ảo GPU Tesla trên Kaggle ({k_status})..."

                # Trạng thái đang chạy huấn luyện trên GPU
                elif k_status == "running":
                    with self.lock:
                        self.state["status"] = "running"
                        self.state["message"] = f"Đang huấn luyện trên GPU Tesla (Running) - Đã chạy {elapsed_total}s"

                # Trạng thái hoàn thành!
                elif k_status == "complete":
                    time.sleep(2.0)  # Đợi 2s để SSE stream kịp nhận nốt các log epoch cuối cùng đang dồn trong buffer
                    self.log(f"🎉 Kaggle Cloud GPU đã hoàn tất toàn bộ {epochs}/{epochs} Epochs!")
                    with self.lock:
                        self.state["current_epoch"] = epochs
                        self.state["progress"] = 95
                        self.state["message"] = f"Cloud GPU: Đã hoàn tất {epochs}/{epochs} Epochs!"
                    break

                # Trạng thái lỗi
                elif k_status in ("error", "failed", "cancelacknowledged", "cancelled"):
                    fail_msg = getattr(k_status_resp, "failure_message", "") or getattr(k_status_resp, "failureMessage", "")
                    raise RuntimeError(f"Lỗi trên máy ảo Kaggle: {fail_msg or k_status}")

            stop_stream.set()

            if self.stop_requested:
                self.log("🛑 Người dùng đã hủy theo dõi phiên Cloud GPU.")
                return

            # 6. Tải mô hình về máy và ghi đè triệt để vào thư mục models/
            with self.lock:
                self.state["status"] = "downloading"
                self.state["progress"] = 96
                self.state["message"] = f"Đang tải mô hình từ Cloud GPU và lưu thành {output_model_name}..."

            self.log(f"📥 Đang tải file model từ Cloud GPU (chỉ ~6MB) -> {output_model_name}...")
            download_dir = KAGGLE_WORK_DIR / "output"
            if download_dir.exists():
                shutil.rmtree(str(download_dir), ignore_errors=True)
            download_dir.mkdir(parents=True, exist_ok=True)

            try:
                # force=True đảm bảo Kaggle API luôn tải phiên bản mới nhất, không bỏ qua
                api.kernels_output(kernel_id, path=str(download_dir), file_pattern=r".*best.*\.pt$", force=True)
            except UnicodeEncodeError:
                pass
            except Exception as e_dl:
                if not list(download_dir.rglob("*.pt")):
                    raise e_dl

            downloaded_model = download_dir / "best_trained.pt"
            dest_best = MODELS_DIR / output_model_name
            MODELS_DIR.mkdir(parents=True, exist_ok=True)

            src_file = None
            if downloaded_model.exists():
                src_file = downloaded_model
            else:
                pts = list(download_dir.rglob("best*.pt")) or list(download_dir.rglob("*.pt"))
                if pts:
                    src_file = pts[0]

            if not src_file or not src_file.exists():
                raise FileNotFoundError("Không tìm thấy file model .pt trong kết quả tải về từ Kaggle!")

            # Nếu mô hình đích đã có sẵn: Xóa bỏ trước để đảm bảo ghi đè hoàn toàn 100%
            if dest_best.exists():
                try:
                    dest_best.unlink()
                    self.log(f"🔄 Đã xóa mô hình cũ '{dest_best.name}' để ghi đè bản mới.")
                except Exception as e_del:
                    self.log(f"⚠️ Chú ý khi ghi đè file '{dest_best.name}': {e_del}")

            shutil.copy2(str(src_file), str(dest_best))
            size_mb = dest_best.stat().st_size / (1024 * 1024)
            self.log(f"✅ Đã ghi đè & lưu mô hình thành công: {dest_best.name} ({size_mb:.1f} MB)")

            with self.lock:
                self.state["status"] = "completed"
                self.state["progress"] = 100
                self.state["best_model"] = str(dest_best)
                self.state["output_model_name"] = output_model_name
                self.state["message"] = f"🎉 Huấn luyện Cloud GPU thành công 100%! Mô hình '{output_model_name}' đã sẵn sàng."
                self.log(f"🎉 [Hoàn thành] Mô hình '{dest_best.name}' đã sẵn sàng nhận diện và gắp thả!")

            # 7. Tự động nạp mô hình vào Vision Engine (Tab 4)
            try:
                server_mod = sys.modules.get("dobot_live_server") or sys.modules.get("__main__")
                if server_mod and hasattr(server_mod, "vision_engine") and server_mod.vision_engine:
                    ok = server_mod.vision_engine.load_best_yolo_model(str(dest_best))
                    if ok:
                        self.log(f"🤖 Đã tự động kích hoạt mô hình '{dest_best.name}' vào hệ thống AI Vision (Tab 4)!")
            except Exception as e_engine:
                self.log(f"Thông báo Vision Engine: {e_engine}")

        except Exception as e:
            self.log(f"❌ Lỗi trong phiên huấn luyện Cloud: {e}")
            with self.lock:
                if self.state["status"] != "stopped":
                    self.state["status"] = "error"
                    self.state["message"] = f"Lỗi Cloud GPU: {str(e)[:150]}"


# Singleton instance
kaggle_trainer = KaggleYOLOTrainer()
