// =========================================================================
// --- MODULE: 3D DIGITAL TWIN, KINEMATICS & ANIMATION ENGINES ---
// =========================================================================

        // --- Three.js Setup ---
        const container = document.getElementById('canvas-container');
        const scene = new THREE.Scene();
        
        scene.background = new THREE.Color(0xb4d7ec);
        scene.fog = new THREE.Fog(0xb4d7ec, 600, 2400);

        const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 1, 4000);
        camera.position.set(450, 280, 400);

        const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;
        container.appendChild(renderer.domElement);

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.target.set(80, 110, 0);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.update();

        // Ánh sáng
        const hemiLight = new THREE.HemisphereLight(0xffffff, 0x556b2f, 0.85);
        scene.add(hemiLight);

        const dirLight = new THREE.DirectionalLight(0xffffff, 1.15);
        dirLight.position.set(250, 500, 300);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.width = 2048;
        dirLight.shadow.mapSize.height = 2048;
        const d = 350;
        dirLight.shadow.camera.left = -d;
        dirLight.shadow.camera.right = d;
        dirLight.shadow.camera.top = d;
        dirLight.shadow.camera.bottom = -d;
        scene.add(dirLight);

        const fillLight = new THREE.DirectionalLight(0xa5c9eb, 0.45);
        fillLight.position.set(-300, 200, -200);
        scene.add(fillLight);

        // Sàn Simulator (Hỗ trợ bán trong suốt để nhìn thấy mục tiêu dưới sàn khi kéo sâu)
        const floorMat = new THREE.MeshStandardMaterial({ color: 0x3d7a46, roughness: 0.8, metalness: 0.1, transparent: true, opacity: 0.88 });
        const floor = new THREE.Mesh(new THREE.PlaneGeometry(3000, 3000), floorMat);
        floor.rotation.x = -Math.PI / 2;
        floor.position.y = -0.5;
        floor.receiveShadow = true;
        scene.add(floor);

        const gridHelper = new THREE.GridHelper(1000, 40, 0x8ce99a, 0x2b5733);
        gridHelper.position.y = 0;
        scene.add(gridHelper);

        const globalAxes = new THREE.AxesHelper(140);
        globalAxes.position.set(0, 0.5, 0);
        scene.add(globalAxes);

        // =========================================================================
        // VẬT LIỆU (MATERIALS)
        // =========================================================================
        const matDobotWhite  = new THREE.MeshStandardMaterial({ color: 0xf0f4f8, roughness: 0.25, metalness: 0.15 });
        const matDobotBlack  = new THREE.MeshStandardMaterial({ color: 0x1e2228, roughness: 0.45, metalness: 0.55 });
        const matDobotBlue   = new THREE.MeshStandardMaterial({ color: 0x1864ab, roughness: 0.30, metalness: 0.50 });
        const matSteelChrome = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.10, metalness: 0.95 });
        const matRailAlu     = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.35, metalness: 0.70 });
        const matBrass       = new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.30, metalness: 0.70 });
        const matSilicone    = new THREE.MeshStandardMaterial({ color: 0xfafafa, roughness: 0.4, metalness: 0.1, transparent: true, opacity: 0.92 });
        const matTube        = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.5, transparent: true, opacity: 0.80 });

        // =========================================================================
        // HỆ THỐNG RAY TRƯỢT 1.0M (SLIDING RAIL KIT 1000mm)
        // Trục chạy dọc Z (khớp với hệ ROS / URDF)
        // =========================================================================
        let isRailModeActive = true;
        let currentRailL = 0.0; // 0 – 1000 mm

        let railGroup = new THREE.Group();
        scene.add(railGroup);

        // Thân ray nhôm định hình (140 x 26 x 1120 mm)
        const railBase = new THREE.Mesh(new THREE.BoxGeometry(140, 26, 1120), matRailAlu);
        railBase.position.y = 13;
        railBase.castShadow = true;
        railBase.receiveShadow = true;
        railGroup.add(railBase);

        // Rãnh đai răng
        const beltSlot = new THREE.Mesh(new THREE.BoxGeometry(28, 6, 1090), matDobotBlack);
        beltSlot.position.y = 24;
        railGroup.add(beltSlot);

        // 2 ty trượt mạ crôm (D12 x 1100 mm)
        for (let rx of [45, -45]) {
            const shaft = new THREE.Mesh(new THREE.CylinderGeometry(6, 6, 1100, 24), matSteelChrome);
            shaft.rotation.x = Math.PI / 2;
            shaft.position.set(rx, 28, 0);
            shaft.castShadow = true;
            railGroup.add(shaft);
        }

        // Hộp motor stepper
        const railMotor = new THREE.Mesh(new THREE.BoxGeometry(110, 50, 70), matDobotBlack);
        railMotor.position.set(0, 30, -535);
        railMotor.castShadow = true;
        railGroup.add(railMotor);

        // Cảm biến công tắc
        const limitSw = new THREE.Mesh(new THREE.BoxGeometry(16, 20, 24), matBrass);
        limitSw.position.set(55, 32, -470);
        railGroup.add(limitSw);

        // Con trượt (Carriage)
        const railCarriage = new THREE.Group();
        railCarriage.position.set(0, 0, -500); // L=0 → Z=-500
        railGroup.add(railCarriage);

        const carriagePlate = new THREE.Mesh(new THREE.BoxGeometry(170, 16, 170), matDobotBlack);
        carriagePlate.position.y = 34;
        carriagePlate.castShadow = true;
        carriagePlate.receiveShadow = true;
        railCarriage.add(carriagePlate);

        const switchTrigger = new THREE.Mesh(new THREE.BoxGeometry(8, 12, 16), matBrass);
        switchTrigger.position.set(55, 32, -55);
        railCarriage.add(switchTrigger);

        // =========================================================================
        // CƠ CẤU ROBOT (URDF-BASED, ROS Coordinate Frame)
        // rosContainer: xoay -90° quanh X để chuyển Z-UP → Y-UP của Three.js
        // =========================================================================
        let robotGroup = new THREE.Group();
        railCarriage.add(robotGroup); // Mặc định gắn trên ray
        robotGroup.position.set(0, 42, 0);

        const rosContainer = new THREE.Group();
        rosContainer.rotation.x = -Math.PI / 2;
        robotGroup.add(rosContainer);

        // --- URDF Hierarchy ---
        let baseGroup = new THREE.Group();
        rosContainer.add(baseGroup);

        let j1Group = new THREE.Group();
        j1Group.position.set(0, 0, L1_BASE);
        baseGroup.add(j1Group);

        let j2Group = new THREE.Group();
        j2Group.position.set(0, 0, 0);
        j1Group.add(j2Group);

        let j3Group = new THREE.Group();
        j3Group.position.set(0, 0, L2_REAR);
        j2Group.add(j3Group);

        let j4WristGroup = new THREE.Group();
        j4WristGroup.position.set(L3_FORE, 0, 0);
        j3Group.add(j4WristGroup);

        let toolGroup = new THREE.Group();
        toolGroup.position.set(L4_WRIST, 0, 0);
        j4WristGroup.add(toolGroup);

        // =========================================================================
        // FALLBACK PARAMETRIC MODEL (hiện khi CAD chưa load xong)
        // =========================================================================
        const geomRobotGroup = new THREE.Group();
        rosContainer.add(geomRobotGroup);

        const baseMeshFb = new THREE.Mesh(new THREE.BoxGeometry(158, 158, 48), matDobotWhite);
        baseMeshFb.position.set(0, 0, 24);
        baseMeshFb.castShadow = true;
        baseGroup.add(baseMeshFb);

        const ringMeshFb = new THREE.Mesh(new THREE.CylinderGeometry(56, 56, 4, 32), matDobotBlue);
        ringMeshFb.rotation.x = Math.PI / 2;
        ringMeshFb.position.set(0, 0, 50);
        baseGroup.add(ringMeshFb);

        const towerFb = new THREE.Mesh(new THREE.CylinderGeometry(52, 64, 88, 32), matDobotWhite);
        towerFb.rotation.x = Math.PI / 2;
        towerFb.position.set(0, 0, -44);
        j1Group.add(towerFb);

        const rearArmFb = new THREE.Mesh(new THREE.BoxGeometry(26, 22, L2_REAR), matDobotBlack);
        rearArmFb.position.set(0, 0, L2_REAR / 2);
        j2Group.add(rearArmFb);

        const rodFb = new THREE.Mesh(new THREE.CylinderGeometry(3.5, 3.5, L2_REAR, 16), matSteelChrome);
        rodFb.rotation.x = Math.PI / 2;
        rodFb.position.set(16, 0, L2_REAR / 2);
        j2Group.add(rodFb);

        const foreArmFb = new THREE.Mesh(new THREE.BoxGeometry(L3_FORE, 22, 26), matDobotBlack);
        foreArmFb.position.set(L3_FORE / 2, 0, 0);
        j3Group.add(foreArmFb);

        const foreCoverFb = new THREE.Mesh(new THREE.BoxGeometry(L3_FORE * 0.7, 24, 8), matDobotWhite);
        foreCoverFb.position.set(L3_FORE * 0.45, 0, 15);
        j3Group.add(foreCoverFb);

        const wristFb = new THREE.Mesh(new THREE.BoxGeometry(L4_WRIST, 26, 22), matDobotBlack);
        wristFb.position.set(L4_WRIST / 2, 0, 0);
        j4WristGroup.add(wristFb);

        const servoFb = new THREE.Mesh(new THREE.BoxGeometry(26, 26, 26), matDobotBlack);
        servoFb.position.set(0, 0, -6);
        toolGroup.add(servoFb);

        const stemFb = new THREE.Mesh(new THREE.CylinderGeometry(5, 5, 36, 16), matSteelChrome);
        stemFb.rotation.x = Math.PI / 2;
        stemFb.position.set(0, 0, -30);
        toolGroup.add(stemFb);

        const cupFb = new THREE.Mesh(new THREE.CylinderGeometry(14, 2, 16, 24), matDobotBlack);
        cupFb.rotation.x = Math.PI / 2;
        cupFb.position.set(0, 0, -52);
        toolGroup.add(cupFb);

        const proceduralMeshes = [baseMeshFb, ringMeshFb, towerFb, rearArmFb, rodFb, foreArmFb, foreCoverFb, wristFb, servoFb, stemFb, cupFb];
        const proceduralMap = {
            base: [baseMeshFb, ringMeshFb],
            link1: [towerFb],
            link2: [rearArmFb, rodFb],
            link3: [foreArmFb, foreCoverFb],
            link4: [wristFb],
            suction: [servoFb, stemFb, cupFb]
        };

        // =========================================================================
        // TCP MARKER & PROJECTIONS
        // =========================================================================
        const tcpAxes = new THREE.AxesHelper(45);
        toolGroup.add(tcpAxes);

        const tcpMarker = new THREE.Mesh(new THREE.SphereGeometry(4.5, 16, 16), new THREE.MeshBasicMaterial({ color: 0xff3333 }));
        scene.add(tcpMarker);

        const dropLineGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0), new THREE.Vector3(0,0,0)]);
        const dropLineMat = new THREE.LineDashedMaterial({ color: 0x339af0, dashSize: 6, gapSize: 4, linewidth: 2 });
        const dropLine = new THREE.Line(dropLineGeo, dropLineMat);
        scene.add(dropLine);

        const groundReticle = new THREE.Mesh(
            new THREE.RingGeometry(10, 14, 32),
            new THREE.MeshBasicMaterial({ color: 0xff922b, side: THREE.DoubleSide })
        );
        groundReticle.rotation.x = -Math.PI / 2;
        groundReticle.position.y = 0.5;
        scene.add(groundReticle);

        const groundPoint = new THREE.Mesh(
            new THREE.CircleGeometry(5, 20),
            new THREE.MeshBasicMaterial({ color: 0xff922b })
        );
        groundPoint.rotation.x = -Math.PI / 2;
        groundPoint.position.y = 0.5;
        scene.add(groundPoint);

        const radiusLineGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0.5,0), new THREE.Vector3(0,0.5,0)]);
        const radiusLineMat = new THREE.LineBasicMaterial({ color: 0xffd43b, opacity: 0.6, transparent: true });
        const radiusLine = new THREE.Line(radiusLineGeo, radiusLineMat);
        scene.add(radiusLine);

        // =========================================================================
        // TARGET BEACON & GIZMO
        // =========================================================================
        const targetBeaconGroup = new THREE.Group();
        targetBeaconGroup.renderOrder = 999;
        scene.add(targetBeaconGroup);

        const beaconBoxGeo = new THREE.BoxGeometry(18, 18, 18);
        const beaconBoxMat = new THREE.MeshStandardMaterial({
            color: 0x51cf66, emissive: 0x2f9e44, emissiveIntensity: 0.65,
            roughness: 0.25, metalness: 0.5, transparent: true, opacity: 0.88
        });
        const beaconBox = new THREE.Mesh(beaconBoxGeo, beaconBoxMat);
        targetBeaconGroup.add(beaconBox);

        const beaconEdges = new THREE.LineSegments(
            new THREE.EdgesGeometry(beaconBoxGeo),
            new THREE.LineBasicMaterial({ color: 0xffffff, linewidth: 2 })
        );
        targetBeaconGroup.add(beaconEdges);

        const beaconCore = new THREE.Mesh(
            new THREE.SphereGeometry(4.5, 16, 16),
            new THREE.MeshBasicMaterial({ color: 0xffffff })
        );
        targetBeaconGroup.add(beaconCore);

        const beaconAxes = new THREE.AxesHelper(32);
        targetBeaconGroup.add(beaconAxes);

        // Vòng tâm ngắm ở mặt sàn
        const targetFloorReticle = new THREE.Mesh(
            new THREE.RingGeometry(8, 14, 32),
            new THREE.MeshBasicMaterial({ color: 0x51cf66, side: THREE.DoubleSide, transparent: true, opacity: 0.75 })
        );
        targetFloorReticle.rotation.x = -Math.PI / 2;
        targetFloorReticle.position.y = 0.6;
        scene.add(targetFloorReticle);

        // Đường gióng rơi thẳng đứng từ cục điểm đích xuống sàn
        const targetDropLineGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, 0)]);
        const targetDropLineMat = new THREE.LineDashedMaterial({ color: 0x51cf66, dashSize: 6, gapSize: 4, opacity: 0.85, transparent: true });
        const targetDropLine = new THREE.Line(targetDropLineGeo, targetDropLineMat);
        scene.add(targetDropLine);

        let transformControl;
        let isDraggingGizmo = false;
        let isTargetGizmoActive = true;

        // ========================================================
        // VÙNG LÀM VIỆC AN TOÀN TRÊN BÀN (SAFE WORKSPACE ZONE)
        // ========================================================
        const workspaceZoneGroup = new THREE.Group();
        if (typeof isRailModeActive !== 'undefined' && isRailModeActive) {
            workspaceZoneGroup.position.z = -500 + currentRailL;
        }
        scene.add(workspaceZoneGroup);

        const zoneMat = new THREE.MeshBasicMaterial({
            color: 0x1971c2,
            transparent: true,
            opacity: 0.12,
            side: THREE.DoubleSide,
            depthWrite: false
        });
        const zoneMesh = new THREE.Mesh(new THREE.RingGeometry(140, 330, 64), zoneMat);
        zoneMesh.rotation.x = -Math.PI / 2;
        zoneMesh.position.y = 0.2;
        workspaceZoneGroup.add(zoneMesh);

        // Vòng biên trong R=140mm (Cảnh báo gần thân robot)
        const innerLimitRing = new THREE.Mesh(
            new THREE.RingGeometry(138.5, 140.5, 64),
            new THREE.MeshBasicMaterial({ color: 0xff6b6b, side: THREE.DoubleSide, transparent: true, opacity: 0.6 })
        );
        innerLimitRing.rotation.x = -Math.PI / 2;
        innerLimitRing.position.y = 0.3;
        workspaceZoneGroup.add(innerLimitRing);

        // Vòng biên ngoài R=330mm (Tầm với tối đa)
        const outerLimitRing = new THREE.Mesh(
            new THREE.RingGeometry(329, 331, 64),
            new THREE.MeshBasicMaterial({ color: 0x339af0, side: THREE.DoubleSide, transparent: true, opacity: 0.6 })
        );
        outerLimitRing.rotation.x = -Math.PI / 2;
        outerLimitRing.position.y = 0.3;
        workspaceZoneGroup.add(outerLimitRing);

        // ========================================================
        // TÂM NGẮM CHUỘT HOVER KHI CHỌN ĐIỂM (HOVER RETICLE)
        // ========================================================
        const hoverReticle = new THREE.Group();
        scene.add(hoverReticle);

        const hoverRing = new THREE.Mesh(
            new THREE.RingGeometry(7, 10, 32),
            new THREE.MeshBasicMaterial({ color: 0x339af0, side: THREE.DoubleSide, transparent: true, opacity: 0.85 })
        );
        hoverRing.rotation.x = -Math.PI / 2;
        hoverReticle.add(hoverRing);

        const hoverDot = new THREE.Mesh(
            new THREE.CircleGeometry(2.5, 16),
            new THREE.MeshBasicMaterial({ color: 0x339af0, side: THREE.DoubleSide, transparent: true, opacity: 0.9 })
        );
        hoverDot.rotation.x = -Math.PI / 2;
        hoverReticle.add(hoverDot);
        hoverReticle.visible = false;

        // ========================================================
        // GIẢI THUẬT INVERSE KINEMATICS (IK) MỀM DẺO
        // ========================================================
        function solveIK(targetX, targetY, targetZ_TCP) {
            const targetZ_Flange = targetZ_TCP + toolOffset;
            const j1Rad = Math.atan2(targetY, targetX);

            const rTotal = Math.sqrt(targetX * targetX + targetY * targetY);
            const r = rTotal - L4_WRIST;
            const z = targetZ_Flange;

            const D = Math.sqrt(r * r + z * z);
            const maxReach = (L2_REAR + L3_FORE) * 0.995;
            const minReach = Math.abs(L2_REAR - L3_FORE) * 1.005;

            // Clamping nhẹ nhàng nếu hơi quá tầm
            const clampedD = Math.max(minReach, Math.min(maxReach, D));

            let cosAlpha = (L2_REAR * L2_REAR + clampedD * clampedD - L3_FORE * L3_FORE) / (2 * L2_REAR * clampedD);
            cosAlpha = Math.max(-1.0, Math.min(1.0, cosAlpha));
            const alpha = Math.acos(cosAlpha);
            const beta = Math.atan2(z, r);

            const phi2 = beta + alpha;
            const j2Rad = Math.PI / 2 - phi2;

            const x3 = r - L2_REAR * Math.sin(j2Rad);
            const y3 = z - L2_REAR * Math.cos(j2Rad);
            const j3Rad = Math.atan2(-y3, x3);

            return {
                j1: THREE.MathUtils.radToDeg(j1Rad),
                j2: THREE.MathUtils.radToDeg(j2Rad),
                j3: THREE.MathUtils.radToDeg(j3Rad)
            };
        }

        // =========================================================================
        // NẠP MÔ HÌNH CAD CHÍNH HÃNG (COLLADA .DAE) – URDF OFFSETS
        // =========================================================================
        const cadNodes = { base: null, link1: null, link2: null, link3: null, link4: null, suction: null, gripper: null };
        let cadLoadedCount = 0;
        const totalCadRequired = 6;

        function getMeshUrl(filename) {
            if (window.location.protocol === 'file:') {
                return 'dobot_description/meshes/dae/' + filename;
            }
            return '/dobot_description/meshes/dae/' + filename;
        }

        function polishCadScene(sceneObj) {
            sceneObj.scale.set(1000, 1000, 1000);
            sceneObj.rotation.set(0, 0, 0);
            sceneObj.traverse(function(child) {
                if (child.isMesh) {
                    child.castShadow = true;
                    child.receiveShadow = true;
                    if (child.material) {
                        child.material.side = THREE.DoubleSide;
                    }
                }
            });
            return sceneObj;
        }

        function loadAllCadMeshes() {
            if (typeof THREE.ColladaLoader === 'undefined') {
                console.warn('[CAD] ColladaLoader chưa sẵn sàng.');
                return;
            }
            const loader = new THREE.ColladaLoader();
            // Offsets lấy từ URDF dobot_magician_standalone.urdf (đơn vị mm)
            const meshesToLoad = [
                { id: 'base',    file: 'magicianBase.dae',         group: baseGroup,     pos: [0, 0, 131.0],           rot: [0, 0, 0] },
                { id: 'link1',   file: 'magicianLink1.dae',        group: j1Group,       pos: [0, 0, 0],               rot: [0, 0, 0] },
                { id: 'link2',   file: 'magicianLink2.dae',        group: j2Group,       pos: [0, 0, 0],               rot: [0, -0.349066, 0] },
                { id: 'link3',   file: 'magicianLink3.dae',        group: j3Group,       pos: [16.452, 0, -133.994],   rot: [0, -0.471239, 0] },
                { id: 'link4',   file: 'magicianLink4.dae',        group: j4WristGroup, pos: [-177.151, 0, -58.595],  rot: [0, 0, 0] },
                { id: 'suction', file: 'suction_cup.dae',          group: toolGroup,     pos: [-0.081, 0, -11.843],    rot: [0, 0, 0] },
                { id: 'gripper', file: 'magicianGripper.dae',      group: null,          pos: [0, 0, 0],               rot: [0, 0, 0] }
            ];

            meshesToLoad.forEach(item => {
                loader.load(
                    getMeshUrl(item.file),
                    function(collada) {
                        const cadObj = polishCadScene(collada.scene);
                        cadObj.position.set(item.pos[0], item.pos[1], item.pos[2]);
                        cadObj.rotation.set(item.rot[0], item.rot[1], item.rot[2]);
                        cadNodes[item.id] = cadObj;
                        if (item.group) item.group.add(cadObj);
                        // Ẩn fallback tương ứng
                        if (proceduralMap[item.id]) {
                            proceduralMap[item.id].forEach(m => { m.visible = false; });
                        }
                        if (item.id !== 'gripper') {
                            cadLoadedCount++;
                            console.log('[CAD] ✅ Loaded:', item.file, '(' + cadLoadedCount + '/' + totalCadRequired + ')');
                        }
                    },
                    undefined,
                    function(err) { console.warn('[CAD] Fallback cho:', item.file, err); }
                );
            });
        }

        setTimeout(loadAllCadMeshes, 200);

        // =========================================================================
        // CẬP NHẬT MÔ HÌNH VÀ TỌA ĐỘ
        // =========================================================================
        function renderRobot(j1Deg, j2Deg, j3Deg, j4Deg, rawX=null, rawY=null, rawZ=null) {
            // --- Cập nhật vị trí Ray trượt & Vùng an toàn ---
            if (isRailModeActive) {
                railGroup.visible = true;
                const railZ = (-500 + currentRailL);
                railCarriage.position.z = railZ;
                if (typeof workspaceZoneGroup !== 'undefined' && workspaceZoneGroup) {
                    workspaceZoneGroup.position.z = railZ;
                }
                if (robotGroup.parent !== railCarriage) {
                    railCarriage.add(robotGroup);
                    robotGroup.position.set(0, 42, 0);
                }
            } else {
                railGroup.visible = false;
                if (typeof workspaceZoneGroup !== 'undefined' && workspaceZoneGroup) {
                    workspaceZoneGroup.position.z = 0;
                }
                if (robotGroup.parent !== scene) {
                    scene.add(robotGroup);
                    robotGroup.position.set(0, 0, 0);
                }
            }

            document.getElementById('j1-val').innerText = j1Deg.toFixed(1) + '°';
            document.getElementById('j2-val').innerText = j2Deg.toFixed(1) + '°';
            document.getElementById('j3-val').innerText = j3Deg.toFixed(1) + '°';
            document.getElementById('j4-val').innerText = j4Deg.toFixed(1) + '°';

            const j1Rad = THREE.MathUtils.degToRad(j1Deg);
            const j2Rad = THREE.MathUtils.degToRad(j2Deg);
            const j3Rad = THREE.MathUtils.degToRad(j3Deg);
            const j4Rad = THREE.MathUtils.degToRad(j4Deg);

            // Trục khớp theo URDF mới (khớp với view_urdf.html)
            j1Group.rotation.z      = j1Rad;
            j2Group.rotation.y      = j2Rad;
            j3Group.rotation.y      = j3Rad - j2Rad;
            j4WristGroup.rotation.y = -j3Rad;
            toolGroup.rotation.z    = j4Rad;

            // Hiển thị công cụ (CAD nodes)
            if (cadNodes.suction) cadNodes.suction.visible = (currentToolType === 'suction');
            if (cadNodes.gripper) cadNodes.gripper.visible = (currentToolType === 'gripper');

            let x, y, zRobot, zTcp, rDeg;
            if (rawX !== null && rawY !== null && rawZ !== null) {
                x = rawX;
                y = rawY;
                zRobot = rawZ;
                zTcp = zRobot - toolOffset;
                rDeg = j1Deg + j4Deg;
            } else {
                const r = L2_REAR * Math.sin(j2Rad) + L3_FORE * Math.cos(j3Rad) + L4_WRIST;
                x = r * Math.cos(j1Rad);
                y = r * Math.sin(j1Rad);
                zRobot = L1_BASE + L2_REAR * Math.cos(j2Rad) - L3_FORE * Math.sin(j3Rad);
                zTcp = zRobot - toolOffset;
                rDeg = j1Deg + j4Deg;
            }

            lastRawJoints = { j1: j1Deg, j2: j2Deg, j3: j3Deg, j4: j4Deg };
            currentX = x; currentY = y; currentZ = zTcp; currentR = rDeg;
            lastKnownRobotPose = {
                x: x, y: y, z: zRobot, r: rDeg, zTcp: zTcp,
                j1: j1Deg, j2: j2Deg, j3: j3Deg, j4: j4Deg
            };

            document.getElementById('tcp-x').innerText = x.toFixed(2) + ' mm';
            document.getElementById('tcp-y').innerText = y.toFixed(2) + ' mm';
            document.getElementById('tcp-z').innerText = zTcp.toFixed(2) + ' mm';
            document.getElementById('tcp-r').innerText = rDeg.toFixed(2) + '°';

            const radiusHoriz = Math.sqrt(x * x + y * y);
            const dist3D = Math.sqrt(x * x + y * y + zTcp * zTcp);
            const railYOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? 42 : 0;
            const floorHeight = railYOffset + L1_BASE + zTcp;

            document.getElementById('tcp-radius').innerText = radiusHoriz.toFixed(2) + ' mm';
            document.getElementById('tcp-dist3d').innerText = dist3D.toFixed(2) + ' mm';
            document.getElementById('tcp-floor').innerText = floorHeight.toFixed(2) + ' mm';

            if (typeof updateSafetyLiveStatus === 'function') {
                updateSafetyLiveStatus();
            }

            if (currentMode === 'live' && !isInteractingWithSliders) {
                document.getElementById('cart-x').value = x;
                document.getElementById('cart-y').value = y;
                document.getElementById('cart-z').value = zTcp;
                document.getElementById('cart-r').value = rDeg;
                document.getElementById('cart-x-val').innerText = x.toFixed(0) + ' mm';
                document.getElementById('cart-y-val').innerText = y.toFixed(0) + ' mm';
                document.getElementById('cart-z-val').innerText = zTcp.toFixed(0) + ' mm';
                document.getElementById('cart-r-val').innerText = rDeg.toFixed(1) + '°';

                document.getElementById('j1').value = j1Deg;
                document.getElementById('j2').value = j2Deg;
                document.getElementById('j3').value = j3Deg;
                document.getElementById('j4').value = j4Deg;
                document.getElementById('j1-val').innerText = j1Deg.toFixed(1) + '°';
                document.getElementById('j2-val').innerText = j2Deg.toFixed(1) + '°';
                document.getElementById('j3-val').innerText = j3Deg.toFixed(1) + '°';
                document.getElementById('j4-val').innerText = j4Deg.toFixed(1) + '°';
            }

            const railOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? (-500 + currentRailL) : 0;
            const tcpWorldPos = new THREE.Vector3(x, floorHeight, railOffset - y);
            tcpMarker.position.copy(tcpWorldPos);

            if (showProjections) {
                const pts = [tcpWorldPos, new THREE.Vector3(x, 0.5, railOffset - y)];
                dropLine.geometry.setFromPoints(pts);
                dropLine.computeLineDistances();
                dropLine.visible = true;

                groundReticle.position.set(x, 0.5, railOffset - y);
                groundPoint.position.set(x, 0.5, railOffset - y);
                groundReticle.visible = true;
                groundPoint.visible = true;

                radiusLine.geometry.setFromPoints([new THREE.Vector3(0, 0.5, railOffset), new THREE.Vector3(x, 0.5, railOffset - y)]);
                radiusLine.visible = true;
            } else {
                dropLine.visible = false;
                groundReticle.visible = false;
                groundPoint.visible = false;
                radiusLine.visible = false;
            }

            updateHudLabel(tcpWorldPos, x, y, zTcp);
        }

        function updateHudLabel(worldPos, x, y, z) {
            const label = document.getElementById('hud-label');
            const pos = worldPos.clone();
            pos.project(camera);
            
            if (pos.z < 1) {
                const sx = (pos.x * 0.5 + 0.5) * window.innerWidth;
                const sy = (-(pos.y * 0.5) + 0.5) * window.innerHeight;
                label.style.left = `${sx}px`;
                label.style.top = `${sy}px`;
                label.style.display = 'block';
                label.innerText = `TCP: (${x.toFixed(1)}, ${y.toFixed(1)}, ${z.toFixed(1)})`;
            } else {
                label.style.display = 'none';
            }
        }

        // --- CÁC HÀM XỬ LÝ SỰ KIỆN GIAO DIỆN ---
        function onCartesianInput() {
            const x = parseFloat(document.getElementById('cart-x').value);
            const y = parseFloat(document.getElementById('cart-y').value);
            const z = parseFloat(document.getElementById('cart-z').value);
            const r = parseFloat(document.getElementById('cart-r').value);

            document.getElementById('cart-x-val').innerText = x.toFixed(0) + ' mm';
            document.getElementById('cart-y-val').innerText = y.toFixed(0) + ' mm';
            document.getElementById('cart-z-val').innerText = z.toFixed(0) + ' mm';
            document.getElementById('cart-r-val').innerText = r.toFixed(1) + '°';

            if (currentMode === 'manual') {
                const ik = solveIK(x, y, z);
                if (ik) {
                    document.getElementById('j1').value = ik.j1;
                    document.getElementById('j2').value = ik.j2;
                    document.getElementById('j3').value = ik.j3;
                    document.getElementById('j4').value = r - ik.j1;
                    document.getElementById('j1-val').innerText = ik.j1.toFixed(1) + '°';
                    document.getElementById('j2-val').innerText = ik.j2.toFixed(1) + '°';
                    document.getElementById('j3-val').innerText = ik.j3.toFixed(1) + '°';
                    document.getElementById('j4-val').innerText = (r - ik.j1).toFixed(1) + '°';
                    renderRobot(ik.j1, ik.j2, ik.j3, r - ik.j1);
                }
            }
        }

        function onJointInput() {
            const j1 = parseFloat(document.getElementById('j1').value);
            const j2 = parseFloat(document.getElementById('j2').value);
            const j3 = parseFloat(document.getElementById('j3').value);
            const j4 = parseFloat(document.getElementById('j4').value);

            document.getElementById('j1-val').innerText = j1.toFixed(1) + '°';
            document.getElementById('j2-val').innerText = j2.toFixed(1) + '°';
            document.getElementById('j3-val').innerText = j3.toFixed(1) + '°';
            document.getElementById('j4-val').innerText = j4.toFixed(1) + '°';

            if (currentMode === 'manual') {
                renderRobot(j1, j2, j3, j4);
            }
        }

        // Bắt sự kiện kéo chuột trên thanh trượt
        ['cart-x', 'cart-y', 'cart-z', 'cart-r', 'j1', 'j2', 'j3', 'j4'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('mousedown', () => { isInteractingWithSliders = true; });
            el.addEventListener('touchstart', () => { isInteractingWithSliders = true; });
            if (id.startsWith('cart-')) {
                el.addEventListener('input', onCartesianInput);
            } else {
                el.addEventListener('input', onJointInput);
            }
        });

        window.addEventListener('mouseup', () => {
            if (isInteractingWithSliders) {
                isInteractingWithSliders = false;
                const auto = document.getElementById('chk-auto-send');
                if (auto && auto.checked) {
                    sendMoveToRobot();
                }
            }
        });

        window.addEventListener('touchend', () => {
            if (isInteractingWithSliders) {
                isInteractingWithSliders = false;
                const auto = document.getElementById('chk-auto-send');
                if (auto && auto.checked) {
                    sendMoveToRobot();
                }
            }
        });

        // --- BÀN PHÍM JOG NHANH VÀ NUDGE ---
        function setJogStep(step) {
            jogStep = step;
            document.querySelectorAll('.btn-step').forEach(btn => {
                btn.classList.toggle('active', parseFloat(btn.dataset.step) === step);
            });
            showToast(`Đã chọn bước Jog: ${step} mm`);
        }

        function doJog(axis, dir) {
            const stepVal = dir * jogStep;
            console.log(`[JOG] ${axis.toUpperCase()} ${stepVal > 0 ? '+' : ''}${stepVal} mm`);
            sendAction('jog', { axis: axis, step: stepVal });
            showToast(`⚡ Đang Jog ${axis.toUpperCase()}: ${stepVal > 0 ? '+' : ''}${stepVal} mm`);
        }

        function nudgeSlider(id, dir) {
            const el = document.getElementById(id);
            if (!el) return;
            const step = parseFloat(el.step || 1);
            let val = parseFloat(el.value) + dir * step;
            val = Math.max(parseFloat(el.min), Math.min(parseFloat(el.max), val));
            el.value = val;
            if (id.startsWith('cart-')) {
                onCartesianInput();
            } else {
                onJointInput();
            }
            const auto = document.getElementById('chk-auto-send');
            if (auto && auto.checked) {
                sendMoveToRobot();
            }
        }

        function syncSlidersWithCurrentPose() {
            document.getElementById('cart-x').value = currentX;
            document.getElementById('cart-y').value = currentY;
            document.getElementById('cart-z').value = currentZ;
            document.getElementById('cart-r').value = currentR;
            document.getElementById('cart-x-val').innerText = currentX.toFixed(0) + ' mm';
            document.getElementById('cart-y-val').innerText = currentY.toFixed(0) + ' mm';
            document.getElementById('cart-z-val').innerText = currentZ.toFixed(0) + ' mm';
            document.getElementById('cart-r-val').innerText = currentR.toFixed(1) + '°';

            if (lastRawJoints) {
                document.getElementById('j1').value = lastRawJoints.j1;
                document.getElementById('j2').value = lastRawJoints.j2;
                document.getElementById('j3').value = lastRawJoints.j3;
                document.getElementById('j4').value = lastRawJoints.j4;
                document.getElementById('j1-val').innerText = lastRawJoints.j1.toFixed(1) + '°';
                document.getElementById('j2-val').innerText = lastRawJoints.j2.toFixed(1) + '°';
                document.getElementById('j3-val').innerText = lastRawJoints.j3.toFixed(1) + '°';
                document.getElementById('j4-val').innerText = lastRawJoints.j4.toFixed(1) + '°';
            }
            showToast('🔄 Đã đồng bộ thanh trượt từ vị trí robot thật');
        }

        function switchTab(tabId) {
            const tabs = ['target', 'jog', 'rail', 'safety', 'teach', 'blockly', 'monitor'];
            const panel = document.getElementById('panel');

            tabs.forEach(t => {
                const navBtn = document.getElementById(`tab-nav-${t}`);
                const pane = document.getElementById(`tab-pane-${t}`);
                if (navBtn) navBtn.classList.toggle('active', t === tabId);
                if (pane) pane.style.display = (t === tabId) ? 'block' : 'none';
            });

            if (tabId === 'safety') {
                fetchSafetyLimits(false);
                if (typeof updateSafetyLiveStatus === 'function') updateSafetyLiveStatus();
            } else if (tabId === 'teach') {
                renderTeachList();
            } else if (tabId === 'blockly') {
                if (panel && !panel.classList.contains('panel-expanded')) {
                    panel.classList.add('panel-expanded');
                    const btn = document.getElementById('btn-toggle-expand');
                    if (btn) btn.innerText = "◀️ Thu Gọn";
                }
                initBlocklyWorkspaceIfNeeded();
                setTimeout(() => {
                    if (blocklyWorkspace && typeof Blockly !== 'undefined') {
                        Blockly.svgResize(blocklyWorkspace);
                    }
                }, 260);
            } else {
                if (panel && panel.classList.contains('panel-expanded') && !isPanelPinnedExpanded) {
                    panel.classList.remove('panel-expanded');
                    const btn = document.getElementById('btn-toggle-expand');
                    if (btn) btn.innerText = "↔️ Mở Rộng";
                }
            }
        }

        function switchControlSubTab(sub) {
            const isJog = (sub === 'jog');
            const btnJog = document.getElementById('subtab-jog');
            const btnSlider = document.getElementById('subtab-slider');
            const jogView = document.getElementById('jog-view');
            const sliderView = document.getElementById('slider-view');
            if (btnJog) btnJog.classList.toggle('active', isJog);
            if (btnSlider) btnSlider.classList.toggle('active', !isJog);
            if (jogView) jogView.style.display = isJog ? 'block' : 'none';
            if (sliderView) sliderView.style.display = !isJog ? 'block' : 'none';
        }

        function setCoordSystem(sys) {
            coordSystem = sys;
            document.getElementById('btn-coord-cartesian').classList.toggle('active', sys === 'cartesian');
            document.getElementById('btn-coord-joint').classList.toggle('active', sys === 'joint');
            document.getElementById('cartesian-controls').style.display = (sys === 'cartesian') ? 'block' : 'none';
            document.getElementById('joint-controls').style.display = (sys === 'joint') ? 'block' : 'none';
        }

        function setMode(mode) {
            currentMode = mode;
            document.getElementById('btn-mode-live').classList.toggle('active', mode === 'live');
            document.getElementById('btn-mode-manual').classList.toggle('active', mode === 'manual');
            
            const badge = document.getElementById('status-badge');
            const statusText = document.getElementById('status-text');

            if (mode === 'manual') {
                syncSlidersWithCurrentPose();
                if (badge && statusText) {
                    badge.className = "status-badge simulation";
                    statusText.innerText = "🎮 Đang chạy mô phỏng 3D độc lập";
                }
                showToast('🎮 Chế độ Mô phỏng: Kéo thanh trượt hoặc chạy kịch bản ảo độc lập');
            } else {
                if (isRobotConnected || isRobotHardwareConnected) {
                    if (badge && statusText) {
                        badge.className = "status-badge live";
                        statusText.innerText = "● Đang đồng bộ thật";
                    }
                } else {
                    if (badge && statusText) {
                        badge.className = "status-badge offline";
                        statusText.innerText = "○ Chưa cắm USB hoặc Robot đang tắt";
                    }
                }
                showToast('⚡ Chế độ Live: Đồng bộ thời gian thực với Robot Dobot');
            }
        }

        function toggleProjectionLines() {
            showProjections = !showProjections;
            renderRobot(parseFloat(document.getElementById('j1').value), parseFloat(document.getElementById('j2').value), parseFloat(document.getElementById('j3').value), parseFloat(document.getElementById('j4').value));
        }

        document.getElementById('tool-select').addEventListener('change', (e) => {
            currentToolType = e.target.value;
            if (currentToolType === 'suction') toolOffset = 59.5;
            else if (currentToolType === 'gripper') toolOffset = 68.0;
            else toolOffset = 0.0;
            if (currentMode === 'manual') {
                if (coordSystem === 'cartesian') onCartesianInput();
                else onJointInput();
            }
        });

        function switchTheme(theme) {
            document.getElementById('btn-sim-theme').classList.toggle('active', theme === 'sim');
            document.getElementById('btn-dark-theme').classList.toggle('active', theme === 'dark');

            if (theme === 'sim') {
                scene.background = new THREE.Color(0xb4d7ec);
                scene.fog = new THREE.Fog(0xb4d7ec, 600, 2400);
                floorMat.color.setHex(0x3d7a46);
                gridHelper.material.color.setHex(0x8ce99a);
            } else {
                scene.background = new THREE.Color(0x13161c);
                scene.fog = new THREE.FogExp2(0x13161c, 0.0014);
                floorMat.color.setHex(0x1a1e26);
                gridHelper.material.color.setHex(0x339af0);
            }
        }

        // ========================================================
        // ĐIỀU KHIỂN CỤC ĐIỂM ĐÍCH 3D (TARGET BEACON & GIZMO)
        // ========================================================
        let lastGizmoDragEndTime = 0;

        function initTransformGizmo() {
            if (typeof THREE.TransformControls !== 'undefined') {
                transformControl = new THREE.TransformControls(camera, renderer.domElement);
                transformControl.size = 0.85;
                transformControl.setMode('translate');
                transformControl.attach(targetBeaconGroup);
                scene.add(transformControl);

                transformControl.addEventListener('dragging-changed', function (event) {
                    controls.enabled = !event.value; // Tạm khóa OrbitControls khi đang kéo mũi tên
                    isDraggingGizmo = event.value;
                    if (!event.value) {
                        lastGizmoDragEndTime = Date.now();
                        onTargetGizmoDragEnd();
                    }
                });

                transformControl.addEventListener('change', function () {
                    if (transformControl.object && isDraggingGizmo) {
                        onTargetGizmoChange();
                    }
                });
            } else {
                console.warn("TransformControls is not available.");
            }
        }

        function toggleTargetGizmo() {
            isTargetGizmoActive = !isTargetGizmoActive;
            targetBeaconGroup.visible = isTargetGizmoActive;
            targetFloorReticle.visible = isTargetGizmoActive;
            targetDropLine.visible = isTargetGizmoActive;
            if (transformControl) {
                transformControl.enabled = isTargetGizmoActive;
                transformControl.visible = isTargetGizmoActive;
            }
            const hud = document.getElementById('beacon-hud');
            if (hud && !isTargetGizmoActive) hud.style.display = 'none';

            const btn = document.getElementById('btn-toggle-gizmo');
            if (btn) {
                btn.className = `btn-gizmo ${isTargetGizmoActive ? 'active' : 'inactive'}`;
                btn.innerHTML = isTargetGizmoActive ? 
                    '🎯 CỤC ĐIỂM ĐÍCH 3D: ĐANG BẬT' : 
                    '🎯 CỤC ĐIỂM ĐÍCH 3D: ĐANG TẮT (Click để bật)';
            }
            showToast(isTargetGizmoActive ? '🎯 Đã hiện cục điểm đích! Kéo mũi tên xanh lá để chỉnh Z, đỏ/xanh dương để chỉnh XY' : 'Đã ẩn cục điểm đích 3D');
        }

        let targetRailL = 0.0;
        let isRailHardwareMoving = false;
        let railAnimationFrameId = null;
        let isRailAnimating = false;

        // ========================================================
        // GIẢI THUẬT ĐỘNG HỌC RAY TRƯỢT THÔNG MINH (RAIL KINEMATICS SOLVER)
        // Dựa trên kiến trúc hệ thống Dobot-Fablab:
        // Dobot có bán kính với cơ khí an toàn [140, 330] mm.
        // Khi gắn trên ray trượt 1000mm, các điểm ngoài tầm với (dọc ray hoặc gần ray 70..150mm)
        // được giải tự động bằng cách dịch bàn trượt dọc theo ray và vươn tới điểm đích.
        // ========================================================
        function solveRailKinematics(xWorld, zWorld, preferredL = (typeof currentRailL !== 'undefined' ? currentRailL : 500.0)) {
            if (xWorld < 70.0 || xWorld > 330.0) return null;

            const curL = Math.max(0.0, Math.min(1000.0, parseFloat(preferredL !== undefined && preferredL !== null ? preferredL : currentRailL) || 0.0));
            const zcCur = curL - 500.0;
            const yArmCur = -(zWorld - zcCur);
            const rCur = Math.sqrt(xWorld * xWorld + yArmCur * yArmCur);
            const j1CurDeg = THREE.MathUtils.radToDeg(Math.atan2(yArmCur, xWorld));

            // 2. Vị trí ray tối ưu (thẳng mặt mục tiêu zWorld dọc trục ray)
            const zCarriageDirect = Math.max(-500.0, Math.min(500.0, zWorld));
            const optimalLDirect = zCarriageDirect + 500.0;
            const yArmDirect = -(zWorld - zCarriageDirect);
            const rDirect = Math.sqrt(xWorld * xWorld + yArmDirect * yArmDirect);
            const j1DirectDeg = THREE.MathUtils.radToDeg(Math.atan2(yArmDirect, xWorld));

            // 1. KIỂM TRA ƯU TIÊN GẮP TẠI CHỖ:
            // Chỉ gắp tại chỗ khi xe trượt đang ở ngay sát vị trí đón phôi tối ưu (lệch <= 40mm)
            // VÀ cánh tay ở tư thế tự nhiên thoải mái (bán kính 140..320mm, góc J1 <= 25 độ).
            // Nếu xe trượt đang ở xa (như ở khay thả L=150mm hay L=500mm), bắt buộc phải chạy ray về đón phôi!
            const diffL = Math.abs(curL - optimalLDirect);
            if (diffL <= 40.0 && rCur >= 140.0 && rCur <= 320.0 && Math.abs(j1CurDeg) <= 25.0) {
                return {
                    l: curL,
                    optimal_l: curL,
                    zCarriage: zcCur,
                    xArm: xWorld,
                    yArm: yArmCur,
                    r: rCur,
                    j1Deg: j1CurDeg,
                    inCurrentReach: true
                };
            }

            // 3. Nếu đang ở xa hoặc góc vặn lớn: Giải vị trí ray tối ưu để đón phôi
            if (xWorld >= 150.0 && rDirect >= 140.0 && rDirect <= 330.0 && Math.abs(j1DirectDeg) <= 85.0) {
                return {
                    l: optimalLDirect,
                    optimal_l: optimalLDirect,
                    zCarriage: zCarriageDirect,
                    xArm: xWorld,
                    yArm: yArmDirect,
                    r: rDirect,
                    j1Deg: j1DirectDeg,
                    inCurrentReach: false
                };
            }

            // 3. Vươn chéo rTarget = 180mm khi xWorld < 150mm
            const rTarget = 180.0;
            const dy = Math.sqrt(Math.max(0.0, rTarget * rTarget - xWorld * xWorld));
            const candidates = [
                zWorld - dy,
                zWorld + dy
            ];

            let best = null;
            let minDiff = Infinity;

            for (const zc of candidates) {
                const zcClamped = Math.max(-500.0, Math.min(500.0, zc));
                const lCandidate = zcClamped + 500.0;
                const yArm = -(zWorld - zcClamped);
                const r = Math.sqrt(xWorld * xWorld + yArm * yArm);
                const j1Deg = THREE.MathUtils.radToDeg(Math.atan2(yArm, xWorld));

                if (r >= 140.0 && r <= 330.0 && Math.abs(j1Deg) <= 85.0) {
                    const diff = Math.abs(lCandidate - curL);
                    if (diff < minDiff) {
                        minDiff = diff;
                        best = {
                            l: lCandidate,
                            optimal_l: lCandidate,
                            zCarriage: zcClamped,
                            xArm: xWorld,
                            yArm: yArm,
                            r: r,
                            j1Deg: j1Deg,
                            inCurrentReach: false
                        };
                    }
                }
            }

            // 4. Quét dự phòng dọc toàn bộ hành trình ray (0..1000mm)
            if (!best) {
                for (let l = 0; l <= 1000; l += 10) {
                    const zc = l - 500.0;
                    const yArm = -(zWorld - zc);
                    const r = Math.sqrt(xWorld * xWorld + yArm * yArm);
                    const j1Deg = THREE.MathUtils.radToDeg(Math.atan2(yArm, xWorld));
                    if (r >= 140.0 && r <= 330.0 && Math.abs(j1Deg) <= 85.0) {
                        const diff = Math.abs(l - curL);
                        if (diff < minDiff) {
                            minDiff = diff;
                            best = {
                                l: l,
                                optimal_l: l,
                                zCarriage: zc,
                                xArm: xWorld,
                                yArm: yArm,
                                r: r,
                                j1Deg: j1Deg,
                                inCurrentReach: false
                            };
                        }
                    }
                }
            }

            return best;
        }

        function isPointInRailWorkspace(xWorld, zWorld, zTcp) {
            if (zTcp < -180.0 || zTcp > 165.0) return false;
            return solveRailKinematics(xWorld, zWorld) !== null;
        }

        // Hoạt hình trượt 3D mượt mà cho Ray trượt trong mô phỏng
        async function animateRailMove(targetL, speedMmS=40.0) {
            targetL = Math.max(0.0, Math.min(1000.0, parseFloat(targetL) || 0.0));
            const startL = currentRailL;
            const dist = Math.abs(targetL - startL);
            if (dist < 0.2) {
                currentRailL = targetL;
                targetRailL = targetL;
                const railZ = -500 + currentRailL;
                if (railCarriage) railCarriage.position.z = railZ;
                if (typeof workspaceZoneGroup !== 'undefined' && workspaceZoneGroup) {
                    workspaceZoneGroup.position.z = railZ;
                }
                const disp = document.getElementById('rail-pos-display');
                if (disp) disp.innerText = targetL.toFixed(1) + ' mm';
                const pbar = document.getElementById('rail-progress-bar');
                if (pbar) pbar.style.width = Math.min(100, Math.max(0, (targetL / 1000.0) * 100)) + '%';
                return;
            }

            if (railAnimationFrameId) {
                cancelAnimationFrame(railAnimationFrameId);
                railAnimationFrameId = null;
            }

            const durationMs = Math.max(200, Math.min(3000, (dist / speedMmS) * 1000));
            const startTime = performance.now();
            isRailAnimating = true;

            return new Promise((resolve) => {
                function step(now) {
                    if (!isRailAnimating) {
                        railAnimationFrameId = null;
                        resolve();
                        return;
                    }
                    const elapsed = now - startTime;
                    const progress = Math.min(1.0, elapsed / durationMs);
                    const eased = progress < 0.5 ? 2 * progress * progress : -1 + (4 - 2 * progress) * progress;
                    const newL = startL + (targetL - startL) * eased;
                    currentRailL = newL;
                    targetRailL = targetL;

                    const railZ = -500 + newL;
                    if (railCarriage) railCarriage.position.z = railZ;
                    if (typeof workspaceZoneGroup !== 'undefined' && workspaceZoneGroup) {
                        workspaceZoneGroup.position.z = railZ;
                    }

                    const disp = document.getElementById('rail-pos-display');
                    if (disp) disp.innerText = newL.toFixed(1) + ' mm';
                    const pbar = document.getElementById('rail-progress-bar');
                    if (pbar) pbar.style.width = Math.min(100, Math.max(0, (newL / 1000.0) * 100)) + '%';

                    if (progress < 1.0) {
                        railAnimationFrameId = requestAnimationFrame(step);
                    } else {
                        currentRailL = targetL;
                        targetRailL = targetL;
                        isRailAnimating = false;
                        railAnimationFrameId = null;
                        resolve();
                    }
                }
                railAnimationFrameId = requestAnimationFrame(step);
            });
        }

        function onTargetGizmoChange() {
            const railYOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? 42 : 0;
            const zTcp = Math.round((targetBeaconGroup.position.y - L1_BASE - railYOffset) * 10) / 10;

            if (isRailModeActive) {
                const zWorld = targetBeaconGroup.position.z;
                const xWorld = targetBeaconGroup.position.x;
                const sol = solveRailKinematics(xWorld, zWorld, currentRailL);
                const lOpt = sol ? sol.l : Math.max(0.0, Math.min(1000.0, zWorld + 500.0));
                targetRailL = lOpt;
                const zCarriage = lOpt - 500.0;
                const xArm = sol ? Math.round(sol.xArm * 10) / 10 : Math.round(xWorld * 10) / 10;
                const yArm = sol ? Math.round(sol.yArm * 10) / 10 : Math.round(-(zWorld - zCarriage) * 10) / 10;

                document.getElementById('inp-target-x').value = xArm.toFixed(1);
                document.getElementById('inp-target-y').value = yArm.toFixed(1);
                document.getElementById('inp-target-z').value = zTcp.toFixed(1);
                updateTargetAncillaries(xArm, yArm, zTcp);
            } else {
                const x = Math.round(targetBeaconGroup.position.x * 10) / 10;
                const y = Math.round(-targetBeaconGroup.position.z * 10) / 10;
                document.getElementById('inp-target-x').value = x.toFixed(1);
                document.getElementById('inp-target-y').value = y.toFixed(1);
                document.getElementById('inp-target-z').value = zTcp.toFixed(1);
                updateTargetAncillaries(x, y, zTcp);
            }
        }

        function onTargetGizmoDragEnd() {
            onTargetGizmoChange();
            const x = parseFloat(document.getElementById('inp-target-x').value) || 0;
            const y = parseFloat(document.getElementById('inp-target-y').value) || 0;
            const zTcp = parseFloat(document.getElementById('inp-target-z').value) || 0;
            const zFlangeCheck = zTcp + toolOffset;
            const zMinCheck = cachedSafetyLimits ? (isRailModeActive ? (cachedSafetyLimits.z_min_rail ?? -180.0) : (cachedSafetyLimits.z_min_standalone ?? -65.0)) : -65.0;
            const zMaxCheck = (cachedSafetyLimits && cachedSafetyLimits.z_max !== undefined) ? cachedSafetyLimits.z_max : 165.0;

            if (isRailModeActive) {
                const zWorld = targetBeaconGroup.position.z;
                const xWorld = targetBeaconGroup.position.x;
                const sol = solveRailKinematics(xWorld, zWorld, currentRailL);
                if (!sol || zFlangeCheck < zMinCheck || zFlangeCheck > zMaxCheck) {
                    showToast(`⚠️ Điểm đích nằm ngoài vùng an toàn mở rộng của Ray trượt + Dobot!`);
                    return;
                }
                const autoMove = document.getElementById('chk-auto-move-drag');
                if (autoMove && autoMove.checked) {
                    if (sol.inCurrentReach) {
                        showToast(`🎯 Thả chuột ➔ Điểm trong tầm với (L=${currentRailL.toFixed(0)}mm), Dobot gắp luôn tại chỗ!`);
                    } else {
                        showToast(`🎯 Thả chuột ➔ Tự động phối hợp Ray (L=${sol.l.toFixed(0)}mm) + Dobot tới đích!`);
                    }
                    executeGoToPoint('safe');
                } else {
                    if (sol.inCurrentReach) {
                        showToast(`📍 Điểm trong tầm an toàn: L=${currentRailL.toFixed(0)}mm, X=${sol.xArm.toFixed(0)}, Y=${sol.yArm.toFixed(0)}. Bấm [Nhấc An Toàn] để gắp luôn!`);
                    } else {
                        showToast(`📍 Cần trượt ray: L=${sol.l.toFixed(0)}mm, X=${sol.xArm.toFixed(0)}, Y=${sol.yArm.toFixed(0)}, Z=${zTcp.toFixed(0)}. Bấm [Nhấc An Toàn] để chạy!`);
                    }
                    const btnSafe = document.querySelector('.btn-safe-jump');
                    if (btnSafe) {
                        btnSafe.style.transform = 'scale(1.05)';
                        setTimeout(() => { btnSafe.style.transform = ''; }, 400);
                    }
                }
            } else {
                const rHoriz = Math.sqrt(x * x + y * y);
                const rMinCheck = (cachedSafetyLimits && cachedSafetyLimits.r_min !== undefined) ? cachedSafetyLimits.r_min : 140.0;
                const rMaxCheck = (cachedSafetyLimits && cachedSafetyLimits.r_max !== undefined) ? cachedSafetyLimits.r_max : 330.0;

                if (rHoriz < rMinCheck || rHoriz > rMaxCheck || zFlangeCheck < zMinCheck || zFlangeCheck > zMaxCheck) {
                    showToast(`⚠️ Điểm đích (X=${x.toFixed(0)}, Y=${y.toFixed(0)}, Z=${zTcp.toFixed(0)}) nằm ngoài vùng an toàn!`);
                    return;
                }

                const autoMove = document.getElementById('chk-auto-move-drag');
                if (autoMove && autoMove.checked) {
                    showToast(`🎯 Thả chuột ➔ Robot đang di chuyển tới X=${x.toFixed(0)}, Y=${y.toFixed(0)}, Z=${zTcp.toFixed(0)}`);
                    executeGoToPoint('safe');
                } else {
                    showToast(`📍 Đã ghim điểm: X=${x.toFixed(0)}, Y=${y.toFixed(0)}, Z=${zTcp.toFixed(0)}. Bấm [Nhấc An Toàn] để chạy!`);
                    const btnSafe = document.querySelector('.btn-safe-jump');
                    if (btnSafe) {
                        btnSafe.style.transform = 'scale(1.05)';
                        setTimeout(() => { btnSafe.style.transform = ''; }, 400);
                    }
                }
            }
        }

        function updateTargetAncillaries(x, y, zTcp) {
            const railYOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? 42 : 0;
            const floorHeight = railYOffset + L1_BASE + zTcp;

            // Vòng tâm ngắm ở mặt sàn
            targetFloorReticle.position.set(targetBeaconGroup.position.x, 0.6, targetBeaconGroup.position.z);

            // Đường gióng rơi thẳng đứng
            const pts = [new THREE.Vector3(targetBeaconGroup.position.x, floorHeight, targetBeaconGroup.position.z), new THREE.Vector3(targetBeaconGroup.position.x, 0.6, targetBeaconGroup.position.z)];
            targetDropLine.geometry.setFromPoints(pts);
            targetDropLine.computeLineDistances();

            // Kiểm tra an toàn dựa trên cấu hình Vùng An Toàn (Safety Limits)
            const rMin = (cachedSafetyLimits && cachedSafetyLimits.r_min !== undefined) ? cachedSafetyLimits.r_min : 140.0;
            const rMax = (cachedSafetyLimits && cachedSafetyLimits.r_max !== undefined) ? cachedSafetyLimits.r_max : 330.0;
            const zMin = cachedSafetyLimits ? (isRailModeActive ? (cachedSafetyLimits.z_min_rail ?? -180.0) : (cachedSafetyLimits.z_min_standalone ?? -65.0)) : -65.0;
            const zMax = (cachedSafetyLimits && cachedSafetyLimits.z_max !== undefined) ? cachedSafetyLimits.z_max : 165.0;
            const zFlange = zTcp + toolOffset;

            let isValid = true;
            let msg = '';

            if (isRailModeActive) {
                const zWorld = targetBeaconGroup.position.z;
                const xWorld = targetBeaconGroup.position.x;
                const sol = solveRailKinematics(xWorld, zWorld, currentRailL);
                if (!sol) {
                    isValid = false;
                    msg = `⚠️ Ngoài tầm với của Ray trượt + Dobot (X: ${xWorld.toFixed(0)}mm)!`;
                } else if (zFlange < zMin) {
                    isValid = false;
                    msg = `⚠️ Cao độ Flange quá thấp (${zFlange.toFixed(1)}mm < ${zMin.toFixed(0)}mm)!`;
                } else if (zFlange > zMax) {
                    isValid = false;
                    msg = `⚠️ Cao độ Flange quá cao (${zFlange.toFixed(1)}mm > ${zMax.toFixed(0)}mm)!`;
                } else {
                    targetRailL = sol.l;
                    const deltaL = Math.abs(sol.l - currentRailL);
                    if (deltaL > 0.5 && !sol.inCurrentReach) {
                        msg = `✅ Trong tầm với Ray (Tự trượt tới L = ${sol.l.toFixed(0)}mm | Dobot: X=${sol.xArm.toFixed(0)}, Y=${sol.yArm.toFixed(0)})`;
                    } else {
                        msg = `✅ Trong tầm với hiện tại (L = ${currentRailL.toFixed(0)}mm | Dobot gắp luôn: R=${sol.r.toFixed(0)}mm)`;
                    }
                }
            } else {
                const rHoriz = Math.sqrt(x * x + y * y);
                msg = `✅ Trong tầm với an toàn (R: ${rHoriz.toFixed(1)} mm, Z_TCP: ${zTcp.toFixed(1)} mm)`;
                if (rHoriz < rMin) {
                    isValid = false;
                    msg = `⚠️ Quá gần thân robot (${rHoriz.toFixed(1)}mm < ${rMin.toFixed(0)}mm)!`;
                } else if (rHoriz > rMax) {
                    isValid = false;
                    msg = `⚠️ Vượt quá tầm với tối đa (${rHoriz.toFixed(1)}mm > ${rMax.toFixed(0)}mm)!`;
                } else if (zFlange < zMin) {
                    isValid = false;
                    msg = `⚠️ Cao độ Flange quá thấp (${zFlange.toFixed(1)}mm < ${zMin.toFixed(0)}mm đáy an toàn)!`;
                } else if (zFlange > zMax) {
                    isValid = false;
                    msg = `⚠️ Cao độ Flange quá cao (${zFlange.toFixed(1)}mm > ${zMax.toFixed(0)}mm đỉnh an toàn)!`;
                }
            }

            const badge = document.getElementById('target-reachability-badge');
            if (badge) {
                badge.className = `reach-badge ${isValid ? 'valid' : 'invalid'}`;
                badge.innerText = msg;
            }

            const colorHex = isValid ? 0x51cf66 : 0xff6b6b;
            const emissiveHex = isValid ? 0x2f9e44 : 0xc92a2a;
            beaconBoxMat.color.setHex(colorHex);
            beaconBoxMat.emissive.setHex(emissiveHex);
            targetFloorReticle.material.color.setHex(colorHex);
            targetDropLineMat.color.setHex(colorHex);

            updateBeaconHudLabel(targetBeaconGroup.position, x, y, zTcp, isValid);
        }

        function updateBeaconHudLabel(pos, x, y, zTcp, isValid) {
            const label = document.getElementById('beacon-hud');
            if (!label) return;
            if (!isTargetGizmoActive) {
                label.style.display = 'none';
                return;
            }

            const p = pos.clone();
            p.project(camera);
            if (p.z < 1) {
                const sx = (p.x * 0.5 + 0.5) * window.innerWidth;
                const sy = (-(p.y * 0.5) + 0.5) * window.innerHeight;
                label.style.left = `${sx}px`;
                label.style.top = `${sy}px`;
                label.style.display = 'block';
                label.style.borderColor = isValid ? '#51cf66' : '#ff6b6b';
                label.style.color = isValid ? '#51cf66' : '#ff6b6b';
                if (isRailModeActive && typeof targetRailL !== 'undefined') {
                    label.innerText = `🎯 ĐÍCH (L=${targetRailL.toFixed(0)}mm): (${x.toFixed(0)}, ${y.toFixed(0)}, ${zTcp.toFixed(0)})`;
                } else {
                    label.innerText = `🎯 ĐÍCH: (${x.toFixed(0)}, ${y.toFixed(0)}, ${zTcp.toFixed(0)})`;
                }
            } else {
                label.style.display = 'none';
            }
        }

        function updateTargetMarker() {
            const x = parseFloat(document.getElementById('inp-target-x').value) || 0;
            const y = parseFloat(document.getElementById('inp-target-y').value) || 0;
            const zTcp = parseFloat(document.getElementById('inp-target-z').value) || 0;

            const railYOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? 42 : 0;
            const floorHeight = railYOffset + L1_BASE + zTcp;
            const railOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? (-500 + currentRailL) : 0;
            targetBeaconGroup.position.set(x, floorHeight, railOffset - y);

            updateTargetAncillaries(x, y, zTcp);
        }

        function copyCurrentPoseToTargetInputs() {
            document.getElementById('inp-target-x').value = currentX.toFixed(1);
            document.getElementById('inp-target-y').value = currentY.toFixed(1);
            document.getElementById('inp-target-z').value = currentZ.toFixed(1);
            document.getElementById('inp-target-r').value = currentR.toFixed(1);
            if (isRailModeActive) targetRailL = currentRailL;
            updateTargetMarker();
            renderTeachList();
            showToast('📍 Đã nạp vị trí thực tế của đầu hút vào ô nhập!');
        }

        function setTargetPreset(x, y, z, r) {
            document.getElementById('inp-target-x').value = x;
            document.getElementById('inp-target-y').value = y;
            document.getElementById('inp-target-z').value = z;
            document.getElementById('inp-target-r').value = r;
            if (isRailModeActive) targetRailL = currentRailL;
            updateTargetMarker();
            showToast(`🎯 Đã chọn điểm đích: X=${x}, Y=${y}, Z=${z}`);
        }

        let isExecutingMotion = false;

        async function executeGoToPoint(mode) {
            if (isExecutingMotion) {
                console.warn("⚠️ Robot đang thực hiện di chuyển, bỏ qua lệnh trùng lặp!");
                return;
            }
            isExecutingMotion = true;
            try {
                const x = parseFloat(document.getElementById('inp-target-x').value);
                const y = parseFloat(document.getElementById('inp-target-y').value);
                const zTcp = parseFloat(document.getElementById('inp-target-z').value);
                const r = parseFloat(document.getElementById('inp-target-r').value) || 0;
                const zFlange = zTcp + toolOffset;

                const zMinLimit = cachedSafetyLimits ? (isRailModeActive ? (cachedSafetyLimits.z_min_rail ?? -180.0) : (cachedSafetyLimits.z_min_standalone ?? -65.0)) : -65.0;
                const zMaxLimit = (cachedSafetyLimits && cachedSafetyLimits.z_max !== undefined) ? cachedSafetyLimits.z_max : 165.0;

                if (isRailModeActive) {
                    // Tọa độ mục tiêu trong không gian 3D World
                    const zWorld = targetBeaconGroup.position.z;
                    const xWorld = targetBeaconGroup.position.x;
                    const sol = solveRailKinematics(xWorld, zWorld, currentRailL);

                    // 1. Kiểm tra an toàn mở rộng (nhờ có ray)
                    if (!sol || zFlange < zMinLimit || zFlange > zMaxLimit) {
                        alert(`⚠️ Điểm đích nằm ngoài vùng an toàn mở rộng của Robot + Ray trượt!\n\n` +
                              `• Tọa độ bàn làm việc: X = ${xWorld.toFixed(1)} mm, Z = ${zWorld.toFixed(1)} mm\n` +
                              `• Cao độ Flange: ${zFlange.toFixed(1)} mm (Z đầu hút: ${zTcp.toFixed(1)} mm | Cho phép: [${zMinLimit}, ${zMaxLimit}] mm)\n\n` +
                              `Không thể thực hiện di chuyển đến điểm ngoài vùng an toàn!`);
                        return;
                    }

                    const lOptimal = sol.l;
                    const xArm = sol.xArm;
                    const yArm = sol.yArm;
                    const railSpeed = parseFloat(document.getElementById('slider-rail-speed')?.value || 100);
                    const deltaL = Math.abs(lOptimal - currentRailL);

                    // 2. BƯỚC 1: DI CHUYỂN RAY ĐẾN VỊ TRÍ ĐÓN (CHỈ KHI CẦN THIẾT)
                    if (deltaL > 0.5 && !sol.inCurrentReach) {
                        showToast(`🚄 [Bước 1/2] Đang di chuyển ray trượt tới L = ${lOptimal.toFixed(0)} mm...`);
                        // Luôn gửi rail_move qua WebSocket để server cập nhật và đồng bộ rail_current_pos
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            sendAction('rail_move', { pos: lOptimal, l: lOptimal, speed: railSpeed });
                        }
                        if (ws && ws.readyState === WebSocket.OPEN && isRobotConnected && currentMode === 'live') {
                            const estDurationMs = (deltaL / railSpeed) * 1000;
                            const maxWaitMs = estDurationMs + 5000;
                            const tStart = Date.now();
                            await sleepMs(300); // Chờ server nhận lệnh và bật cờ moving
                            while (Date.now() - tStart < maxWaitMs) {
                                if (!isRailHardwareMoving && Math.abs(currentRailL - lOptimal) <= 1.5) {
                                    break; // Ray đã tới đích và dừng hẳn
                                }
                                await sleepMs(50);
                            }
                            if (Math.abs(currentRailL - lOptimal) > 3.0) {
                                showToast(`⚠️ Ray chưa tới đích yêu cầu (${currentRailL.toFixed(1)} != ${lOptimal.toFixed(1)} mm)! Đã hủy bước 2.`);
                                return;
                            }
                        } else {
                            await animateRailMove(lOptimal, railSpeed);
                        }
                        currentRailL = lOptimal;
                        targetRailL = lOptimal;
                    } else {
                        showToast(`🎯 Điểm trong tầm an toàn của Dobot (L = ${currentRailL.toFixed(0)} mm) ➔ Dobot gắp luôn tại chỗ!`);
                    }

                    // 3. BƯỚC 2: DI CHUYỂN DOBOT TỚI ĐÍCH
                    showToast(`🎯 [Bước 2/2] Dobot đang vươn tới đích (X=${xArm.toFixed(0)}, Y=${yArm.toFixed(0)}, Z=${zTcp.toFixed(0)})...`);
                    if (ws && ws.readyState === WebSocket.OPEN && isRobotConnected && currentMode === 'live') {
                        if (mode === 'safe') {
                            sendAction('safe_jump', { x: xArm, y: yArm, z: zFlange, r: r });
                        } else {
                            sendAction('move_xyz', { x: xArm, y: yArm, z: zFlange, r: r, mode: 1 });
                        }
                    } else {
                        await animateRobotCartesian(xArm, yArm, zTcp, r, mode, mode === 'safe' ? 600 : 450);
                    }
                    showToast(`🎉 Hoàn tất di chuyển tới đích (L=${currentRailL.toFixed(0)}mm)!`);
                } else {
                    // CHẾ ĐỘ STANDALONE ĐỂ BÀN ĐỘC LẬP
                    const rHoriz = Math.sqrt(x * x + y * y);
                    const rMin = (cachedSafetyLimits && cachedSafetyLimits.r_min !== undefined) ? cachedSafetyLimits.r_min : 140.0;
                    const rMax = (cachedSafetyLimits && cachedSafetyLimits.r_max !== undefined) ? cachedSafetyLimits.r_max : 330.0;

                    if (rHoriz < rMin || rHoriz > rMax || zFlange < zMinLimit || zFlange > zMaxLimit) {
                        alert(`⚠️ Tọa độ không an toàn!\nBán kính: ${rHoriz.toFixed(1)}mm (hợp lệ: ${rMin} - ${rMax}mm)\nFlange Z: ${zFlange.toFixed(1)}mm (Z đầu hút: ${zTcp.toFixed(1)}mm)\nGiới hạn an toàn Flange: [${zMinLimit}, ${zMaxLimit}]mm`);
                        return;
                    }
                    if (typeof isSimulationMode === 'function' && isSimulationMode()) {
                        showToast(`🎮 [Mô phỏng 3D] ${mode === 'safe' ? 'Nhấc an toàn' : 'Bay thẳng'} -> X=${x.toFixed(0)}, Y=${y.toFixed(0)}, Z=${zTcp.toFixed(0)}`);
                        await animateRobotCartesian(x, y, zTcp, r, mode, mode === 'safe' ? 600 : 450);
                    } else {
                        if (mode === 'safe') {
                            sendAction('safe_jump', { x: x, y: y, z: zFlange, r: r });
                            showToast(`📦 Safe Jump: Nhấc an toàn -> X=${x.toFixed(0)}, Y=${y.toFixed(0)}, Z=${zTcp.toFixed(0)}`);
                        } else {
                            sendAction('move_xyz', { x: x, y: y, z: zFlange, r: r, mode: 1 });
                            showToast(`🚀 Direct PTP: Bay thẳng -> X=${x.toFixed(0)}, Y=${y.toFixed(0)}, Z=${zTcp.toFixed(0)}`);
                        }
                    }
                }
            } finally {
                isExecutingMotion = false;
            }
        }

        // ========================================================
        // TƯƠNG TÁC CHUỘT SNAP VÀ DI CHUỘT TRÊN MẶT BÀN
        // ========================================================
        const raycaster = new THREE.Raycaster();
        const mouseVec = new THREE.Vector2();
        let mouseDownTime = 0;
        let mouseDownPos = { x: 0, y: 0 };

        function get3DPointFromMouse(event) {
            const container = document.getElementById('canvas-container');
            const rect = container.getBoundingClientRect();
            mouseVec.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            mouseVec.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

            raycaster.setFromCamera(mouseVec, camera);

            // Cao độ mặt phẳng chọn điểm (Robot Z = targetZ, tính theo Three.js Y = railYOffset + L1_BASE + targetZ)
            const targetZ = parseFloat(document.getElementById('inp-target-z').value) || 0;
            const railYOffset = (typeof isRailModeActive !== 'undefined' && isRailModeActive) ? 42 : 0;
            const planeY = railYOffset + L1_BASE + targetZ;
            const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -planeY);
            const hit = new THREE.Vector3();
            const result = raycaster.ray.intersectPlane(plane, hit);

            if (result) {
                if (isRailModeActive) {
                    const sol = solveRailKinematics(hit.x, hit.z, currentRailL);
                    const lOpt = sol ? sol.l : Math.max(0.0, Math.min(1000.0, hit.z + 500.0));
                    const zCarriage = lOpt - 500.0;
                    const xArm = sol ? Math.round(sol.xArm * 10) / 10 : Math.round(hit.x * 10) / 10;
                    const yArm = sol ? Math.round(sol.yArm * 10) / 10 : Math.round(-(hit.z - zCarriage) * 10) / 10;
                    return {
                        x: xArm,
                        y: yArm,
                        z: targetZ,
                        l: Math.round(lOpt * 10) / 10,
                        worldPos: hit
                    };
                } else {
                    return {
                        x: Math.round(hit.x * 10) / 10,
                        y: Math.round(-hit.z * 10) / 10,
                        z: targetZ,
                        l: 0,
                        worldPos: hit
                    };
                }
            }
            return null;
        }

        function applyPickedPoint(rawX, rawY, rawZ, pickedL=null) {
            const curZ = parseFloat(document.getElementById('inp-target-z').value) || 0;
            document.getElementById('inp-target-x').value = rawX.toFixed(1);
            document.getElementById('inp-target-y').value = rawY.toFixed(1);

            if (isRailModeActive) {
                if (pickedL !== null) targetRailL = pickedL;
                const railYOffset = 42;
                const floorHeight = railYOffset + L1_BASE + curZ;
                const zCarriage = (targetRailL !== null ? targetRailL : currentRailL) - 500;
                targetBeaconGroup.position.set(rawX, floorHeight, zCarriage - rawY);
                updateTargetAncillaries(rawX, rawY, curZ);

                const sol = solveRailKinematics(rawX, targetBeaconGroup.position.z, currentRailL);
                if (!sol) {
                    showToast(`⚠️ Điểm ngoài vùng làm việc của Ray trượt!`);
                    return;
                }
                const autoMove = document.getElementById('chk-auto-move-drag');
                if (autoMove && autoMove.checked) {
                    if (sol.inCurrentReach) {
                        showToast(`🎯 Click chọn ➔ Điểm trong tầm an toàn (L=${currentRailL.toFixed(0)}mm), Dobot gắp luôn tại chỗ!`);
                    } else {
                        showToast(`🎯 Click chọn ➔ Tự động phối hợp Ray (L=${sol.l.toFixed(0)}mm) + Dobot tới đích!`);
                    }
                    executeGoToPoint('safe');
                } else {
                    if (sol.inCurrentReach) {
                        showToast(`📍 Trong tầm với an toàn: L=${currentRailL.toFixed(0)}mm, X=${sol.xArm.toFixed(0)}, Y=${sol.yArm.toFixed(0)}. Bấm [Nhấc An Toàn] để gắp luôn!`);
                    } else {
                        showToast(`📍 Đã ghim điểm: L=${sol.l.toFixed(0)}mm, X=${sol.xArm.toFixed(0)}, Y=${sol.yArm.toFixed(0)}. Bấm [Nhấc An Toàn] để chạy!`);
                    }
                }
            } else {
                updateTargetMarker();
                const rHoriz = Math.sqrt(rawX * rawX + rawY * rawY);
                if (rHoriz < 140.0) {
                    showToast(`⚠️ Điểm (X=${rawX.toFixed(0)}, Y=${rawY.toFixed(0)}) quá gần đế robot (< 140mm)!`);
                    return;
                }
                if (rHoriz > 330.0) {
                    showToast(`⚠️ Điểm (X=${rawX.toFixed(0)}, Y=${rawY.toFixed(0)}) vượt quá tầm với (> 330mm)!`);
                    return;
                }
                const autoMove = document.getElementById('chk-auto-move-drag');
                if (autoMove && autoMove.checked) {
                    showToast(`🎯 Click chọn ➔ Robot đang di chuyển tới X=${rawX.toFixed(0)}, Y=${rawY.toFixed(0)}, Z=${curZ.toFixed(0)}`);
                    executeGoToPoint('safe');
                } else {
                    showToast(`📍 Đã ghim điểm đích tới X=${rawX.toFixed(0)}, Y=${rawY.toFixed(0)}. Kéo mũi tên xanh lá để chỉnh Z!`);
                }
            }
        }

        // Bắt phím Shift để đổi con trỏ
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Shift') {
                document.getElementById('canvas-container').classList.add('canvas-picking');
                zoneMat.opacity = 0.32;
            }
        });

        window.addEventListener('keyup', (e) => {
            if (e.key === 'Shift') {
                document.getElementById('canvas-container').classList.remove('canvas-picking');
                zoneMat.opacity = 0.12;
                hoverReticle.visible = false;
                document.getElementById('hover-tooltip').style.display = 'none';
            }
        });

        // Xử lý Mouse Down / Up phân biệt giữa Click snap điểm và Drag xoay camera
        window.addEventListener('mousedown', (e) => {
            mouseDownTime = Date.now();
            mouseDownPos = { x: e.clientX, y: e.clientY };
        });

        window.addEventListener('mouseup', (e) => {
            const elapsed = Date.now() - mouseDownTime;
            const dx = e.clientX - mouseDownPos.x;
            const dy = e.clientY - mouseDownPos.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            // Nếu đang kéo gizmo hoặc kéo xoay camera thì bỏ qua
            if (isDraggingGizmo || dist > 8 || elapsed > 800) return;

            // Bỏ qua nếu click trên sidebar menu, nút nổi hoặc toast
            if (e.target.closest('#panel') || e.target.closest('#floating-toggle-btn') || e.target.closest('#toast-container')) return;

            // Click snap điểm trên mặt bàn
            if (e.shiftKey || (isTargetGizmoActive && e.button === 0)) {
                const pt = get3DPointFromMouse(e);
                if (pt) {
                    applyPickedPoint(pt.x, pt.y, pt.z, pt.l);
                }
            }
        });

        // Xử lý di chuột Hover
        window.addEventListener('mousemove', (e) => {
            if (e.target.closest('#panel') || e.target.closest('#floating-toggle-btn') || isDraggingGizmo) {
                hoverReticle.visible = false;
                document.getElementById('hover-tooltip').style.display = 'none';
                return;
            }

            if (e.shiftKey) {
                const pt = get3DPointFromMouse(e);
                const tooltip = document.getElementById('hover-tooltip');
                if (pt) {
                    const rHoriz = Math.sqrt(pt.x * pt.x + pt.y * pt.y);
                    const isValid = (rHoriz >= 140 && rHoriz <= 330);

                    hoverReticle.position.set(pt.worldPos.x, pt.worldPos.y + 0.5, pt.worldPos.z);
                    hoverReticle.visible = true;

                    const colorHex = isValid ? 0x51cf66 : 0xff6b6b;
                    hoverRing.material.color.setHex(colorHex);
                    hoverDot.material.color.setHex(colorHex);

                    tooltip.style.left = `${e.clientX}px`;
                    tooltip.style.top = `${e.clientY}px`;
                    tooltip.style.display = 'block';
                    tooltip.innerHTML = `🎯 <b>X:</b> ${pt.x.toFixed(0)} mm | <b>Y:</b> ${pt.y.toFixed(0)} mm <span style="color:${isValid ? '#51cf66' : '#ff6b6b'}">(${isValid ? 'Hợp lệ' : 'Ngoài tầm ⚠️'})</span>`;
                } else {
                    hoverReticle.visible = false;
                    tooltip.style.display = 'none';
                }
            } else {
                hoverReticle.visible = false;
                document.getElementById('hover-tooltip').style.display = 'none';
            }
        });

        // --- Gửi lệnh di chuyển tới Robot thật ---
        function sendMoveToRobot() {
            if (coordSystem === 'cartesian') {
                const x = parseFloat(document.getElementById('cart-x').value);
                const y = parseFloat(document.getElementById('cart-y').value);
                const zTcp = parseFloat(document.getElementById('cart-z').value);
                const zFlange = zTcp + toolOffset;
                const r = parseFloat(document.getElementById('cart-r').value);
                console.log(`Gửi lệnh PTP XYZ: X=${x}, Y=${y}, Z=${zFlange}, R=${r}`);
                sendAction('move_xyz', { x: x, y: y, z: zFlange, r: r, mode: 1 });
                showToast(`🚀 Đang gửi PTP: X=${x.toFixed(0)}, Y=${y.toFixed(0)}, Z=${zTcp.toFixed(0)}`);
            } else {
                const j1 = parseFloat(document.getElementById('j1').value);
                const j2 = parseFloat(document.getElementById('j2').value);
                const j3 = parseFloat(document.getElementById('j3').value);
                const j4 = parseFloat(document.getElementById('j4').value);
                console.log(`Gửi lệnh Joint: J1=${j1}, J2=${j2}, J3=${j3}, J4=${j4}`);
                sendAction('move_joint', { j1: j1, j2: j2, j3: j3, j4: j4, mode: 4 });
                showToast(`🔄 Đang gửi góc khớp: J1=${j1.toFixed(1)}°, J2=${j2.toFixed(1)}°`);
            }
        }

        // --- Toast Notification ---
        function showToast(msg) {
            let container = document.getElementById('toast-container');
            if (!container) {
                container = document.createElement('div');
                container.id = 'toast-container';
                document.body.appendChild(container);
            }
            const toast = document.createElement('div');
            toast.className = 'toast-msg';
            toast.innerText = msg;
            container.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = '0';
                setTimeout(() => toast.remove(), 300);
            }, 2500);
        }

        function configureServerUrl() {
            const current = localStorage.getItem('dobot_ws_url') || "";
            const input = prompt("⚙️ CẤU HÌNH KẾT NỐI ROBOT (Publish Web/Tunnel):\n\nNhập địa chỉ WebSocket Server của Robot (Ví dụ:\nwss://your-tunnel.trycloudflare.com/ws\nhoặc wss://abc.ngrok-free.app/ws\nhoặc ws://localhost:8080/ws).\n\nĐể trống để tự động dò tìm:", current);
            if (input !== null) {
                if (input.trim() === "") {
                    localStorage.removeItem('dobot_ws_url');
                    showToast("🔄 Đã xóa cấu hình riêng, chuyển về tự động dò tìm");
                } else {
                    localStorage.setItem('dobot_ws_url', input.trim());
                    showToast("💾 Đã lưu địa chỉ Server mới!");
                }
                if (ws) {
                    try { ws.close(); } catch(e){}
                }
                initWebSocket();
            }
        }


        // --- KÉO THẢ DI CHUYỂN MENU (DRAGGABLE) ---
        (function initDraggablePanel() {
            let isDragging = false;
            let startX = 0, startY = 0;
            let initialLeft = 0, initialTop = 0;

            panelTitleBar.addEventListener('mousedown', (e) => {
                // Không kéo nếu click vào các nút điều khiển
                if (e.target.closest('button') || e.target.closest('input')) return;
                
                isDragging = true;
                panelEl.classList.add('is-dragging');
                startX = e.clientX;
                startY = e.clientY;
                const rect = panelEl.getBoundingClientRect();
                initialLeft = rect.left;
                initialTop = rect.top;

                panelTitleBar.style.cursor = 'grabbing';
                e.preventDefault();
                e.stopPropagation();

                function onMouseMove(moveEvent) {
                    if (!isDragging) return;
                    const dx = moveEvent.clientX - startX;
                    const dy = moveEvent.clientY - startY;

                    let newLeft = initialLeft + dx;
                    let newTop = initialTop + dy;

                    // Giới hạn biên màn hình
                    const maxLeft = window.innerWidth - panelEl.offsetWidth - 10;
                    const maxTop = window.innerHeight - 50;
                    newLeft = Math.max(10, Math.min(maxLeft, newLeft));
                    newTop = Math.max(10, Math.min(maxTop, newTop));

                    panelEl.style.left = newLeft + 'px';
                    panelEl.style.top = newTop + 'px';
                    panelEl.style.right = 'auto';
                    panelEl.style.bottom = 'auto';
                }

                function onMouseUp() {
                    isDragging = false;
                    panelEl.classList.remove('is-dragging');
                    panelTitleBar.style.cursor = 'grab';
                    window.removeEventListener('mousemove', onMouseMove);
                    window.removeEventListener('mouseup', onMouseUp);
                }

                window.addEventListener('mousemove', onMouseMove);
                window.addEventListener('mouseup', onMouseUp);
            });

            // Hỗ trợ cảm ứng màn hình
            panelTitleBar.addEventListener('touchstart', (e) => {
                if (e.target.closest('button')) return;
                const touch = e.touches[0];
                isDragging = true;
                panelEl.classList.add('is-dragging');
                startX = touch.clientX;
                startY = touch.clientY;
                const rect = panelEl.getBoundingClientRect();
                initialLeft = rect.left;
                initialTop = rect.top;

                function onTouchMove(te) {
                    if (!isDragging) return;
                    const t = te.touches[0];
                    let newLeft = initialLeft + (t.clientX - startX);
                    let newTop = initialTop + (t.clientY - startY);
                    newLeft = Math.max(10, Math.min(window.innerWidth - panelEl.offsetWidth - 10, newLeft));
                    newTop = Math.max(10, Math.min(window.innerHeight - 50, newTop));
                    panelEl.style.left = newLeft + 'px';
                    panelEl.style.top = newTop + 'px';
                }

                function onTouchEnd() {
                    isDragging = false;
                    panelEl.classList.remove('is-dragging');
                    window.removeEventListener('touchmove', onTouchMove);
                    window.removeEventListener('touchend', onTouchEnd);
                }

                window.addEventListener('touchmove', onTouchMove);
                window.addEventListener('touchend', onTouchEnd);
            }, { passive: false });
        })();

        // --- KÉO THAY ĐỔI KÍCH THƯỚC (RESIZABLE) ---
        (function initResizablePanel() {
            function handleResizeDrag(handleEl, resizeWidth, resizeHeight) {
                if (!handleEl) return;
                handleEl.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    panelEl.classList.add('is-resizing');
                    panelEl.classList.remove('maximized'); // Hủy cờ maximized nếu tự tay resize

                    const startX = e.clientX;
                    const startY = e.clientY;
                    const startWidth = panelEl.offsetWidth;
                    const startHeight = panelEl.offsetHeight;

                    function onMouseMove(moveEvent) {
                        if (resizeWidth) {
                            const newW = startWidth + (moveEvent.clientX - startX);
                            const clampedW = Math.max(300, Math.min(window.innerWidth - panelEl.offsetLeft - 10, newW));
                            panelEl.style.width = clampedW + 'px';
                        }
                        if (resizeHeight) {
                            const newH = startHeight + (moveEvent.clientY - startY);
                            const clampedH = Math.max(180, Math.min(window.innerHeight - panelEl.offsetTop - 10, newH));
                            panelEl.style.height = clampedH + 'px';
                        }
                    }

                    function onMouseUp() {
                        panelEl.classList.remove('is-resizing');
                        window.removeEventListener('mousemove', onMouseMove);
                        window.removeEventListener('mouseup', onMouseUp);
                    }

                    window.addEventListener('mousemove', onMouseMove);
                    window.addEventListener('mouseup', onMouseUp);
                });
            }

            handleResizeDrag(resizeCorner, true, true);
            handleResizeDrag(resizeEdgeR, true, false);
            handleResizeDrag(resizeEdgeB, false, true);
        })();



        async function animateRobotCartesian(targetX, targetY, targetZ_TCP, targetR, mode='direct', totalDurationMs=500, checkActive=null, isPaused=null) {
            const startX = (currentX !== undefined && !isNaN(currentX)) ? currentX : ((lastKnownRobotPose && lastKnownRobotPose.x) || 250);
            const startY = (currentY !== undefined && !isNaN(currentY)) ? currentY : ((lastKnownRobotPose && lastKnownRobotPose.y) || 0);
            const startZ = (currentZ !== undefined && !isNaN(currentZ)) ? currentZ : ((lastKnownRobotPose && lastKnownRobotPose.zTcp !== undefined) ? lastKnownRobotPose.zTcp : 50);
            const startR = (currentR !== undefined && !isNaN(currentR)) ? currentR : ((lastKnownRobotPose && lastKnownRobotPose.r) || 0);

            function easeInOut(t) {
                return t * t * (3 - 2 * t);
            }

            const stepMs = 25; // ~40 FPS
            const steps = Math.max(6, Math.round(totalDurationMs / stepMs));

            // Safe jump safe height
            let zSafe = Math.max(startZ, targetZ_TCP) + 35;
            if (zSafe > 140) zSafe = 140;
            if (zSafe < 30) zSafe = 30;

            for (let step = 1; step <= steps; step++) {
                if (checkActive && !checkActive()) return false;
                while (isPaused && isPaused()) {
                    if (checkActive && !checkActive()) return false;
                    await sleepMs(50);
                }

                const t = step / steps;
                let curX, curY, curZ, curR;

                if (mode === 'safe') {
                    // 3-phase trajectory: Lift (0 -> 0.28), Traverse (0.28 -> 0.72), Lower (0.72 -> 1.0)
                    if (t <= 0.28) {
                        const u = easeInOut(t / 0.28);
                        curX = startX;
                        curY = startY;
                        curR = startR;
                        curZ = startZ + u * (zSafe - startZ);
                    } else if (t <= 0.72) {
                        const u = easeInOut((t - 0.28) / (0.72 - 0.28));
                        curX = startX + u * (targetX - startX);
                        curY = startY + u * (targetY - startY);
                        curR = startR + u * (targetR - startR);
                        curZ = zSafe;
                    } else {
                        const u = easeInOut((t - 0.72) / (1.0 - 0.72));
                        curX = targetX;
                        curY = targetY;
                        curR = targetR;
                        curZ = zSafe + u * (targetZ_TCP - zSafe);
                    }
                } else {
                    // Direct PTP linear interpolation
                    const u = easeInOut(t);
                    curX = startX + u * (targetX - startX);
                    curY = startY + u * (targetY - startY);
                    curZ = startZ + u * (targetZ_TCP - startZ);
                    curR = startR + u * (targetR - startR);
                }

                const ik = solveIK(curX, curY, curZ);
                if (ik) {
                    const zFlange = curZ + toolOffset;
                    const j4 = curR - ik.j1;
                    renderRobot(ik.j1, ik.j2, ik.j3, j4, curX, curY, zFlange);
                }

                await sleepMs(stepMs);
            }

            // Ensure exact target pose at the end
            const finalIk = solveIK(targetX, targetY, targetZ_TCP);
            if (finalIk) {
                const finalZFlange = targetZ_TCP + toolOffset;
                const finalJ4 = targetR - finalIk.j1;
                renderRobot(finalIk.j1, finalIk.j2, finalIk.j3, finalJ4, targetX, targetY, finalZFlange);
            }
            return true;
        }

        async function animateRobotJoints(targetJ1, targetJ2, targetJ3, targetJ4, totalDurationMs=450, checkActive=null, isPaused=null) {
            const startJ1 = (lastRawJoints && !isNaN(lastRawJoints.j1)) ? lastRawJoints.j1 : 0;
            const startJ2 = (lastRawJoints && !isNaN(lastRawJoints.j2)) ? lastRawJoints.j2 : 0;
            const startJ3 = (lastRawJoints && !isNaN(lastRawJoints.j3)) ? lastRawJoints.j3 : 0;
            const startJ4 = (lastRawJoints && !isNaN(lastRawJoints.j4)) ? lastRawJoints.j4 : 0;

            function easeInOut(t) {
                return t * t * (3 - 2 * t);
            }

            const stepMs = 25;
            const steps = Math.max(6, Math.round(totalDurationMs / stepMs));

            for (let step = 1; step <= steps; step++) {
                if (checkActive && !checkActive()) return false;
                while (isPaused && isPaused()) {
                    if (checkActive && !checkActive()) return false;
                    await sleepMs(50);
                }

                const t = step / steps;
                const u = easeInOut(t);
                const curJ1 = startJ1 + u * (targetJ1 - startJ1);
                const curJ2 = startJ2 + u * (targetJ2 - startJ2);
                const curJ3 = startJ3 + u * (targetJ3 - startJ3);
                const curJ4 = startJ4 + u * (targetJ4 - startJ4);

                renderRobot(curJ1, curJ2, curJ3, curJ4);
                await sleepMs(stepMs);
            }

            renderRobot(targetJ1, targetJ2, targetJ3, targetJ4);
            return true;
        }
        

        // ========================================================
        // HỆ THỐNG DẠY ĐIỂM & CHẠY CHUỖI (TEACH & PLAYBACK)
        // ========================================================
        function sleepMs(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

