// =========================================================================
// --- MODULE: AI VISION, DATASET, TRAINER, AUTO-SORT & CALIBRATION ---
// =========================================================================

        // =====================================================================
        // FABLAB AI & DOBOT WEB STUDIO - 4 MODULE CONTROLLER
        // =====================================================================
        let currentStudioTab = '3d';
        let selectedDatasetClass = 'cube_red';
        let isRecordingDataset = false;
        let datasetRecordTimer = null;
        let trainPollTimer = null;
        let visionPollTimer = null;
        let knownClasses = ['cube_red', 'cube_green', 'cube_blue', 'cube_yellow'];

        // =====================================================================
        // VIDEO WEBSOCKET MANAGER - thay thế MJPEG <img src> không ổn định
        // =====================================================================
        const videoStreams = {};

        function startVideoStream(canvasId, mode) {
            // 1. Nếu stream này đã đang chạy đúng canvas và đúng mode thì giữ nguyên
            const existing = videoStreams[canvasId];
            if (existing && existing.mode === mode && existing.ws && 
                (existing.ws.readyState === WebSocket.OPEN || existing.ws.readyState === WebSocket.CONNECTING)) {
                return;
            }

            // 2. Dừng stream cũ một cách an toàn
            stopVideoStream(canvasId);

            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');

            const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
            const wsUrl = `${protocol}://${location.host}/ws/video?mode=${mode}`;
            const ws = new WebSocket(wsUrl);
            ws.binaryType = 'arraybuffer';

            const streamEntry = { ws, mode, isClosedByUser: false };
            videoStreams[canvasId] = streamEntry;

            ws.onopen = () => {
                console.log(`[VideoWS] ${canvasId} connected (mode=${mode})`);
            };

            ws.onmessage = (event) => {
                if (!(event.data instanceof ArrayBuffer) || event.data.byteLength === 0) return;
                const blob = new Blob([event.data], { type: 'image/jpeg' });
                const url = URL.createObjectURL(blob);
                const img = new Image();
                img.onload = () => {
                    canvas.width = img.naturalWidth || canvas.clientWidth;
                    canvas.height = img.naturalHeight || canvas.clientHeight;
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                    URL.revokeObjectURL(url);
                };
                img.src = url;
            };

            ws.onerror = (e) => {
                if (!streamEntry.isClosedByUser) {
                    console.warn('[VideoWS] error', e);
                }
            };

            ws.onclose = () => {
                console.log(`[VideoWS] ${canvasId} closed (intentional=${streamEntry.isClosedByUser})`);
                if (videoStreams[canvasId] === streamEntry) {
                    videoStreams[canvasId] = null;
                }
                // Chỉ tự động reconnect nếu không phải do người dùng chuyển tab (chủ động đóng)
                if (!streamEntry.isClosedByUser) {
                    setTimeout(() => {
                        const isCurrentTab = (canvasId === 'img-data-stream' && currentStudioTab === 'data') ||
                                             (canvasId === 'img-sort-stream' && currentStudioTab === 'sort');
                        if (isCurrentTab && !videoStreams[canvasId]) {
                            startVideoStream(canvasId, mode);
                        }
                    }, 2000);
                }
            };
        }

        function stopVideoStream(canvasId) {
            const entry = videoStreams[canvasId];
            if (entry) {
                entry.isClosedByUser = true;
                videoStreams[canvasId] = null;
                if (entry.ws) {
                    // Nếu đang CONNECTING, đợi kết nối xong mới đóng để trình duyệt không báo lỗi
                    if (entry.ws.readyState === WebSocket.CONNECTING) {
                        entry.ws.onopen = () => {
                            try { entry.ws.close(); } catch(e) {}
                        };
                    } else if (entry.ws.readyState === WebSocket.OPEN) {
                        try { entry.ws.close(); } catch(e) {}
                    }
                }
            }
        }

        // =====================================================================
        // BỘ QUẢN LÝ TIẾN TRÌNH CÔNG CỤ NATIVE (CAPTURE & AUTO SORT)
        // =====================================================================
        let currentActiveTool = null;
        let toolStatusTimer = null;

        async function checkToolStatus() {
            try {
                const res = await fetch('/api/tool/status');
                const data = await res.json();
                const wasRunning = (currentActiveTool !== null);
                const isRunning = data.is_running;
                currentActiveTool = isRunning ? data.active_tool : null;
                updateToolUiState(isRunning, data.active_tool);

                // Nếu vừa mới đóng công cụ capture, tự động tải lại thống kê ảnh đã chụp
                if (wasRunning && !isRunning) {
                    fetchDatasetStats();
                }
            } catch(e) {}
        }

        function updateToolUiState(isRunning, activeTool) {
            // Tab 2 (Capture)
            const badgeCap = document.getElementById('badge-tool-capture');
            const bannerCap = document.getElementById('banner-tool-capture-running');
            const btnLaunchCap = document.getElementById('btn-launch-capture');
            const btnStopCap = document.getElementById('btn-stop-capture');

            // Tab 4 (Sort)
            const badgeSort = document.getElementById('badge-tool-sort');
            const bannerSort = document.getElementById('banner-tool-sort-running');
            const btnLaunchSort = document.getElementById('btn-launch-sort');
            const btnStopSort = document.getElementById('btn-stop-sort');

            // Tab 5 (Calib)
            const badgeCalib = document.getElementById('badge-tool-calib');
            const bannerCalib = document.getElementById('banner-tool-calib-running');
            const btnLaunchCalib = document.getElementById('btn-launch-calib');
            const btnStopCalib = document.getElementById('btn-stop-calib');

            // Cập nhật Tab 2
            if (isRunning && activeTool === 'capture') {
                if (badgeCap) { badgeCap.className = 'sys-badge online'; badgeCap.innerText = '🔴 Đang mở cửa sổ Camera'; }
                if (bannerCap) bannerCap.style.display = 'block';
                if (btnLaunchCap) btnLaunchCap.style.display = 'none';
                if (btnStopCap) btnStopCap.style.display = 'flex';
            } else {
                if (badgeCap) { badgeCap.className = 'sys-badge offline'; badgeCap.innerText = 'Chưa mở công cụ'; }
                if (bannerCap) bannerCap.style.display = 'none';
                if (btnLaunchCap) btnLaunchCap.style.display = 'flex';
                if (btnStopCap) btnStopCap.style.display = 'none';
            }

            // Cập nhật Tab 4
            if (isRunning && activeTool === 'sort') {
                if (badgeSort) { badgeSort.className = 'sys-badge online'; badgeSort.innerText = '🟢 AI Auto Sort Đang Chạy'; }
                if (bannerSort) bannerSort.style.display = 'block';
                if (btnLaunchSort) btnLaunchSort.style.display = 'none';
                if (btnStopSort) btnStopSort.style.display = 'flex';
            } else {
                if (badgeSort) { badgeSort.className = 'sys-badge offline'; badgeSort.innerText = 'Chưa khởi chạy'; }
                if (bannerSort) bannerSort.style.display = 'none';
                if (btnLaunchSort) btnLaunchSort.style.display = 'flex';
                if (btnStopSort) btnStopSort.style.display = 'none';
            }

            // Cập nhật Tab 5
            if (isRunning && activeTool === 'calib') {
                if (badgeCalib) { badgeCalib.className = 'sys-badge online'; badgeCalib.innerText = '🔵 Đang Mở Hiệu Chuẩn'; }
                if (bannerCalib) bannerCalib.style.display = 'block';
                if (btnLaunchCalib) btnLaunchCalib.style.display = 'none';
                if (btnStopCalib) btnStopCalib.style.display = 'flex';
            } else {
                if (badgeCalib) { badgeCalib.className = 'sys-badge offline'; badgeCalib.innerText = 'Chưa mở công cụ'; }
                if (bannerCalib) bannerCalib.style.display = 'none';
                if (btnLaunchCalib) btnLaunchCalib.style.display = 'flex';
                if (btnStopCalib) btnStopCalib.style.display = 'none';
            }
        }

        async function handleLaunchCaptureTool() {
            if (currentActiveTool && currentActiveTool !== 'capture') {
                showToast("⚠️ Vui lòng dừng công cụ ở Tab kia trước để giải phóng Camera!");
                return;
            }
            const selCam = document.getElementById('sel-cam-tab2');
            const camId = selCam ? selCam.value : '';
            if (camId === '' || camId === null || isNaN(parseInt(camId))) {
                showToast("⚠️ Không tìm thấy camera nào kết nối! Không thể mở công cụ.");
                return;
            }

            showToast(`🔄 Đang mở cửa sổ capture_from_camera (Camera ${camId})...`);
            try {
                const res = await fetch('/api/tool/launch', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        tool: 'capture', 
                        class_name: selectedDatasetClass,
                        cam_id: parseInt(camId)
                    })
                });
                const data = await res.json();
                if (data.success) {
                    showToast("✅ Đã mở cửa sổ Camera! Nhấn phím 'Q' trên cửa sổ để đóng.");
                    checkToolStatus();
                } else {
                    showToast(`❌ ${data.error}`);
                }
            } catch(err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        async function handleLaunchSortTool() {
            if (currentActiveTool && currentActiveTool !== 'sort') {
                showToast("⚠️ Vui lòng dừng công cụ ở Tab kia trước để giải phóng Camera!");
                return;
            }
            const selCam = document.getElementById('sel-cam-tab4');
            const camId = selCam ? selCam.value : '';
            if (camId === '' || camId === null || isNaN(parseInt(camId))) {
                showToast("⚠️ Không tìm thấy camera nào kết nối! Không thể mở công cụ.");
                return;
            }

            showToast(`🔄 Đang khởi chạy dobot_auto_sort (Camera ${camId})...`);
            const modelSel = document.getElementById('sel-vision-model');
            const modelName = modelSel ? modelSel.value : '';
            try {
                const res = await fetch('/api/tool/launch', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        tool: 'sort', 
                        model: modelName,
                        cam_id: parseInt(camId)
                    })
                });
                const data = await res.json();
                if (data.success) {
                    showToast("✅ Đã khởi chạy Auto Sort! Nhấn phím 'Q' trên cửa sổ để dừng.");
                    checkToolStatus();
                } else {
                    showToast(`❌ ${data.error}`);
                }
            } catch(err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        async function handleLaunchCalibTool() {
            if (currentActiveTool && currentActiveTool !== 'calib') {
                showToast("⚠️ Vui lòng dừng công cụ ở Tab kia trước để giải phóng Camera!");
                return;
            }
            const selCam = document.getElementById('sel-cam-tab5');
            const camId = selCam ? selCam.value : '';
            if (camId === '' || camId === null || isNaN(parseInt(camId))) {
                showToast("⚠️ Không tìm thấy camera nào kết nối! Không thể mở công cụ.");
                return;
            }

            showToast(`🔄 Đang mở cửa sổ Hiệu Chuẩn calibrate_camera_to_dobot (Camera ${camId})...`);
            try {
                const res = await fetch('/api/tool/launch', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        tool: 'calib', 
                        cam_id: parseInt(camId)
                    })
                });
                const data = await res.json();
                if (data.success) {
                    showToast("✅ Đã mở cửa sổ Hiệu Chuẩn! Nhấp chuột chọn 4 điểm và nhập X,Y trong Terminal.");
                    checkToolStatus();
                } else {
                    showToast(`❌ ${data.error}`);
                }
            } catch(err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        async function handleStopTool(toolName) {
            showToast("🔄 Đang đóng công cụ & giải phóng camera...");
            try {
                const res = await fetch('/api/tool/stop', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ tool: toolName })
                });
                const data = await res.json();
                showToast("✅ Đã đóng công cụ & Camera đã được giải phóng!");
                checkToolStatus();
                fetchDatasetStats();
                if (toolName === 'calib') fetchCalibInfo();
            } catch(err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        // --- 1. CHUYỂN TAB WEB STUDIO ---
        function switchStudioTab(tabId) {
            currentStudioTab = tabId;
            
            const btnReopenTop = document.getElementById('btn-reopen-panel');
            if (btnReopenTop) {
                btnReopenTop.style.display = (tabId === '3d' && panelEl && panelEl.style.display === 'none') ? 'flex' : 'none';
            }
            
            // Cập nhật nút tab trên Top Navbar
            document.querySelectorAll('.nav-studio-tab').forEach(btn => {
                btn.classList.toggle('active', btn.id === `btn-tab-${tabId}`);
            });

            // Hiển thị view tương ứng
            const tabViews = {
                '3d': 'view-3d-twin',
                'data': 'view-data-collection',
                'train': 'view-ai-trainer',
                'sort': 'view-auto-sort',
                'calib': 'view-camera-calib',
                'hand': 'view-hand-teleop'
            };

            Object.entries(tabViews).forEach(([id, viewId]) => {
                const el = document.getElementById(viewId);
                if (el) el.classList.toggle('active', id === tabId);
            });

            // Quản lý dữ liệu khi chuyển tab
            if (tabId === 'data') {
                fetchDatasetStats();
                fetchCameraDevices();
                checkToolStatus();
            } else if (tabId === 'train') {
                fetchTrainStatus();
            } else if (tabId === 'sort') {
                fetchVisionModels();
                fetchCameraDevices();
                checkToolStatus();
                fetchDropTargets();
            } else if (tabId === 'calib') {
                fetchCameraDevices();
                checkToolStatus();
                fetchCalibInfo();
            } else if (tabId === 'hand') {
                initHandTeleopTab();
            }
        }

        

        // ========================================================
        // BỘ NỘI SUY CHUYỂN ĐỘNG 3D THỜI GIAN THỰC (3D ANIMATION ENGINE)
        // ========================================================


        // =====================================================================
        // --- 4. CẤU HÌNH VỊ TRÍ KHAY THẢ ĐỒ (DROP TARGETS) ---
        // =====================================================================
        let dropTargetsConfig = {
            mode: "all",
            default: { x: 49.2, y: -230.1, z: -44.0, name: "Khay Mặc Định" },
            by_color: {
                cube_red:    { x: 49.2, y: -230.1, z: -44.0, name: "Khay Đỏ" },
                cube_green:  { x: 49.2, y: -230.1, z: -44.0, name: "Khay Xanh Lục" },
                cube_blue:   { x: 49.2, y: -230.1, z: -44.0, name: "Khay Xanh Dương" },
                cube_yellow: { x: 49.2, y: -230.1, z: -44.0, name: "Khay Vàng" }
            }
        };

        async function fetchDropTargets() {
            try {
                const res = await fetch('/api/vision/drop_targets');
                const data = await res.json();
                if (data.status === 'ok' && data.data) {
                    dropTargetsConfig = data.data;
                    if (!dropTargetsConfig.default) {
                        dropTargetsConfig.default = { x: 49.2, y: -230.1, z: -44.0, name: "Khay Mặc Định" };
                    }
                    if (!dropTargetsConfig.by_color) {
                        dropTargetsConfig.by_color = {};
                    }
                    renderDropTargetsUI();
                }
            } catch (err) {
                console.warn("fetchDropTargets error:", err);
            }
        }

        function renderDropTargetsUI() {
            const mode = dropTargetsConfig.mode || 'all';
            const btnAll = document.getElementById('btn-mode-drop-all');
            const btnColor = document.getElementById('btn-mode-drop-color');
            const badgeMode = document.getElementById('badge-drop-mode');

            if (btnAll && btnColor) {
                if (mode === 'all') {
                    btnAll.style.background = '#0284c7';
                    btnAll.style.borderColor = '#38bdf8';
                    btnAll.style.color = '#fff';
                    btnColor.style.background = '#1e293b';
                    btnColor.style.borderColor = '#475569';
                    btnColor.style.color = '#94a3b8';
                    if (badgeMode) {
                        badgeMode.innerText = "Chung 1 khay";
                        badgeMode.style.color = "#38bdf8";
                        badgeMode.style.borderColor = "#38bdf8";
                    }
                } else {
                    btnColor.style.background = '#0284c7';
                    btnColor.style.borderColor = '#38bdf8';
                    btnColor.style.color = '#fff';
                    btnAll.style.background = '#1e293b';
                    btnAll.style.borderColor = '#475569';
                    btnAll.style.color = '#94a3b8';
                    if (badgeMode) {
                        badgeMode.innerText = "Phân theo 4 màu";
                        badgeMode.style.color = "#a855f7";
                        badgeMode.style.borderColor = "#c084fc";
                    }
                }
            }

            const selTray = document.getElementById('sel-drop-tray');
            const currentSelected = selTray ? selTray.value : 'default';
            handleSelectDropTray(currentSelected);

            const inpPickZ = document.getElementById('inp-pick-z');
            const pickZ = (dropTargetsConfig.pick_z !== undefined) ? dropTargetsConfig.pick_z : -54.7;
            if (inpPickZ) {
                inpPickZ.value = pickZ;
                handlePickZChange(pickZ);
            }

            const inpCalibRailL = document.getElementById('inp-calib-rail-l');
            const calibRailL = (dropTargetsConfig.calib_rail_l !== undefined) ? dropTargetsConfig.calib_rail_l : 360.0;
            if (inpCalibRailL) {
                inpCalibRailL.value = calibRailL;
                handleCalibRailLChange(calibRailL);
            }

            renderDropTargetsSummary();
        }

        function handleCalibRailLChange(val) {
            const lNum = parseFloat(val);
            const lblVal = document.getElementById('lbl-calib-rail-val');
            if (!isNaN(lNum) && lblVal) {
                lblVal.innerText = lNum.toFixed(1) + ' mm';
            }
        }

        async function handleAutoFillCalibRailL() {
            try {
                showToast("🔍 Đang đọc vị trí con trượt ray hiện tại từ robot...");
                const res = await fetch('/api/cmd');
                const data = await res.json();
                let l = 360.0;
                if (data.status === 'ok' && data.rail && data.rail.pos !== undefined) {
                    l = Math.round(Number(data.rail.pos) * 10) / 10;
                } else if (typeof currentRailL !== 'undefined') {
                    l = Math.round(Number(currentRailL) * 10) / 10;
                }
                const inpCalibRailL = document.getElementById('inp-calib-rail-l');
                if (inpCalibRailL) {
                    inpCalibRailL.value = l;
                    handleCalibRailLChange(l);
                }
                showToast(`📍 Đã lấy vị trí Ray Calib: L=${l} mm! Nhớ nhấn "Lưu Vị Trí Khay".`);
            } catch(e) {
                showToast(`❌ Lỗi: ${e.message}`);
            }
        }

        async function handleTestMoveToCalibRailL() {
            const inpCalibRailL = document.getElementById('inp-calib-rail-l');
            const l = parseFloat(inpCalibRailL ? inpCalibRailL.value : '360.0') || 360.0;
            if (!confirm(`Bạn có chắc muốn chạy ray về vị trí Calib / Bàn gắp: L=${l} mm?\nRobot sẽ tự động di chuyển ray đến vị trí này.`)) return;
            try {
                showToast(`🚄 Đang di chuyển ray về vị trí Calib L=${l} mm...`);
                const res = await fetch('/api/cmd', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: 'rail_move_to',
                        target_mm: l,
                        target_l: l,
                        speed: 100.0
                    })
                });
                const data = await res.json();
                if (data.status === 'ok' || data.success) {
                    showToast(`✅ Ray đang di chuyển về L=${l} mm!`);
                } else {
                    showToast(`⚠️ ${data.message || data.error || 'Lỗi gửi lệnh'}`);
                }
            } catch(e) {
                showToast(`❌ Lỗi: ${e.message}`);
            }
        }

        function handlePickZChange(val) {
            const zNum = parseFloat(val);
            const lblTcp = document.getElementById('lbl-pick-tcp-val');
            const lblInfo = document.getElementById('lbl-info-pick-z');
            if (!isNaN(zNum)) {
                const tcpZ = (zNum - 59.5).toFixed(1);
                if (lblTcp) lblTcp.innerText = tcpZ + ' mm';
                if (lblInfo) lblInfo.innerText = `${zNum} mm (Mũi hút TCP: ${tcpZ} mm)`;
            }
        }

        async function handleAutoFillPickZ() {
            try {
                showToast("🔍 Đang đọc tọa độ Z tiếp xúc từ Dobot...");
                const res = await fetch('/api/cmd');
                const data = await res.json();
                if (data.status === 'ok' && data.pose && (data.pose.z !== undefined)) {
                    // Robot đang chạm phôi tại pose.z. Hạ tiếp 5.0 mm (0.5 cm) để hút chặt
                    const contactZ = Number(data.pose.z);
                    const targetZ = Math.round((contactZ - 5.0) * 10) / 10;
                    const inpPickZ = document.getElementById('inp-pick-z');
                    if (inpPickZ) {
                        inpPickZ.value = targetZ;
                        handlePickZChange(targetZ);
                    }
                    showToast(`📍 Dobot đang ở Z=${contactZ.toFixed(1)} mm. Đã tính độ sâu gắp: Z=${targetZ} mm (TCP: ${(targetZ - 59.5).toFixed(1)} mm)!`);
                } else {
                    showToast("⚠️ Chưa đọc được tọa độ robot! Hãy kết nối Dobot trước.");
                }
            } catch(e) {
                showToast(`❌ Lỗi: ${e.message}`);
            }
        }

        function handleSelectDropTray(trayKey) {
            let target;
            if (trayKey === 'default') {
                target = dropTargetsConfig.default;
            } else {
                target = (dropTargetsConfig.by_color && dropTargetsConfig.by_color[trayKey]) 
                         ? dropTargetsConfig.by_color[trayKey] 
                         : dropTargetsConfig.default;
            }

            if (target) {
                const inpX = document.getElementById('inp-drop-x');
                const inpY = document.getElementById('inp-drop-y');
                const inpZ = document.getElementById('inp-drop-z');
                const inpL = document.getElementById('inp-drop-l');
                if (inpX) inpX.value = (target.x !== undefined) ? target.x : 49.2;
                if (inpY) inpY.value = (target.y !== undefined) ? target.y : -230.1;
                if (inpZ) inpZ.value = (target.z !== undefined) ? target.z : -44.0;
                if (inpL) inpL.value = (target.l !== undefined ? target.l : (target.rail_l !== undefined ? target.rail_l : 0.0));
            }
        }

        function selectTrayAndEdit(trayKey) {
            const sel = document.getElementById('sel-drop-tray');
            if (sel) {
                sel.value = trayKey;
                handleSelectDropTray(trayKey);
                const optName = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : trayKey;
                showToast(`✏️ Đang sửa tọa độ: ${optName}`);
            }
        }

        async function handleSetDropMode(mode) {
            dropTargetsConfig.mode = mode;
            renderDropTargetsUI();
            try {
                await fetch('/api/vision/drop_targets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dropTargetsConfig)
                });
                showToast(mode === 'all' 
                    ? "📦 Đã đổi sang chế độ: Dùng chung 1 khay cho mọi màu!" 
                    : "🎨 Đã đổi sang chế độ: Phân khay theo màu riêng biệt!");
            } catch (err) {
                console.warn(err);
            }
        }

        async function handleAutoFillDropCoordinates() {
            try {
                showToast("🔍 Đang đọc tọa độ hiện tại từ robot Dobot & Ray trượt...");
                const res = await fetch('/api/cmd');
                const data = await res.json();
                if (data.status === 'ok' && data.pose && (data.pose.x !== undefined)) {
                    const x = Math.round(Number(data.pose.x) * 10) / 10;
                    const y = Math.round(Number(data.pose.y) * 10) / 10;
                    const z = Math.round(Number(data.pose.z) * 10) / 10;

                    let l = 0.0;
                    if (data.rail && data.rail.pos !== undefined) {
                        l = Math.round(Number(data.rail.pos) * 10) / 10;
                    } else if (typeof currentRailL !== 'undefined') {
                        l = Math.round(Number(currentRailL) * 10) / 10;
                    }

                    const inpX = document.getElementById('inp-drop-x');
                    const inpY = document.getElementById('inp-drop-y');
                    const inpZ = document.getElementById('inp-drop-z');
                    const inpL = document.getElementById('inp-drop-l');
                    if (inpX) inpX.value = x;
                    if (inpY) inpY.value = y;
                    if (inpZ) inpZ.value = z;
                    if (inpL) inpL.value = l;

                    showToast(`📍 Đã lấy tọa độ Dobot: X=${x}, Y=${y}, Z=${z}, Ray L=${l} mm! Nhớ nhấn "Lưu Vị Trí Khay".`);
                } else {
                    showToast("⚠️ Chưa đọc được tọa độ! Hãy kiểm tra kết nối Dobot ở góc trên bên phải.");
                }
            } catch (err) {
                showToast(`❌ Lỗi đọc tọa độ Dobot: ${err.message}`);
            }
        }

        async function handleSaveDropTargets() {
            const inpX = document.getElementById('inp-drop-x');
            const inpY = document.getElementById('inp-drop-y');
            const inpZ = document.getElementById('inp-drop-z');
            const inpL = document.getElementById('inp-drop-l');
            const selTray = document.getElementById('sel-drop-tray');

            const x = parseFloat(inpX ? inpX.value : '');
            const y = parseFloat(inpY ? inpY.value : '');
            const z = parseFloat(inpZ ? inpZ.value : '');
            const l = parseFloat(inpL ? inpL.value : '0') || 0.0;

            if (isNaN(x) || isNaN(y) || isNaN(z)) {
                showToast("⚠️ Vui lòng nhập số hợp lệ cho các trục X, Y, Z, L!");
                return;
            }

            const selKey = selTray ? selTray.value : 'default';
            if (selKey === 'default') {
                dropTargetsConfig.default = { x, y, z, l, rail_l: l, name: "Khay Mặc Định" };
                // Nếu đang dùng mode 'all', đồng bộ luôn cả 4 màu
                if (dropTargetsConfig.mode === 'all' && dropTargetsConfig.by_color) {
                    for (const k of Object.keys(dropTargetsConfig.by_color)) {
                        dropTargetsConfig.by_color[k].x = x;
                        dropTargetsConfig.by_color[k].y = y;
                        dropTargetsConfig.by_color[k].z = z;
                        dropTargetsConfig.by_color[k].l = l;
                        dropTargetsConfig.by_color[k].rail_l = l;
                    }
                }
            } else {
                const names = {
                    'cube_red': 'Khay Đỏ',
                    'cube_green': 'Khay Xanh Lục',
                    'cube_blue': 'Khay Xanh Dương',
                    'cube_yellow': 'Khay Vàng'
                };
                if (!dropTargetsConfig.by_color) dropTargetsConfig.by_color = {};
                dropTargetsConfig.by_color[selKey] = {
                    x, y, z, l, rail_l: l,
                    name: names[selKey] || selKey
                };
            }

            const inpPickZ = document.getElementById('inp-pick-z');
            if (inpPickZ) {
                const pz = parseFloat(inpPickZ.value);
                if (!isNaN(pz)) {
                    dropTargetsConfig.pick_z = pz;
                }
            }

            const inpCalibRailL = document.getElementById('inp-calib-rail-l');
            if (inpCalibRailL) {
                const cl = parseFloat(inpCalibRailL.value);
                if (!isNaN(cl)) {
                    dropTargetsConfig.calib_rail_l = cl;
                }
            }

            try {
                showToast("💾 Đang lưu vị trí khay thả, L Calib & độ cao Z gắp...");
                const res = await fetch('/api/vision/drop_targets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dropTargetsConfig)
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast("✅ Đã lưu vị trí thả đồ thành công!");
                    renderDropTargetsUI();
                } else {
                    showToast(`❌ Lỗi lưu: ${data.message}`);
                }
            } catch (err) {
                showToast(`❌ Lỗi mạng: ${err.message}`);
            }
        }

        async function handleTestMoveToDropTarget() {
            const inpX = document.getElementById('inp-drop-x');
            const inpY = document.getElementById('inp-drop-y');
            const inpZ = document.getElementById('inp-drop-z');
            const inpL = document.getElementById('inp-drop-l');

            const x = parseFloat(inpX ? inpX.value : '');
            const y = parseFloat(inpY ? inpY.value : '');
            const z = parseFloat(inpZ ? inpZ.value : '');
            const l = parseFloat(inpL ? inpL.value : '0') || 0.0;

            if (isNaN(x) || isNaN(y) || isNaN(z)) {
                showToast("⚠️ Vui lòng nhập tọa độ hợp lệ trước khi bay thử!");
                return;
            }

            if (!confirm(`Bạn có chắc chắn muốn Dobot bay thử đến tọa độ khay: (X=${x}, Y=${y}, Z=${z}, Ray L=${l}) mm?\nRobot sẽ tự động di chuyển ray và nhấc lên cao an toàn trước khi di chuyển.`)) {
                return;
            }

            try {
                showToast(`🚀 Đang điều khiển Dobot bay an toàn tới (X=${x}, Y=${y}, Z=${z}, L=${l})...`);
                const res = await fetch('/api/cmd', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: 'safe_jump',
                        x: x,
                        y: y,
                        z: z,
                        l: l,
                        rail_l: l,
                        r: 0,
                        safe_z: 35.0
                    })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast("✅ Dobot đã bay tới vị trí khay thả an toàn!");
                } else {
                    showToast("❌ Không thể di chuyển robot! Vui lòng kiểm tra kết nối.");
                }
            } catch (err) {
                showToast(`❌ Lỗi: ${err.message}`);
            }
        }

        function renderDropTargetsSummary() {
            const sumEl = document.getElementById('drop-targets-summary');
            if (!sumEl) return;
            const mode = dropTargetsConfig.mode || 'all';
            const def = dropTargetsConfig.default || { x: 49.2, y: -230.1, z: -44.0, l: 0.0 };
            const byColor = dropTargetsConfig.by_color || {};

            const items = [
                { key: 'cube_red', name: 'Đỏ', col: '#ef4444', data: byColor.cube_red || def },
                { key: 'cube_green', name: 'Lục', col: '#22c55e', data: byColor.cube_green || def },
                { key: 'cube_blue', name: 'Dương', col: '#3b82f6', data: byColor.cube_blue || def },
                { key: 'cube_yellow', name: 'Vàng', col: '#eab308', data: byColor.cube_yellow || def }
            ];

            sumEl.innerHTML = items.map(it => {
                const t = (mode === 'all') ? def : it.data;
                const trayL = (t.l !== undefined ? t.l : (t.rail_l !== undefined ? t.rail_l : 0.0));
                return `
                    <div onclick="selectTrayAndEdit('${it.key}')" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 5px 8px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; transition: all 0.2s;" title="Nhấp để xem hoặc sửa tọa độ khay ${it.name}">
                        <div style="display: flex; align-items: center; gap: 5px;">
                            <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${it.col};"></span>
                            <span style="color: #cbd5e1; font-weight: 600;">${it.name}:</span>
                        </div>
                        <span style="color: #38bdf8; font-family: monospace; font-weight: 700;">(${t.x}, ${t.y}, L=${trayL})</span>
                    </div>
                `;
            }).join('');

            const infoEl = document.getElementById('lbl-info-drop-coords');
            if (infoEl) {
                if (mode === 'all') {
                    infoEl.innerText = `X = ${def.x} mm, Y = ${def.y} mm`;
                } else {
                    infoEl.innerText = `Theo từng màu (Đỏ, Lục, Dương, Vàng)`;
                }
            }
        }

        // --- PHÍM TẮT BÀN PHÍM TÍCH HỢP ---
        window.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'm' || e.key === 'M') {
                if (currentStudioTab === '3d') togglePanel();
            } else if (e.code === 'Space') {
                if (currentStudioTab === 'data') {
                    e.preventDefault();
                    triggerSingleCapture();
                }
            } else if (e.key === 'r' || e.key === 'R') {
                if (currentStudioTab === 'data') {
                    e.preventDefault();
                    toggleContinuousRecording();
                }
            }
        });
