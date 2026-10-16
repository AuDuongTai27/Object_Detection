// =========================================================================
// --- MODULE: TRỢ LÝ GIỌNG NÓI AI & PHÂN TÍCH LỆNH (VOICE ASSISTANT STT/TTS) ---
// =========================================================================

class DobotVoiceController {
    constructor() {
        this.recognition = null;
        this.isListening = false;
        this.currentTranscript = "";
        this.isConfirmRequired = true;
        this.isTTSEnabled = true;
        this.pendingAction = null;
        this.confirmTimer = null;
        this.vietnameseVoice = null;

        this.initSettings();
        this.initSpeechRecognition();
        this.initSpeechSynthesis();
        this.bindEvents();
    }

    async initSettings() {
        try {
            const res = await fetch("/api/vision/voice_config");
            const resData = await res.json();
            if (resData.status === "ok" && resData.data) {
                if (typeof resData.data.confirm_required === "boolean") {
                    this.isConfirmRequired = resData.data.confirm_required;
                }
                if (typeof resData.data.tts_enabled === "boolean") {
                    this.isTTSEnabled = resData.data.tts_enabled;
                }
            }
        } catch (e) {
            const savedConfirm = localStorage.getItem("dobot_voice_confirm_required");
            if (savedConfirm !== null) this.isConfirmRequired = savedConfirm === "true";
            const savedTTS = localStorage.getItem("dobot_voice_tts_enabled");
            if (savedTTS !== null) this.isTTSEnabled = savedTTS === "true";
        }

        setTimeout(() => {
            const chkConfirm = document.getElementById("chk-voice-confirm-required");
            if (chkConfirm) chkConfirm.checked = this.isConfirmRequired;
            const chkTTS = document.getElementById("chk-voice-tts-feedback");
            if (chkTTS) chkTTS.checked = this.isTTSEnabled;
        }, 300);
    }

