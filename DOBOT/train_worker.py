#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_worker.py: Standalone Subprocess Huấn luyện YOLO cho Web Studio.
Độc lập hoàn toàn với tiến trình chính Tornado Web Server.
Khi người dùng bấm Dừng (Stop), tiến trình này có thể bị ngắt (kill) ngay lập tức
mà không ảnh hưởng tới Web Server hay khóa tài nguyên CUDA/GIL.
"""

import os
import sys
import json
import time
import shutil
import argparse
from pathlib import Path

# Đảm bảo UTF-8 và unbuffered stdout cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass


def send_status(payload: dict):
    """Gửi thông điệp JSON có tiền tố JSON_STATUS: cho web_trainer đọc từ stdout."""
    try:
        line = f"JSON_STATUS:{json.dumps(payload, ensure_ascii=False)}"
        print(line, flush=True)
    except Exception as e:
        print(f"[Worker Status Error] {e}", flush=True)


def select_optimal_device():
    """Tự động kiểm tra phần cứng và chọn GPU tối ưu nhất.
    Nếu có nhiều GPU (ví dụ máy Lab có 2 GPU): Tự so sánh VRAM và chọn card khỏe nhất / còn nhiều bộ nhớ nhất.
    Nếu không có GPU NVIDIA: Tự động dùng CPU.
    """
    try:
        import torch
    except ImportError:
        return "cpu", "CPU (Chưa cài đặt PyTorch)"

    if not torch.cuda.is_available():
        return "cpu", "CPU (Không phát hiện GPU NVIDIA / CUDA)"

    gpu_count = torch.cuda.device_count()
    if gpu_count == 0:
        return "cpu", "CPU (CUDA khả dụng nhưng không có card)"

    if gpu_count == 1:
        name = torch.cuda.get_device_name(0)
        total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return 0, f"GPU 0: {name} ({total_vram:.1f} GB VRAM)"

    # Máy có từ 2 GPU trở lên (Multi-GPU ở Lab):
    print(f"[*] Phát hiện hệ thống có {gpu_count} GPU NVIDIA. Đang phân tích để chọn GPU tối ưu...", flush=True)
    best_device_idx = 0
    best_score = -1
    best_desc = ""

    for i in range(gpu_count):
        prop = torch.cuda.get_device_properties(i)
        try:
            free_mem, total_mem = torch.cuda.mem_get_info(i)
        except Exception:
            free_mem = 0
            total_mem = prop.total_memory

        free_gb = free_mem / (1024**3)
        total_gb = total_mem / (1024**3)
        print(f"    [+] GPU {i}: {prop.name} | Tổng VRAM: {total_gb:.1f} GB | VRAM trống: {free_gb:.1f} GB", flush=True)

        # Ưu tiên GPU có nhiều VRAM trống hơn và tổng VRAM lớn hơn
        score = total_mem + free_mem * 2
        if score > best_score:
            best_score = score
            best_device_idx = i
            best_desc = f"GPU {i}: {prop.name} (VRAM trống: {free_gb:.1f} GB / Tổng: {total_gb:.1f} GB)"

    return best_device_idx, best_desc


def main():
    parser = argparse.ArgumentParser(description="Standalone YOLO Training Worker")
    parser.add_argument("--base-model", type=str, default="yolov8n.pt", help="Mô hình khởi điểm (.pt)")
    parser.add_argument("--data-yaml", type=str, required=True, help="Đường dẫn file data.yaml")
    parser.add_argument("--epochs", type=int, default=30, help="Số epochs")
    parser.add_argument("--batch", type=int, default=16, help="Kích thước batch")
    parser.add_argument("--imgsz", type=int, default=640, help="Kích thước ảnh")
    parser.add_argument("--output-model", type=str, default="", help="Đường dẫn lưu file best_trained.pt")
    parser.add_argument("--project-root", type=str, default="", help="Thư mục gốc của project")

    args = parser.parse_args()

    project_root = Path(args.project_root) if args.project_root else Path(__file__).resolve().parent.parent
    data_yaml_path = Path(args.data_yaml).resolve()

    if not data_yaml_path.exists():
        send_status({"type": "error", "message": f"Không tìm thấy file {data_yaml_path}"})
        sys.exit(1)

    print(f"[*] Bắt đầu Train Worker với: Model={args.base_model}, Epochs={args.epochs}, Batch={args.batch}", flush=True)
    send_status({"type": "init", "message": f"Đang nạp mô hình {args.base_model}..."})

    try:
        from ultralytics import YOLO
    except ImportError:
        send_status({"type": "error", "message": "Chưa cài đặt thư viện ultralytics! Chạy: pip install ultralytics"})
        sys.exit(1)

    try:
        model = YOLO(args.base_model)
    except Exception as e:
        send_status({"type": "error", "message": f"Lỗi nạp mô hình {args.base_model}: {str(e)}"})
        sys.exit(1)

    start_time = time.time()
    total_epochs = args.epochs

    # Các callback theo dõi tiến độ
    def on_train_epoch_end(trainer):
        try:
            ep = trainer.epoch + 1
            total = trainer.epochs
            pct = int((ep / max(1, total)) * 100)

            loss = 0.0
            if hasattr(trainer, "loss_items") and trainer.loss_items is not None:
                try:
                    loss = float(trainer.loss_items[0])
                except Exception:
                    pass

            elapsed = time.time() - start_time
            eta_seconds = int((elapsed / max(1, ep)) * (total - ep))

            send_status({
                "type": "epoch",
                "epoch": ep,
                "total_epochs": total,
                "progress": pct,
                "loss": round(loss, 4),
                "eta_seconds": eta_seconds,
                "message": f"Đang huấn luyện Epoch {ep}/{total} ({pct}%) - Loss: {loss:.4f}"
            })
            print(f"[Worker] Epoch {ep}/{total} - Loss: {loss:.4f} - Còn lại ~{eta_seconds}s", flush=True)
        except Exception as e:
            print(f"[Worker Epoch Callback Error] {e}", flush=True)

    def on_fit_epoch_end(trainer):
        try:
            metrics = getattr(trainer, "metrics", None)
            if metrics and "metrics/mAP50(B)" in metrics:
                val = float(metrics["metrics/mAP50(B)"])
                send_status({
                    "type": "metrics",
                    "map50": round(val, 4)
                })
                print(f"[Worker] mAP50(B): {val:.4f}", flush=True)
        except Exception as e:
            pass

    model.add_callback("on_train_epoch_end", on_train_epoch_end)
    model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

    # Tự động phát hiện và chọn GPU tối ưu nhất (hoặc fallback về CPU)
    device_arg, device_info = select_optimal_device()
    print(f"[*] Thiết bị huấn luyện: {device_info}", flush=True)
    send_status({"type": "status", "message": f"Sử dụng {device_info}"})

    # Chạy huấn luyện chính
    print(f"[*] Bắt đầu huấn luyện YOLO trên thiết bị: {device_arg}...", flush=True)

    try:
        results = model.train(
            data=str(data_yaml_path),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=device_arg,
            name="web_studio_train",
            exist_ok=True,
            verbose=False,
            workers=2
        )
    except Exception as e:
        print(f"[Worker Training Error] {e}", flush=True)
        send_status({"type": "error", "message": f"Lỗi trong lúc train: {str(e)}"})
        sys.exit(1)

    # Sao chép best.pt tới output_model
    trained_best = project_root / "runs" / "detect" / "web_studio_train" / "weights" / "best.pt"
    if args.output_model:
        dest_model = Path(args.output_model).resolve()
        dest_model.parent.mkdir(parents=True, exist_ok=True)
        if trained_best.exists():
            shutil.copy2(str(trained_best), str(dest_model))
            print(f"[*] Đã sao chép mô hình tốt nhất vào: {dest_model}", flush=True)
            send_status({
                "type": "completed",
                "best_model": str(dest_model),
                "message": "🎉 Huấn luyện thành công! Mô hình đã sẵn sàng gắp thả."
            })
            sys.exit(0)

    send_status({
        "type": "completed",
        "best_model": str(trained_best) if trained_best.exists() else "",
        "message": "🎉 Huấn luyện hoàn tất!"
    })
    sys.exit(0)


if __name__ == "__main__":
    main()
