// =========================================================================
// --- MODULE: MEDIAPIPE HAND TELEOPERATION & 1-EURO ADAPTIVE FILTER ---
// =========================================================================


        // =====================================================================
        // --- TAB 6: ĐIỀU KHIỂN CỬ CHỈ TAY MEDIAPIPE (HAND TELEOPERATION) ---
        // =====================================================================
        let handMediaPipeInstance = null;
        let handCameraStream = null;
        let handCameraRunning = false;
        let isHandMirrored = true;
        let isTeleopMasterActive = false;
        let handAnimationId = null;

        // Trạng thái Hiệu Chuẩn Mốc 0 & Độ Nhạy
        let handLastSeenLandmarks = null;
        let handLastSeenNorm = { x: 0.5, y: 0.5, scale: 0.18 };
        let handCalib = {
            calibrated: false,
            centerNormX: 0.50,
            centerNormY: 0.50,
            centerScale: 0.18
        };
        let handSensitivity = 1.0;
        let handCustomLimits = {
            xMin: 180.0,
            xMax: 300.0,
            yMin: -150.0,
            yMax: 150.0,
            zMin: -125.0,
            zMax: 80.0
        };

        // Thuật toán 1-Euro Filter (Bộ lọc triệt rung thích nghi đẳng cấp công nghiệp)
        class OneEuroFilter {
            constructor(minCutoff = 0.8, beta = 0.04, dCutoff = 1.0) {
                this.minCutoff = minCutoff;
                this.beta = beta;
                this.dCutoff = dCutoff;
                this.xPrev = null;
                this.dxPrev = 0;
                this.tPrev = null;
            }
            filter(val, timestamp) {
                if (this.xPrev === null) {
                    this.xPrev = val;
                    this.tPrev = timestamp;
                    return val;
                }
                const dt = Math.max(0.001, (timestamp - this.tPrev) / 1000);
                this.tPrev = timestamp;
                const dx = (val - this.xPrev) / dt;
                const aD = this.alpha(dt, this.dCutoff);
                const dxHat = aD * dx + (1 - aD) * this.dxPrev;
                this.dxPrev = dxHat;
                const cutoff = this.minCutoff + this.beta * Math.abs(dxHat);
                const a = this.alpha(dt, cutoff);
                const xHat = a * val + (1 - a) * this.xPrev;
                this.xPrev = xHat;
                return xHat;
            }
            alpha(dt, cutoff) {
                const tau = 1.0 / (2 * Math.PI * cutoff);
                return 1.0 / (1.0 + tau / dt);
            }
            reset() {
                this.xPrev = null;
                this.dxPrev = 0;
                this.tPrev = null;
            }
        }

        const euroX = new OneEuroFilter(0.8, 0.05);
        const euroY = new OneEuroFilter(0.8, 0.05);
        const euroZ = new OneEuroFilter(0.8, 0.05);

        // Trạng thái mượt & Rate limit
        let lastHandSendTime = 0;
        let handSmoothX = 230.0;
        let handSmoothY = 0.0;
        let handSmoothZ = 20.0;
        let handLastTargetX = 230.0;
        let handLastTargetY = 0.0;
        let handLastTargetZ = 20.0;
        let handCurrentSuction = false;
        let handFistDebounceCounter = 0;
        let handOpenDebounceCounter = 0;

        // FPS tracking
        let handFpsFrameCount = 0;
        let handFpsLastTime = performance.now();
        let handCurrentFps = 0;

        function updateHandSettingsUI() {
            const hz = document.getElementById('slider-hand-hz')?.value || 12;
            const ema = document.getElementById('slider-hand-ema')?.value || 0.25;
            const deadband = document.getElementById('slider-hand-deadband')?.value || 2.0;
            const fistThresh = document.getElementById('slider-hand-fist-thresh')?.value || 0.65;

            const lblHz = document.getElementById('val-hand-hz');
            const lblEma = document.getElementById('val-hand-ema');
            const lblDeadband = document.getElementById('val-hand-deadband');
            const lblFist = document.getElementById('val-hand-fist-thresh');

            if (lblHz) lblHz.innerText = hz + ' Hz';
            if (lblEma) lblEma.innerText = parseFloat(ema).toFixed(2);
            if (lblDeadband) lblDeadband.innerText = parseFloat(deadband).toFixed(1) + ' mm';
            if (lblFist) lblFist.innerText = Math.round(fistThresh * 100) + '%';

            // Cập nhật tham số 1-Euro Filter từ slider
            const minCut = Math.max(0.1, parseFloat(ema) * 2.5);
            euroX.minCutoff = minCut;
            euroY.minCutoff = minCut;
            euroZ.minCutoff = minCut;
        }

        function updateCustomLimits() {
            const xmin = parseFloat(document.getElementById('inp-lim-xmin')?.value) || 180;
            const xmax = parseFloat(document.getElementById('inp-lim-xmax')?.value) || 300;
            const ymin = parseFloat(document.getElementById('inp-lim-ymin')?.value) || -150;
            const ymax = parseFloat(document.getElementById('inp-lim-ymax')?.value) || 150;
            const zmin = parseFloat(document.getElementById('inp-lim-zmin')?.value) || -125;
            const zmax = parseFloat(document.getElementById('inp-lim-zmax')?.value) || 80;

            handCustomLimits.xMin = Math.min(xmin, xmax);
            handCustomLimits.xMax = Math.max(xmin, xmax);
            handCustomLimits.yMin = Math.min(ymin, ymax);
            handCustomLimits.yMax = Math.max(ymin, ymax);
            handCustomLimits.zMin = Math.min(zmin, zmax);
            handCustomLimits.zMax = Math.max(zmin, zmax);
        }

        function syncZPickFromDropTargets() {
            let pickZ = -122.2;
            if (typeof dropTargetsConfig !== 'undefined' && dropTargetsConfig.pick_z !== undefined) {
                pickZ = parseFloat(dropTargetsConfig.pick_z);
            }
            const inpZMin = document.getElementById('inp-lim-zmin');
            if (inpZMin) {
                inpZMin.value = pickZ.toFixed(1);
                updateCustomLimits();
            }
            showToast(`📍 Đã đồng bộ Z_min = ${pickZ.toFixed(1)} mm từ cấu hình khay gắp thực tế!`);
        }

        function setHandSensitivity(s) {
            handSensitivity = s;
            const btnSlow = document.getElementById('btn-sens-slow');
            const btnNorm = document.getElementById('btn-sens-norm');
            const btnFast = document.getElementById('btn-sens-fast');

            [btnSlow, btnNorm, btnFast].forEach(b => {
                if (b) {
                    b.style.background = '#1e293b';
                    b.style.borderColor = '#475569';
                    b.style.color = '#94a3b8';
                    b.style.fontWeight = 'normal';
                }
            });

            if (s === 0.5 && btnSlow) {
                btnSlow.style.background = '#0284c7';
                btnSlow.style.borderColor = '#38bdf8';
                btnSlow.style.color = '#fff';
                btnSlow.style.fontWeight = '700';
                showToast("🎯 Đã chuyển sang chế độ 0.5x (Siêu Tinh Chỉnh cho phôi nhỏ)");
            } else if (s === 1.5 && btnFast) {
                btnFast.style.background = '#0284c7';
                btnFast.style.borderColor = '#38bdf8';
                btnFast.style.color = '#fff';
                btnFast.style.fontWeight = '700';
                showToast("⚡ Đã chuyển sang chế độ 1.5x (Biên độ vung tay rộng)");
            } else if (btnNorm) {
                btnNorm.style.background = '#0284c7';
                btnNorm.style.borderColor = '#38bdf8';
                btnNorm.style.color = '#fff';
                btnNorm.style.fontWeight = '700';
                showToast("⚖️ Đã chuyển về chế độ 1.0x (Tiêu Chuẩn)");
            }
        }

        function calibrateHandNeutral() {
            if (!handLastSeenLandmarks) {
                showToast("⚠️ Chưa phát hiện bàn tay! Hãy giơ tay trước camera trước khi bấm lấy mốc.");
                return;
            }
            handCalib.calibrated = true;
            handCalib.centerNormX = handLastSeenNorm.x;
            handCalib.centerNormY = handLastSeenNorm.y;
            handCalib.centerScale = handLastSeenNorm.scale;

            euroX.reset();
            euroY.reset();
            euroZ.reset();

            const badge = document.getElementById('hand-calib-status-badge');
            if (badge) {
                badge.style.background = "rgba(16, 185, 129, 0.25)";
                badge.style.color = "#34d399";
                badge.style.borderColor = "#10b981";
                badge.innerText = `Mốc 0: X=${(handCalib.centerNormX).toFixed(2)}, Y=${(handCalib.centerNormY).toFixed(2)}`;
            }

            showToast("🎯 ĐÃ HIỆU CHUẨN TÂM MỐC 0! Mọi chuyển động nay sẽ tính từ tư thế thoải mái này của bạn.");
        }

        function resetHandNeutral() {
            handCalib.calibrated = false;
            handCalib.centerNormX = 0.50;
            handCalib.centerNormY = 0.50;
            handCalib.centerScale = 0.18;

            euroX.reset();
            euroY.reset();
            euroZ.reset();

            const badge = document.getElementById('hand-calib-status-badge');
            if (badge) {
                badge.style.background = "rgba(14, 165, 233, 0.2)";
                badge.style.color = "#38bdf8";
                badge.style.borderColor = "rgba(56, 189, 248, 0.4)";
                badge.innerText = "Mốc: Mặc định";
            }
            showToast("🔄 Đã đặt lại tâm mốc 0 về giữa khung hình camera.");
        }

        async function initHandTeleopTab() {
            updateHandSettingsUI();
            updateCustomLimits();
            updateHandRobotStatusBadge();
            await populateHandCameraDevices();
        }

        function updateHandRobotStatusBadge() {
            const badge = document.getElementById('hand-robot-badge');
            if (badge) {
                if (isRobotConnected || isRobotHardwareConnected) {
                    badge.className = "sys-badge live";
                    badge.innerText = "DOBOT: ĐÃ KẾT NỐI ●";
                } else {
                    badge.className = "sys-badge offline";
                    badge.innerText = "DOBOT: CHƯA KẾT NỐI ○";
                }
            }
        }

        async function populateHandCameraDevices() {
            const selectEl = document.getElementById('hand-cam-select');
            if (!selectEl) return;
            try {
                if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
                    selectEl.innerHTML = '<option value="">-- Trình duyệt không hỗ trợ Camera API --</option>';
                    return;
                }
                const devices = await navigator.mediaDevices.enumerateDevices();
                const videoDevices = devices.filter(d => d.kind === 'videoinput');
                if (videoDevices.length === 0) {
                    selectEl.innerHTML = '<option value="">-- Không tìm thấy camera nào --</option>';
                    return;
                }
                const currentVal = selectEl.value;
                selectEl.innerHTML = '';
                videoDevices.forEach((dev, idx) => {
                    const opt = document.createElement('option');
                    opt.value = dev.deviceId;
                    opt.text = dev.label || `Camera ${idx + 1}`;
                    selectEl.appendChild(opt);
                });
                if (currentVal && Array.from(selectEl.options).some(o => o.value === currentVal)) {
                    selectEl.value = currentVal;
                }
            } catch (err) {
                console.warn("Lỗi dò tìm camera:", err);
            }
        }

        function toggleHandMirror() {
            isHandMirrored = !isHandMirrored;
            showToast(isHandMirrored ? "🔄 Đã bật chế độ lật gương (Mirror)" : "🔄 Đã tắt chế độ lật gương");
        }

        function toggleTeleopMaster() {
            isTeleopMasterActive = !isTeleopMasterActive;
            const btn = document.getElementById('btn-teleop-master');
            const txt = document.getElementById('teleop-master-text');
            const statusBadge = document.getElementById('hand-status-badge');

            if (isTeleopMasterActive) {
                if (btn) btn.className = "btn-teleop-master on";
                if (txt) txt.innerText = "🟢 ĐANG PHÁT LỆNH ĐIỀU KHIỂN (CLICK ĐỂ TẮT)";
                if (statusBadge) {
                    statusBadge.className = "sys-badge live";
                    statusBadge.innerText = "🟢 TELEOP BẬT";
                }
                showToast("🚀 ĐÃ KÍCH HOẠT ĐIỀU KHIỂN DOBOT! Robot sẽ di chuyển bám sát tay bạn.");
            } else {
                if (btn) btn.className = "btn-teleop-master off";
                if (txt) txt.innerText = "KÍCH HOẠT PHÁT LỆNH ĐẾN DOBOT (ĐANG TẮT)";
                if (statusBadge) {
                    statusBadge.className = "sys-badge offline";
                    statusBadge.innerText = "🔴 TELEOP TẮT";
                }
                sendAction('suction', false);
                handCurrentSuction = false;
                const metricSuction = document.getElementById('teleop-metric-suction');
                if (metricSuction) {
                    metricSuction.innerText = "OFF (ĐÃ TẮT)";
                    metricSuction.style.color = "#94a3b8";
                }
                showToast("⏹️ Đã tắt phát lệnh điều khiển Dobot. Chuyển về chế độ preview.");
            }
        }

        async function toggleHandCamera() {
            if (handCameraRunning) {
                stopHandCamera();
            } else {
                await startHandCamera();
            }
        }

        async function startHandCamera() {
            const btn = document.getElementById('btn-hand-cam-toggle');
            const videoEl = document.getElementById('hand-raw-video');
            const selectEl = document.getElementById('hand-cam-select');
            const placeholder = document.getElementById('hand-cam-placeholder');

            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showToast("❌ Trình duyệt không hỗ trợ truy cập Webcam!");
                return;
            }

            try {
                if (btn) {
                    btn.innerText = "⏳ Đang mở...";
                    btn.disabled = true;
                }

                const deviceId = selectEl ? selectEl.value : null;
                const constraints = {
                    video: deviceId ? { deviceId: { exact: deviceId }, width: { ideal: 640 }, height: { ideal: 480 } } : { width: { ideal: 640 }, height: { ideal: 480 } },
                    audio: false
                };

                handCameraStream = await navigator.mediaDevices.getUserMedia(constraints);
                videoEl.srcObject = handCameraStream;
                await videoEl.play();

                if (placeholder) placeholder.style.display = 'none';

                if (!handMediaPipeInstance) {
                    initMediaPipeHands();
                }

                handCameraRunning = true;
                if (btn) {
                    btn.innerText = "⏹️ Tắt Camera";
                    btn.style.background = "#e11d48";
                    btn.style.borderColor = "#f43f5e";
                    btn.disabled = false;
                }

                showToast("📷 Đã mở Camera và khởi động AI nhận diện bàn tay!");
                runHandProcessLoop();
            } catch (err) {
                console.error("Lỗi mở camera:", err);
                showToast("❌ Không thể mở camera: " + (err.message || err.name));
                if (btn) {
                    btn.innerText = "▶️ Bật Camera";
                    btn.disabled = false;
                }
            }
        }

        function stopHandCamera() {
            handCameraRunning = false;
            if (handAnimationId) {
                cancelAnimationFrame(handAnimationId);
                handAnimationId = null;
            }
            if (handCameraStream) {
                handCameraStream.getTracks().forEach(t => t.stop());
                handCameraStream = null;
            }
            const videoEl = document.getElementById('hand-raw-video');
            if (videoEl) videoEl.srcObject = null;

            const btn = document.getElementById('btn-hand-cam-toggle');
            if (btn) {
                btn.innerText = "▶️ Bật Camera";
                btn.style.background = "#0284c7";
                btn.style.borderColor = "#38bdf8";
            }

            const placeholder = document.getElementById('hand-cam-placeholder');
            if (placeholder) placeholder.style.display = 'block';

            const canvas = document.getElementById('hand-teleop-canvas');
            if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }

            const trackBadge = document.getElementById('hand-tracking-badge');
            if (trackBadge) {
                trackBadge.className = "hand-badge tracking-off";
                trackBadge.innerText = "○ CHƯA THẤY TAY";
            }

            if (isTeleopMasterActive) {
                toggleTeleopMaster();
            }
            showToast("⏹️ Đã tắt camera.");
        }

        function initMediaPipeHands() {
            if (typeof Hands === 'undefined') {
                console.warn("MediaPipe Hands JS chưa được tải!");
                showToast("⚠️ Thư viện MediaPipe Hands đang tải từ CDN, vui lòng đợi vài giây...");
                return;
            }

            handMediaPipeInstance = new Hands({
                locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
            });

            handMediaPipeInstance.setOptions({
                maxNumHands: 1,
                modelComplexity: 1,
                minDetectionConfidence: 0.65,
                minTrackingConfidence: 0.65
            });

            handMediaPipeInstance.onResults(onHandResults);
            console.log("[MediaPipe] Hands model initialized.");
        }

        async function runHandProcessLoop() {
            if (!handCameraRunning) return;
            const videoEl = document.getElementById('hand-raw-video');

            if (videoEl && videoEl.readyState >= 2 && handMediaPipeInstance) {
                try {
                    await handMediaPipeInstance.send({ image: videoEl });
                } catch (e) {
                    console.warn("Lỗi gửi frame MediaPipe:", e);
                }
            }

            if (handCameraRunning) {
                handAnimationId = requestAnimationFrame(runHandProcessLoop);
            }
        }

        // Xử lý kết quả trả về từ MediaPipe Hands với độ chính xác cao & 1-Euro Filter
        function onHandResults(results) {
            const canvas = document.getElementById('hand-teleop-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const w = canvas.width;
            const h = canvas.height;

            // Đo FPS
            handFpsFrameCount++;
            const now = performance.now();
            if (now - handFpsLastTime >= 1000) {
                handCurrentFps = Math.round((handFpsFrameCount * 1000) / (now - handFpsLastTime));
                handFpsFrameCount = 0;
                handFpsLastTime = now;
                const fpsBadge = document.getElementById('hand-fps-badge');
                if (fpsBadge) fpsBadge.innerText = `FPS: ${handCurrentFps}`;
            }

            ctx.save();
            ctx.clearRect(0, 0, w, h);

            // Vẽ video feed nền (hỗ trợ lật gương)
            if (isHandMirrored) {
                ctx.translate(w, 0);
                ctx.scale(-1, 1);
            }
            if (results.image) {
                ctx.drawImage(results.image, 0, 0, w, h);
            }
            ctx.restore();

            const trackBadge = document.getElementById('hand-tracking-badge');
            const gestureBadge = document.getElementById('hand-gesture-badge');
            const posHud = document.getElementById('hand-pos-hud');

            // Nếu không phát hiện thấy bàn tay
            if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
                handLastSeenLandmarks = null;
                if (trackBadge) {
                    trackBadge.className = "hand-badge tracking-off";
                    trackBadge.innerText = "○ CHƯA THẤY TAY";
                }
                return;
            }

            // Có phát hiện bàn tay
            if (trackBadge) {
                trackBadge.className = "hand-badge tracking-on";
                trackBadge.innerText = "● ĐANG THEO DÕI TAY";
            }

            const landmarks = results.multiHandLandmarks[0];
            handLastSeenLandmarks = landmarks;

            // 1. Phân tích cử chỉ: Nắm tay (Fist) hay Mở tay (Open Palm)
            const wrist = landmarks[0];
            const middleMCP = landmarks[9];
            const palmBaseDist = Math.hypot(middleMCP.x - wrist.x, middleMCP.y - wrist.y);

            const fingerTips = [8, 12, 16, 20];
            const fingerPIPs = [6, 10, 14, 18];
            let foldedFingersCount = 0;

            for (let i = 0; i < 4; i++) {
                const tip = landmarks[fingerTips[i]];
                const pip = landmarks[fingerPIPs[i]];
                const distTipWrist = Math.hypot(tip.x - wrist.x, tip.y - wrist.y);
                const distPipWrist = Math.hypot(pip.x - wrist.x, pip.y - wrist.y);
                if (distTipWrist < distPipWrist * 1.08) {
                    foldedFingersCount++;
                }
            }

            const thumbTip = landmarks[4];
            const indexMCP = landmarks[5];
            const thumbDist = Math.hypot(thumbTip.x - indexMCP.x, thumbTip.y - indexMCP.y);
            if (thumbDist < palmBaseDist * 0.75) {
                foldedFingersCount++;
            }

            const isFistDetected = (foldedFingersCount >= 3);

            if (isFistDetected) {
                handFistDebounceCounter++;
                handOpenDebounceCounter = 0;
            } else {
                handOpenDebounceCounter++;
                handFistDebounceCounter = 0;
            }

            let isSuctionActive = handCurrentSuction;
            if (handFistDebounceCounter >= 2) {
                isSuctionActive = true;
            } else if (handOpenDebounceCounter >= 2) {
                isSuctionActive = false;
            }

            if (gestureBadge) {
                if (isSuctionActive) {
                    gestureBadge.className = "hand-badge gesture-fist";
                    gestureBadge.innerText = "✊ NẮM TAY (HÚT: BẬT)";
                } else {
                    gestureBadge.className = "hand-badge gesture-open";
                    gestureBadge.innerText = "🖐️ TAY MỞ (HÚT: TẮT)";
                }
            }

            const metricGesture = document.getElementById('teleop-metric-gesture');
            if (metricGesture) {
                metricGesture.innerText = isSuctionActive ? "✊ NẮM TAY (FIST)" : "🖐️ MỞ (OPEN)";
                metricGesture.style.color = isSuctionActive ? "#f87171" : "#34d399";
            }

            // 2. Tọa độ tâm bàn tay chuẩn hóa
            let palmX = (landmarks[0].x + landmarks[5].x + landmarks[17].x) / 3;
            let palmY = (landmarks[0].y + landmarks[5].y + landmarks[17].y) / 3;
            let palmZ = landmarks[0].z || 0;

            let normX = isHandMirrored ? (1.0 - palmX) : palmX;
            let normY = palmY;

            handLastSeenNorm = { x: normX, y: normY, scale: palmBaseDist };

            if (posHud) {
                posHud.innerText = `Tay: (${normX.toFixed(2)}, ${normY.toFixed(2)}) | Scale: ${(palmBaseDist * 100).toFixed(0)}%`;
            }

            // 3. ÁNH XẠ TOẠ ĐỘ DOBOT CÓ HIỆU CHUẨN MỐC 0 & ĐỘ NHẠY
            const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
            let rawDobotX, rawDobotY, rawDobotZ;

            const xSpan = handCustomLimits.xMax - handCustomLimits.xMin;
            const ySpan = handCustomLimits.yMax - handCustomLimits.yMin;
            const zSpan = handCustomLimits.zMax - handCustomLimits.zMin;
            const xMid = (handCustomLimits.xMin + handCustomLimits.xMax) / 2;
            const yMid = (handCustomLimits.yMin + handCustomLimits.yMax) / 2;
            const zMid = (handCustomLimits.zMin + handCustomLimits.zMax) / 2;

            if (handCalib.calibrated) {
                // Chế độ đã hiệu chuẩn mốc 0: Tính từ độ lệch so với tư thế tự nhiên của người dùng
                const deltaX = (normX - handCalib.centerNormX) * handSensitivity;
                const deltaY = (normY - handCalib.centerNormY) * handSensitivity;
                const deltaScale = (palmBaseDist - handCalib.centerScale) * handSensitivity;

                rawDobotY = yMid + deltaX * (ySpan * 1.5);
                rawDobotZ = zMid - deltaY * (zSpan * 1.6);
                rawDobotX = xMid + deltaScale * (xSpan * 6.5);
            } else {
                // Chế độ mặc định: Ánh xạ tỷ lệ theo khung hình chuẩn [0.15, 0.85]
                const rangeNormX = clamp((normX - 0.15) / 0.70, 0, 1);
                const rangeNormY = clamp((normY - 0.15) / 0.70, 0, 1);
                const normDist = clamp((palmBaseDist - 0.10) / 0.18, 0, 1);

                rawDobotY = handCustomLimits.yMin + rangeNormX * ySpan;
                rawDobotZ = handCustomLimits.zMax - rangeNormY * zSpan;
                rawDobotX = handCustomLimits.xMin + normDist * xSpan;
            }

            // 4. BỘ LỌC 1-EURO FILTER THÍCH NGHI ĐẲNG CẤP CAO
            const filteredX = euroX.filter(rawDobotX, now);
            const filteredY = euroY.filter(rawDobotY, now);
            const filteredZ = euroZ.filter(rawDobotZ, now);

            // Kẹp trong phạm vi tùy chỉnh
            const finalX = clamp(Math.round(filteredX * 10) / 10, handCustomLimits.xMin, handCustomLimits.xMax);
            const finalY = clamp(Math.round(filteredY * 10) / 10, handCustomLimits.yMin, handCustomLimits.yMax);
            const finalZ = clamp(Math.round(filteredZ * 10) / 10, handCustomLimits.zMin, handCustomLimits.zMax);

            // 5. Vẽ Skeleton, Mốc 0 và Thước đo HUD
            drawHandSkeleton(ctx, landmarks, w, h, isHandMirrored, isSuctionActive, finalX, finalY, finalZ);

            // Cập nhật Metrics UI
            const metricTarget = document.getElementById('teleop-metric-target');
            if (metricTarget) {
                metricTarget.innerText = `X: ${finalX.toFixed(0)} | Y: ${finalY.toFixed(0)} | Z: ${finalZ.toFixed(0)}`;
            }

            const metricActual = document.getElementById('teleop-metric-actual');
            if (metricActual && lastKnownRobotPose) {
                metricActual.innerText = `X: ${lastKnownRobotPose.x.toFixed(0)} | Y: ${lastKnownRobotPose.y.toFixed(0)} | Z: ${lastKnownRobotPose.z.toFixed(0)}`;
            }

            // 6. Phát lệnh điều khiển thời gian thực
            const targetHz = parseInt(document.getElementById('slider-hand-hz')?.value) || 12;
            const sendIntervalMs = 1000 / targetHz;

            if (isTeleopMasterActive && (now - lastHandSendTime >= sendIntervalMs)) {
                lastHandSendTime = now;

                const deadbandMm = parseFloat(document.getElementById('slider-hand-deadband')?.value) || 2.0;
                const distChange = Math.hypot(finalX - handLastTargetX, finalY - handLastTargetY, finalZ - handLastTargetZ);

                if (distChange >= deadbandMm) {
                    handLastTargetX = finalX;
                    handLastTargetY = finalY;
                    handLastTargetZ = finalZ;

                    const zFlange = finalZ + toolOffset;
                    sendAction('move_xyz', { x: finalX, y: finalY, z: zFlange, r: 0, mode: 2 });
                }

                if (isSuctionActive !== handCurrentSuction) {
                    handCurrentSuction = isSuctionActive;
                    sendAction('suction', handCurrentSuction);

                    const metricSuction = document.getElementById('teleop-metric-suction');
                    if (metricSuction) {
                        metricSuction.innerText = handCurrentSuction ? "ON (ĐANG HÚT)" : "OFF (ĐÃ TẮT)";
                        metricSuction.style.color = handCurrentSuction ? "#f87171" : "#94a3b8";
                    }
                }
            }
        }

        // Vẽ Khung Xương Bàn Tay & HUD Thước Đo Trực Quan
        function drawHandSkeleton(ctx, landmarks, w, h, mirrored, isFist, curX, curY, curZ) {
            const HAND_CONNECTIONS = [
                [0, 1], [1, 2], [2, 3], [3, 4],
                [0, 5], [5, 6], [6, 7], [7, 8],
                [5, 9], [9, 10], [10, 11], [11, 12],
                [9, 13], [13, 14], [14, 15], [15, 16],
                [13, 17], [17, 18], [18, 19], [19, 20],
                [0, 17]
            ];

            const boneColor = isFist ? "rgba(248, 113, 113, 0.85)" : "rgba(56, 189, 248, 0.85)";
            const jointColor = isFist ? "#ef4444" : "#38bdf8";

            // Vẽ các đường nối xương
            ctx.lineWidth = 3;
            ctx.strokeStyle = boneColor;
            ctx.beginPath();
            for (let pair of HAND_CONNECTIONS) {
                const p1 = landmarks[pair[0]];
                const p2 = landmarks[pair[1]];
                const x1 = mirrored ? (1 - p1.x) * w : p1.x * w;
                const y1 = p1.y * h;
                const x2 = mirrored ? (1 - p2.x) * w : p2.x * w;
                const y2 = p2.y * h;
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
            }
            ctx.stroke();

            // Vẽ các khớp đốt (Joints)
            for (let i = 0; i < landmarks.length; i++) {
                const pt = landmarks[i];
                const x = mirrored ? (1 - pt.x) * w : pt.x * w;
                const y = pt.y * h;

                ctx.beginPath();
                ctx.arc(x, y, [4, 8, 12, 16, 20].includes(i) ? 6 : 4, 0, 2 * Math.PI);
                ctx.fillStyle = [4, 8, 12, 16, 20].includes(i) ? (isFist ? "#ffedd5" : "#ffffff") : jointColor;
                ctx.fill();
                ctx.strokeStyle = boneColor;
                ctx.lineWidth = 1.5;
                ctx.stroke();
            }

            // Vẽ tâm lòng bàn tay
            const palmX = (landmarks[0].x + landmarks[5].x + landmarks[17].x) / 3;
            const palmY = (landmarks[0].y + landmarks[5].y + landmarks[17].y) / 3;
            const px = mirrored ? (1 - palmX) * w : palmX * w;
            const py = palmY * h;

            ctx.beginPath();
            ctx.arc(px, py, 14, 0, 2 * Math.PI);
            ctx.strokeStyle = isFist ? "#ef4444" : "#10b981";
            ctx.lineWidth = 2.5;
            ctx.stroke();

            ctx.beginPath();
            ctx.arc(px, py, 4, 0, 2 * Math.PI);
            ctx.fillStyle = isFist ? "#f87171" : "#34d399";
            ctx.fill();

            // VẼ MỐC 0 CHUẨN ĐÃ HIỆU CHUẨN (CALIBRATED NEUTRAL CROSSHAIR)
            if (handCalib.calibrated) {
                const cx = mirrored ? (1 - handCalib.centerNormX) * w : handCalib.centerNormX * w;
                const cy = handCalib.centerNormY * h;

                ctx.save();
                ctx.strokeStyle = "rgba(244, 63, 94, 0.7)";
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 4]);

                // Vòng tròn mốc 0
                ctx.beginPath();
                ctx.arc(cx, cy, 22, 0, 2 * Math.PI);
                ctx.stroke();

                // Dấu cộng tâm
                ctx.beginPath();
                ctx.moveTo(cx - 30, cy); ctx.lineTo(cx + 30, cy);
                ctx.moveTo(cx, cy - 30); ctx.lineTo(cx, cy + 30);
                ctx.stroke();

                ctx.fillStyle = "#f43f5e";
                ctx.font = "10px monospace";
                ctx.fillText("MỐC 0 CHUẨN", cx + 26, cy - 8);
                ctx.restore();
            }

            // VẼ THƯỚC ĐO CAO ĐỘ Z (VERTICAL HEIGHT GAUGE) BÊN PHẢI CANVAS
            const gaugeX = w - 18;
            const gaugeTop = 60;
            const gaugeBottom = h - 60;
            const gaugeH = gaugeBottom - gaugeTop;

            ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
            ctx.fillRect(gaugeX - 6, gaugeTop, 12, gaugeH);
            ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
            ctx.strokeRect(gaugeX - 6, gaugeTop, 12, gaugeH);

            const zPct = (curZ - handCustomLimits.zMin) / (handCustomLimits.zMax - handCustomLimits.zMin);
            const zMarkerY = gaugeBottom - Math.max(0, Math.min(1, zPct)) * gaugeH;

            ctx.fillStyle = "#38bdf8";
            ctx.fillRect(gaugeX - 8, zMarkerY - 3, 16, 6);
            ctx.fillStyle = "#cbd5e1";
            ctx.font = "9px monospace";
            ctx.fillText(`Z: ${curZ.toFixed(0)}`, gaugeX - 48, zMarkerY + 3);
        }