    async saveSettings() {
        localStorage.setItem("dobot_voice_confirm_required", this.isConfirmRequired);
        localStorage.setItem("dobot_voice_tts_enabled", this.isTTSEnabled);
        try {
            await fetch("/api/vision/voice_config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    confirm_required: this.isConfirmRequired,
                    tts_enabled: this.isTTSEnabled
                })
            });
        } catch (e) {
            console.warn("[VoiceAI] Error saving voice config to backend:", e);
        }
    }

    setConfirmRequired(enable) {
        this.isConfirmRequired = !!enable;
        this.saveSettings();
        console.log(`[VoiceAI] Yêu cầu xác nhận an toàn: ${this.isConfirmRequired}`);
    }

    setTTSEnabled(enable) {
        this.isTTSEnabled = !!enable;
        this.saveSettings();
        console.log(`[VoiceAI] Phản hồi giọng nói TTS: ${this.isTTSEnabled}`);
    }

    // --- 1. KHỞI TẠO BỘ NHẬN DIỆN GIỌNG NÓI (STT) ---
    initSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            console.warn("[VoiceAI] Trình duyệt không hỗ trợ Web Speech API!");
            this.updateStatusBadge("Không hỗ trợ", "error");
            return;
        }

        this.recognition = new SpeechRecognition();
        this.recognition.lang = "vi-VN";
        this.recognition.continuous = false;
        this.recognition.interimResults = true;
        this.recognition.maxAlternatives = 1;

        this.recognition.onstart = () => {
            this.isListening = true;
            this.currentTranscript = "";
            this.updateUIListening(true);
            this.updateStatusBadge("Đang lắng nghe...", "listening");
        };

        this.recognition.onresult = (event) => {
            let interimTranscript = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                const text = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    this.currentTranscript = text;
                } else {
                    interimTranscript += text;
                }
            }
            const display = this.currentTranscript || interimTranscript;
            this.updateTranscriptDisplay(display);
        };

        this.recognition.onerror = (event) => {
            console.warn("[VoiceAI] Lỗi nhận diện:", event.error);
            this.isListening = false;
            this.updateUIListening(false);
            if (event.error === "no-speech") {
                this.updateTranscriptDisplay("Không nghe thấy giọng nói. Hãy thử lại!");
                this.updateStatusBadge("Chưa nhận diện", "idle");
            } else if (event.error === "not-allowed") {
                this.updateTranscriptDisplay("Micro bị chặn! Hãy cấp quyền truy cập Micro trên trình duyệt.");
                this.updateStatusBadge("Bị chặn quyền", "error");
            } else {
                this.updateStatusBadge("Lỗi: " + event.error, "error");
            }
        };

        this.recognition.onend = () => {
            this.isListening = false;
            this.updateUIListening(false);
            if (this.currentTranscript && this.currentTranscript.trim()) {
                this.handleVoiceCommand(this.currentTranscript.trim());
            } else {
                this.updateStatusBadge("Sẵn sàng", "idle");
            }
        };
    }

    // --- 2. KHỞI TẠO PHÁT ÂM TIẾNG VIỆT (TTS) ---
    initSpeechSynthesis() {
        if (!("speechSynthesis" in window)) {
            console.warn("[VoiceAI] Trình duyệt không hỗ trợ Text-to-Speech!");
            return;
        }

        const updateVoices = () => {
            const voices = window.speechSynthesis.getVoices();
            // Ưu tiên các giọng tiếng Việt chất lượng cao
            this.vietnameseVoice = voices.find(v => v.lang === "vi-VN" || v.lang.startsWith("vi")) || null;
            if (this.vietnameseVoice) {
                console.log(`[VoiceAI] Đã nạp giọng đọc: ${this.vietnameseVoice.name}`);
            }
        };

        updateVoices();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {
            window.speechSynthesis.onvoiceschanged = updateVoices;
        }
    }

    speak(text) {
        if (!this.isTTSEnabled || !("speechSynthesis" in window) || !text) return;
        try {
            window.speechSynthesis.cancel(); // Dừng câu nói cũ
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = "vi-VN";
            utterance.rate = 1.05;
            utterance.pitch = 1.0;
            if (this.vietnameseVoice) {
                utterance.voice = this.vietnameseVoice;
            }
            window.speechSynthesis.speak(utterance);
        } catch (e) {
            console.warn("[VoiceAI] TTS error:", e);
        }
    }

    // --- 3. ĐIỀU KHIỂN PUSH-TO-TALK (HOLD TO TALK) ---
    startListening() {
        if (!this.recognition) {
            alert("Trình duyệt của bạn không hỗ trợ Web Speech API (Khuyên dùng Google Chrome hoặc Microsoft Edge).");
            return;
        }
        if (this.isListening) return;

        try {
            window.speechSynthesis.cancel();
            this.currentTranscript = "";
            this.recognition.start();
        } catch (e) {
            console.warn("[VoiceAI] Không thể start recognition:", e);
        }
    }

    stopListening() {
        if (!this.recognition || !this.isListening) return;
        try {
            this.recognition.stop();
        } catch (e) {
            console.warn("[VoiceAI] Không thể stop recognition:", e);
        }
    }

    // --- 4. BỘ PHÂN TÍCH CÂU LỆNH GIỌNG NÓI (INTENT PARSER) ---
    parseIntent(rawText) {
        const text = rawText.toLowerCase().trim();

        // 1. Gắp khối phôi theo màu
        if (text.includes("gắp") || text.includes("lấy") || text.includes("pick") || text.includes("nhặt") || text.includes("khối")) {
            if (text.includes("đỏ") || text.includes("red") || text.includes("hồng")) {
                return { action: "pick_color", color: "cube_red", colorName: "màu đỏ" };
            }
            if (text.includes("xanh dương") || text.includes("dương") || text.includes("biển") || text.includes("da trời") || text.includes("blue")) {
                return { action: "pick_color", color: "cube_blue", colorName: "màu xanh dương" };
            }
            if (text.includes("xanh lá") || text.includes("xanh lục") || text.includes("lá") || text.includes("green") || text.includes("xanh")) {
                return { action: "pick_color", color: "cube_green", colorName: "màu xanh lục" };
            }
            if (text.includes("vàng") || text.includes("yellow") || text.includes("cam")) {
                return { action: "pick_color", color: "cube_yellow", colorName: "màu vàng" };
            }
            if (text.includes("tất cả") || text.includes("hết")) {
                return { action: "auto_sort", enable: true, label: "Tự động phân loại tất cả" };
            }
            // Mặc định nếu chỉ nói "gắp" mà không nói màu -> gắp khối đầu tiên
            return { action: "pick_first", label: "Gắp khối phôi đầu tiên" };
        }

        // 2. Chế độ Tự Động Phân Loại (Auto Sort)
        if (text.includes("tự động") || text.includes("auto") || text.includes("phân loại")) {
            if (text.includes("dừng") || text.includes("tắt") || text.includes("ngừng") || text.includes("hủy")) {
                return { action: "auto_sort", enable: false, label: "Dừng tự động phân loại" };
            }
            return { action: "auto_sort", enable: true, label: "Bật tự động phân loại" };
        }

        // 3. Dừng lại / Khẩn cấp
        if (text.includes("dừng") || text.includes("ngừng") || text.includes("tắt") || text.includes("stop") || text.includes("hủy")) {
            return { action: "stop", label: "Dừng mọi hoạt động" };
        }

        // 4. Vị trí an toàn / Home
        if (text.includes("an toàn") || text.includes("về nhà") || text.includes("home") || text.includes("nghỉ") || text.includes("về chỗ")) {
            return { action: "safe_home", label: "Về vị trí an toàn" };
        }

        // 5. Đếm số khối phôi
        if (text.includes("bao nhiêu") || text.includes("mấy") || text.includes("đếm") || text.includes("số lượng")) {
            return { action: "count_cubes", label: "Đếm số khối vật thể" };
        }

        return null;
    }

    // --- 5. XỬ LÝ LỆNH & KIỂM TRA XÁC NHẬN AN TOÀN ---
    async handleVoiceCommand(transcript) {
        console.log(`[VoiceAI] Nhận diện câu nói: "${transcript}"`);
        const intent = this.parseIntent(transcript);

        if (!intent) {
            const failMsg = "Không thể thực hiện yêu cầu, vui lòng nói lại!";
            this.updateTranscriptDisplay(`❓ Không hiểu lệnh: "${transcript}"`);
            this.updateStatusBadge("Không hiểu lệnh", "error");
            this.speak(failMsg);
            if (typeof showToast === "function") showToast("❓ " + failMsg);
            return;
        }

        // Chuẩn bị thông điệp và lời thoại xác nhận
        let confirmText = "";
        let actionDesc = "";

        if (intent.action === "pick_color") {
            confirmText = `Bạn có chắc chắn muốn gắp khối ${intent.colorName} không?`;
            actionDesc = `Gắp khối ${intent.colorName}`;
        } else if (intent.action === "pick_first") {
            confirmText = "Bạn có chắc chắn muốn gắp khối đầu tiên trên bàn không?";
            actionDesc = "Gắp khối đầu tiên";
        } else if (intent.action === "auto_sort") {
            confirmText = intent.enable ? "Xác nhận bật chế độ tự động phân loại toàn bộ?" : "Xác nhận dừng chế độ tự động phân loại?";
            actionDesc = intent.label;
        } else if (intent.action === "safe_home") {
            confirmText = "Xác nhận đưa cánh tay robot về vị trí an toàn?";
            actionDesc = "Về vị trí an toàn";
        } else if (intent.action === "stop") {
            // Lệnh dừng thì thực hiện ngay lập tức không cần chờ xác nhận
            this.executeAction(intent);
            return;
        } else if (intent.action === "count_cubes") {
            // Lệnh hỏi thông tin thì trả lời ngay
            this.executeAction(intent);
            return;
        }

        // Kiểm tra cấu hình có yêu cầu xác nhận trước khi thực hiện hay không
        if (this.isConfirmRequired) {
            this.showConfirmDialog(actionDesc, confirmText, intent);
        } else {
            this.executeAction(intent);
        }
    }

    // --- 6. HỘP THOẠI XÁC NHẬN AN TOÀN (SAFETY CONFIRMATION MODAL) ---
    showConfirmDialog(title, speakText, intent) {
        this.pendingAction = intent;
        this.speak(speakText);

        const modal = document.getElementById("voice-confirm-modal");
        const msgEl = document.getElementById("voice-confirm-message");
        if (modal && msgEl) {
            msgEl.innerHTML = `Yêu cầu: <b style="color:#facc15;">${title}</b><br><span style="font-size:12px; color:#cbd5e1;">${speakText}</span>`;
            modal.style.display = "flex";
        }

        // Tự động hủy sau 10 giây nếu người dùng không bấm xác nhận
        if (this.confirmTimer) clearTimeout(this.confirmTimer);
        this.confirmTimer = setTimeout(() => {
            this.cancelConfirmation("Hết thời gian chờ xác nhận");
        }, 10000);
    }

    confirmAction() {
        if (this.confirmTimer) clearTimeout(this.confirmTimer);
        const modal = document.getElementById("voice-confirm-modal");
        if (modal) modal.style.display = "none";

        if (this.pendingAction) {
            const actionToExec = this.pendingAction;
            this.pendingAction = null;
            this.executeAction(actionToExec);
        }
    }

    cancelConfirmation(reason = "Đã hủy lệnh") {
        if (this.confirmTimer) clearTimeout(this.confirmTimer);
        const modal = document.getElementById("voice-confirm-modal");
        if (modal) modal.style.display = "none";
        this.pendingAction = null;

        this.updateTranscriptDisplay(`❌ ${reason}`);
        this.updateStatusBadge("Đã hủy", "idle");
        this.speak("Đã hủy yêu cầu.");
        if (typeof showToast === "function") showToast("❌ Đã hủy yêu cầu giọng nói.");
    }

    // --- 7. THỰC THI HÀNH ĐỘNG VỚI DOBOT & CAMERA ---
    async executeAction(intent) {
        this.updateStatusBadge("Đang thực hiện...", "busy");

        // 1. Gắp khối theo màu
        if (intent.action === "pick_color") {
            await this.executePickColor(intent.color, intent.colorName);
        }
        // 2. Gắp khối đầu tiên
        else if (intent.action === "pick_first") {
            await this.executePickFirst();
        }
        // 3. Bật/Tắt tự động phân loại
        else if (intent.action === "auto_sort") {
            await this.executeToggleAutoSort(intent.enable);
        }
        // 4. Về vị trí an toàn
        else if (intent.action === "safe_home") {
            await this.executeSafeHome();
        }
        // 5. Dừng hoạt động
        else if (intent.action === "stop") {
            await this.executeStop();
        }
        // 6. Đếm số khối
        else if (intent.action === "count_cubes") {
            await this.executeCountCubes();
        }
    }

    async executePickColor(colorClass, colorName) {
        this.updateTranscriptDisplay(`⏳ Đang tìm khối ${colorName}...`);
        try {
            // Lấy danh sách phôi đang phát hiện
            const res = await fetch("/api/vision/status");
            const data = await res.json();
            const cubes = data.detected_cubes || [];

            // Tìm khối có màu tương ứng
            const targetCube = cubes.find(c => c.class_name === colorClass);

            if (!targetCube) {
                const msg = `Không tìm thấy khối ${colorName} nào trên bàn thao tác!`;
                this.updateTranscriptDisplay(`⚠️ ${msg}`);
                this.updateStatusBadge("Không tìm thấy", "error");
                this.speak(msg);
                if (typeof showToast === "function") showToast("⚠️ " + msg);
                return;
            }

            const dx = (targetCube.dobot_x !== undefined && targetCube.dobot_x !== null) ? targetCube.dobot_x : targetCube.dobot_coord?.x;
            const dy = (targetCube.dobot_y !== undefined && targetCube.dobot_y !== null) ? targetCube.dobot_y : targetCube.dobot_coord?.y;

            if (dx === null || dy === null || dx === undefined || dy === undefined) {
                const msg = `Khối ${colorName} chưa có tọa độ hiệu chuẩn!`;
                this.speak(msg);
                if (typeof showToast === "function") showToast("⚠️ " + msg);
                return;
            }

            this.updateTranscriptDisplay(`🚀 Đang gắp khối ${colorName} tại (${dx}, ${dy})...`);
            this.speak(`Đang tiến hành gắp khối ${colorName}.`);
            if (typeof showToast === "function") showToast(`🚀 Bắt đầu gắp ${colorName}...`);

            // Gửi lệnh gắp
            const pickRes = await fetch("/api/vision/pick", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ dobot_x: dx, dobot_y: dy, class_name: colorClass })
            });
            const pickData = await pickRes.json();

            if (pickData.status === "ok" || pickData.success) {
                const successMsg = `Đã hoàn thành gắp khối ${colorName}!`;
                this.updateTranscriptDisplay(`✅ ${successMsg}`);
                this.updateStatusBadge("Hoàn thành", "success");
                this.speak(successMsg);
                if (typeof showToast === "function") showToast("✅ " + successMsg);
            } else {
                const errMsg = `Không thể gắp khối: ${pickData.message || pickData.error || "Lỗi robot"}`;
                this.updateTranscriptDisplay(`❌ ${errMsg}`);
                this.updateStatusBadge("Thất bại", "error");
                this.speak(errMsg);
                if (typeof showToast === "function") showToast("❌ " + errMsg);
            }
        } catch (e) {
            console.error(e);
            const err = "Lỗi kết nối khi gửi lệnh gắp phôi!";
            this.updateTranscriptDisplay(`❌ ${err}`);
            this.updateStatusBadge("Lỗi mạng", "error");
            this.speak(err);
        }
    }

    async executePickFirst() {
        try {
            const res = await fetch("/api/vision/status");
            const data = await res.json();
            const cubes = data.detected_cubes || [];

            if (cubes.length === 0) {
                const msg = "Không phát hiện khối màu nào trên bàn thao tác!";
                this.speak(msg);
                if (typeof showToast === "function") showToast("⚠️ " + msg);
                return;
            }

            const firstCube = cubes[0];
            const dx = firstCube.dobot_x || firstCube.dobot_coord?.x;
            const dy = firstCube.dobot_y || firstCube.dobot_coord?.y;

            this.speak(`Đang gắp khối ${firstCube.class_name}.`);
            const pickRes = await fetch("/api/vision/pick", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ dobot_x: dx, dobot_y: dy, class_name: firstCube.class_name })
            });
            const pickData = await pickRes.json();
            if (pickData.status === "ok" || pickData.success) {
                this.speak("Đã gắp thành công!");
                this.updateStatusBadge("Hoàn thành", "success");
            } else {
                this.speak("Không thể gắp khối vật thể!");
            }
        } catch (e) {
            this.speak("Lỗi kết nối tới hệ thống Dobot!");
        }
    }

    async executeToggleAutoSort(enable) {
        try {
            const res = await fetch("/api/vision/auto_sort", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enable: !!enable })
            });
            const data = await res.json();
            const chkAuto = document.getElementById("chk-auto-sort");
            if (chkAuto) chkAuto.checked = !!enable;

            const msg = enable ? "Đã bật chế độ tự động phân loại!" : "Đã tắt chế độ tự động phân loại!";
            this.updateTranscriptDisplay(`⚡ ${msg}`);
            this.updateStatusBadge(enable ? "Auto ON" : "Auto OFF", "success");
            this.speak(msg);
            if (typeof showToast === "function") showToast(msg);
        } catch (e) {
            this.speak("Lỗi khi điều khiển chế độ tự động!");
        }
    }

    async executeSafeHome() {
        try {
            // Gửi lệnh về tọa độ an toàn chuẩn
            const res = await fetch("/api/cmd", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ type: "ptp", x: 200.0, y: 0.0, z: 35.0, r: 0.0 })
            });
            const msg = "Đã đưa robot về vị trí an toàn!";
            this.updateTranscriptDisplay(`🛡️ ${msg}`);
            this.updateStatusBadge("An toàn", "success");
            this.speak(msg);
            if (typeof showToast === "function") showToast("🛡️ " + msg);
        } catch (e) {
            this.speak("Không thể điều khiển robot về vị trí an toàn!");
        }
    }

    async executeStop() {
        try {
            await fetch("/api/vision/auto_sort", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enable: false })
            });
            const chkAuto = document.getElementById("chk-auto-sort");
            if (chkAuto) chkAuto.checked = false;

            const msg = "Đã dừng toàn bộ chu trình phân loại!";
            this.updateTranscriptDisplay(`⏹️ ${msg}`);
            this.updateStatusBadge("Đã dừng", "idle");
            this.speak(msg);
            if (typeof showToast === "function") showToast("⏹️ " + msg);
        } catch (e) {
            this.speak("Lỗi dừng chu trình!");
        }
    }

    async executeCountCubes() {
        try {
            const res = await fetch("/api/vision/status");
            const data = await res.json();
            const count = (data.detected_cubes || []).length;
            const msg = `Hiện tại có ${count} khối vật thể đang được phát hiện trên bàn.`;
            this.updateTranscriptDisplay(`📊 ${msg}`);
            this.updateStatusBadge(`${count} khối`, "success");
            this.speak(msg);
            if (typeof showToast === "function") showToast(`📊 ${msg}`);
        } catch (e) {
            this.speak("Không đọc được số lượng khối phôi!");
        }
    }

    // --- 8. CẬP NHẬT GIAO DIỆN & EVENT LISTENERS ---
    updateUIListening(listening) {
        const btn = document.getElementById("btn-voice-hold-talk");
        const icon = document.getElementById("voice-btn-icon");
        const text = document.getElementById("voice-btn-text");
        const dot = document.getElementById("voice-live-dot");

        if (!btn) return;

        if (listening) {
            btn.style.background = "linear-gradient(135deg, #dc2626, #ef4444)";
            btn.style.borderColor = "#f87171";
            btn.style.boxShadow = "0 0 20px rgba(239, 68, 68, 0.6)";
            if (text) text.innerText = "ĐANG THU ÂM (THẢ TAY ĐỂ GỬI LỆNH)...";
            if (icon) icon.innerText = "🔴";
            if (dot) dot.style.display = "inline";
        } else {
            btn.style.background = "linear-gradient(135deg, #7c3aed, #9333ea)";
            btn.style.borderColor = "#c084fc";
            btn.style.boxShadow = "0 4px 14px rgba(147, 51, 234, 0.35)";
            if (text) text.innerText = "NHẤN GIỮ ĐỂ NÓI (HOLD TO TALK)";
            if (icon) icon.innerText = "🎙️";
            if (dot) dot.style.display = "none";
        }
    }

    updateTranscriptDisplay(text) {
        const el = document.getElementById("voice-transcript-text");
        if (el) el.innerText = text;
    }

    updateStatusBadge(text, state) {
        const badge = document.getElementById("voice-status-badge");
        if (!badge) return;
        badge.innerText = text;

        if (state === "listening") {
            badge.style.background = "rgba(239, 68, 68, 0.2)";
            badge.style.borderColor = "#ef4444";
            badge.style.color = "#f87171";
        } else if (state === "busy") {
            badge.style.background = "rgba(245, 158, 11, 0.2)";
            badge.style.borderColor = "#f59e0b";
            badge.style.color = "#fbbf24";
        } else if (state === "success") {
            badge.style.background = "rgba(34, 197, 94, 0.2)";
            badge.style.borderColor = "#22c55e";
            badge.style.color = "#4ade80";
        } else if (state === "error") {
            badge.style.background = "rgba(239, 68, 68, 0.2)";
            badge.style.borderColor = "#ef4444";
            badge.style.color = "#f87171";
        } else {
            badge.style.background = "rgba(168, 85, 247, 0.15)";
            badge.style.borderColor = "#a855f7";
            badge.style.color = "#c084fc";
        }
    }

    bindEvents() {
        document.addEventListener("DOMContentLoaded", () => {
            this.setupButtonHold();
            this.setupConfirmModal();
        });
        // Trường hợp file load sau DOMContentLoaded
        if (document.readyState === "complete" || document.readyState === "interactive") {
            this.setupButtonHold();
            this.setupConfirmModal();
        }
    }

    setupButtonHold() {
        const btn = document.getElementById("btn-voice-hold-talk");
        if (!btn || btn._hasVoiceEvents) return;
        btn._hasVoiceEvents = true;

        // Chuột máy tính (Hold = Mousedown, Release = Mouseup/Mouseleave)
        btn.addEventListener("mousedown", (e) => {
            e.preventDefault();
            this.startListening();
        });

        btn.addEventListener("mouseup", (e) => {
            e.preventDefault();
            this.stopListening();
        });

        btn.addEventListener("mouseleave", (e) => {
            e.preventDefault();
            this.stopListening();
        });

        // Màn hình cảm ứng / Mobile (Touchstart, Touchend)
        btn.addEventListener("touchstart", (e) => {
            e.preventDefault();
            this.startListening();
        });

        btn.addEventListener("touchend", (e) => {
            e.preventDefault();
            this.stopListening();
        });
    }

    setupConfirmModal() {
        const btnOk = document.getElementById("btn-voice-confirm-ok");
        const btnCancel = document.getElementById("btn-voice-confirm-cancel");

        if (btnOk && !btnOk._hasConfirmEvent) {
            btnOk._hasConfirmEvent = true;
            btnOk.addEventListener("click", () => this.confirmAction());
        }

        if (btnCancel && !btnCancel._hasConfirmEvent) {
            btnCancel._hasConfirmEvent = true;
            btnCancel.addEventListener("click", () => this.cancelConfirmation("Người dùng đã hủy lệnh"));
        }

        // Bắt phím Enter / Escape cho modal xác nhận
        window.addEventListener("keydown", (e) => {
            const modal = document.getElementById("voice-confirm-modal");
            if (modal && modal.style.display === "flex") {
                if (e.key === "Enter") {
                    e.preventDefault();
                    this.confirmAction();
                } else if (e.key === "Escape") {
                    e.preventDefault();
                    this.cancelConfirmation("Người dùng nhấn Escape để hủy");
                }
            }
        });
    }
}

// Khởi tạo Singleton Voice Controller toàn cục
window.dobotVoice = new DobotVoiceController();

function handleToggleVoiceConfirm(checked) {
    if (window.dobotVoice) {
        window.dobotVoice.setConfirmRequired(checked);
    }
}

function handleToggleVoiceTTS(checked) {
    if (window.dobotVoice) {
        window.dobotVoice.setTTSEnabled(checked);
    }
}
