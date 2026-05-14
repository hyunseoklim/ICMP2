"""
core/management/commands/seed.py
─────────────────────────────────
ICMP2 통합 시드 커맨드

사용법:
    python manage.py seed              # 전체 시드
    python manage.py seed --flush      # DB 초기화 후 시드
    python manage.py seed --section accounts
    python manage.py seed --section facilities
    python manage.py seed --section monitoring
    python manage.py seed --section alerts
    python manage.py seed --section safety
    python manage.py seed --section workers
"""

import sys
from django.core.management.base import BaseCommand
from django.db import transaction, connection


# ─────────────────────────────────────────────────────────────
# 섹션별 시드 함수
# ─────────────────────────────────────────────────────────────

def seed_accounts():
    """departments, users (admin / manager1 / worker1 / worker_002~005 / worker_006~105)"""
    from accounts.models import Department, User

    print("  [accounts] departments...")
    depts = [
        ("DEPT_001", "경영지원팀"),
        ("DEPT_002", "영업팀"),
        ("DEPT_003", "사업기획팀"),
        ("DEPT_004", "기술연구소"),
        ("DEPT_005", "개발팀"),
        ("DEPT_006", "관제운영팀"),
        ("DEPT_007", "시스템운영팀"),
        ("DEPT_008", "안전관리팀"),
        ("DEPT_009", "품질관리팀"),
        ("DEPT_010", "생산관리팀"),
        ("DEPT_011", "설치공사팀"),
        ("DEPT_012", "유지보수팀"),
        ("DEPT_013", "고객지원팀"),
    ]
    dept_map = {}
    for code, name in depts:
        obj, _ = Department.objects.get_or_create(code=code, defaults={"name": name})
        dept_map[code] = obj

    print("  [accounts] users (admin, manager1, worker1)...")
    # admin
    admin, created = User.objects.get_or_create(username="admin")
    if created or not admin.has_usable_password():
        admin.set_password("admin1234!")
    admin.name = "관리자"
    admin.user_type = "admin"
    admin.department = dept_map["DEPT_001"]
    admin.position = "부장"
    admin.phone = "010-0000-0001"
    admin.email = "admin@icmp.co.kr"
    admin.is_staff = True
    admin.is_superuser = True
    admin.save()

    # manager1
    mgr, created = User.objects.get_or_create(username="manager1")
    if created or not mgr.has_usable_password():
        mgr.set_password("manager1234!")
    mgr.name = "현장관리자"
    mgr.user_type = "manager"
    mgr.department = dept_map["DEPT_006"]
    mgr.position = "과장"
    mgr.phone = "010-0000-0002"
    mgr.email = "manager1@icmp.co.kr"
    mgr.is_staff = True
    mgr.save()

    # worker1 (W001 연결용)
    w1, created = User.objects.get_or_create(username="worker1")
    if created or not w1.has_usable_password():
        w1.set_password("worker1234!")
    w1.name = "김철수"
    w1.user_type = "worker"
    w1.department = dept_map["DEPT_010"]
    w1.position = "사원"
    w1.phone = "010-0000-0003"
    w1.email = "worker1@icmp.co.kr"
    w1.save()

    print("  [accounts] users (worker_002~005)...")
    worker_core = [
        ("worker_002", "이영희",  "010-6631-6561"),
        ("worker_003", "박민준",  "010-4359-5031"),
        ("worker_004", "최수진",  "010-2109-9189"),
        ("worker_005", "정도현",  "010-8224-5510"),
    ]
    for uname, name, phone in worker_core:
        u, created = User.objects.get_or_create(username=uname)
        if created or not u.has_usable_password():
            u.set_password("worker1234!")
        u.name = name
        u.user_type = "worker"
        u.department = dept_map["DEPT_010"]
        u.position = "사원"
        u.phone = phone
        u.email = f"{uname}@icmp.co.kr"
        u.save()

    print("  [accounts] users (worker_006~105)...")
    BULK_USERS = [
        ("W006","박서연",11,"010-5251-5704","safe","worker_006","박서연","admin","차장","worker_006@icmp.co.kr",1),
        ("W007","권지유",4,"010-5253-6380","warning","worker_007","권지유","worker","대리","worker_007@icmp.co.kr",0),
        ("W008","한지민",2,"010-7336-7970","danger","worker_008","한지민","worker","사원","worker_008@icmp.co.kr",0),
        ("W009","권민재",3,"010-9605-9661","danger","worker_009","권민재","worker","대리","worker_009@icmp.co.kr",0),
        ("W010","김지아",4,"010-5833-5004","safe","worker_010","김지아","worker","대리","worker_010@icmp.co.kr",0),
        ("W011","서현우",1,"010-5885-8320","danger","worker_011","서현우","worker","대리","worker_011@icmp.co.kr",0),
        ("W012","서민준",3,"010-4909-5016","safe","worker_012","서민준","manager","과장","worker_012@icmp.co.kr",1),
        ("W013","서채원",12,"010-7651-6223","safe","worker_013","서채원","worker","사원","worker_013@icmp.co.kr",0),
        ("W014","서현우",12,"010-8842-1034","safe","worker_014","서현우","worker","사원","worker_014@icmp.co.kr",0),
        ("W015","김도윤",4,"010-1131-4005","safe","worker_015","김도윤","worker","사원","worker_015@icmp.co.kr",0),
        ("W016","오채원",7,"010-6127-1873","safe","worker_016","오채원","admin","차장","worker_016@icmp.co.kr",1),
        ("W017","정지유",13,"010-6381-7355","safe","worker_017","정지유","worker","사원","worker_017@icmp.co.kr",0),
        ("W018","이서윤",1,"010-8571-3707","safe","worker_018","이서윤","worker","대리","worker_018@icmp.co.kr",0),
        ("W019","오민준",1,"010-5825-9702","safe","worker_019","오민준","admin","차장","worker_019@icmp.co.kr",1),
        ("W020","김하은",2,"010-3545-8398","safe","worker_020","김하은","worker","사원","worker_020@icmp.co.kr",0),
        ("W021","신예준",3,"010-3421-7061","safe","worker_021","신예준","worker","사원","worker_021@icmp.co.kr",0),
        ("W022","오지아",6,"010-6396-4120","safe","worker_022","오지아","admin","차장","worker_022@icmp.co.kr",1),
        ("W023","임채원",3,"010-7403-9647","safe","worker_023","임채원","worker","사원","worker_023@icmp.co.kr",0),
        ("W024","오예준",7,"010-9316-5732","safe","worker_024","오예준","worker","사원","worker_024@icmp.co.kr",0),
        ("W025","김수아",7,"010-1111-6008","safe","worker_025","김수아","worker","사원","worker_025@icmp.co.kr",0),
        ("W026","황예준",5,"010-4212-2279","safe","worker_026","황예준","worker","사원","worker_026@icmp.co.kr",0),
        ("W027","이민지",13,"010-4289-9183","safe","worker_027","이민지","worker","사원","worker_027@icmp.co.kr",0),
        ("W028","이도윤",8,"010-2764-7960","safe","worker_028","이도윤","worker","사원","worker_028@icmp.co.kr",0),
        ("W029","황준혁",6,"010-3501-8736","safe","worker_029","황준혁","worker","대리","worker_029@icmp.co.kr",0),
        ("W030","임예린",1,"010-4408-8619","safe","worker_030","임예린","worker","사원","worker_030@icmp.co.kr",0),
        ("W031","신준혁",9,"010-6573-4398","safe","worker_031","신준혁","worker","대리","worker_031@icmp.co.kr",0),
        ("W032","김예린",11,"010-5003-2481","safe","worker_032","김예린","worker","사원","worker_032@icmp.co.kr",0),
        ("W033","강민준",4,"010-2785-7893","safe","worker_033","강민준","worker","사원","worker_033@icmp.co.kr",0),
        ("W034","박예준",5,"010-4636-8218","safe","worker_034","박예준","worker","사원","worker_034@icmp.co.kr",0),
        ("W035","정민지",13,"010-9217-5038","safe","worker_035","정민지","worker","사원","worker_035@icmp.co.kr",0),
        ("W036","한하은",8,"010-3924-4972","safe","worker_036","한하은","worker","사원","worker_036@icmp.co.kr",0),
        ("W037","이준혁",12,"010-6498-2847","safe","worker_037","이준혁","worker","대리","worker_037@icmp.co.kr",0),
        ("W038","김지우",2,"010-7324-6593","safe","worker_038","김지우","worker","사원","worker_038@icmp.co.kr",0),
        ("W039","조현준",9,"010-8612-3471","safe","worker_039","조현준","worker","사원","worker_039@icmp.co.kr",0),
        ("W040","최예린",10,"010-9183-7264","safe","worker_040","최예린","worker","사원","worker_040@icmp.co.kr",0),
        ("W041","권민재",5,"010-3647-8192","safe","worker_041","권민재","worker","사원","worker_041@icmp.co.kr",0),
        ("W042","박하은",7,"010-7293-4861","safe","worker_042","박하은","worker","사원","worker_042@icmp.co.kr",0),
        ("W043","이서연",11,"010-4821-6374","safe","worker_043","이서연","worker","사원","worker_043@icmp.co.kr",0),
        ("W044","강지우",13,"010-6147-2983","safe","worker_044","강지우","worker","사원","worker_044@icmp.co.kr",0),
        ("W045","조서연",4,"010-8392-1647","safe","worker_045","조서연","worker","사원","worker_045@icmp.co.kr",0),
        ("W046","한준혁",3,"010-2748-9316","safe","worker_046","한준혁","worker","대리","worker_046@icmp.co.kr",0),
        ("W047","정예준",6,"010-5163-4827","safe","worker_047","정예준","worker","사원","worker_047@icmp.co.kr",0),
        ("W048","신지아",8,"010-9274-3618","safe","worker_048","신지아","worker","사원","worker_048@icmp.co.kr",0),
        ("W049","임민준",1,"010-3816-7243","safe","worker_049","임민준","worker","사원","worker_049@icmp.co.kr",0),
        ("W050","오지우",2,"010-7429-1836","safe","worker_050","오지우","worker","사원","worker_050@icmp.co.kr",0),
        ("W051","황채원",5,"010-4873-2961","safe","worker_051","황채원","worker","사원","worker_051@icmp.co.kr",0),
        ("W052","김민재",9,"010-6312-8497","safe","worker_052","김민재","worker","사원","worker_052@icmp.co.kr",0),
        ("W053","이하은",11,"010-8147-3629","safe","worker_053","이하은","worker","사원","worker_053@icmp.co.kr",0),
        ("W054","박채원",13,"010-2963-7148","safe","worker_054","박채원","worker","사원","worker_054@icmp.co.kr",0),
        ("W055","강예준",7,"010-7381-4926","safe","worker_055","강예준","worker","사원","worker_055@icmp.co.kr",0),
        ("W056","조민재",4,"010-4926-8371","safe","worker_056","조민재","worker","사원","worker_056@icmp.co.kr",0),
        ("W057","한예린",10,"010-9147-2836","safe","worker_057","한예린","worker","사원","worker_057@icmp.co.kr",0),
        ("W058","정서연",3,"010-3618-7492","safe","worker_058","정서연","worker","사원","worker_058@icmp.co.kr",0),
        ("W059","신민지",6,"010-7263-4918","safe","worker_059","신민지","worker","사원","worker_059@icmp.co.kr",0),
        ("W060","임준혁",12,"010-4891-3726","safe","worker_060","임준혁","worker","대리","worker_060@icmp.co.kr",0),
        ("W061","오예린",2,"010-8374-1629","safe","worker_061","오예린","worker","사원","worker_061@icmp.co.kr",0),
        ("W062","황지우",5,"010-2916-8347","safe","worker_062","황지우","worker","사원","worker_062@icmp.co.kr",0),
        ("W063","김준혁",9,"010-6483-2917","safe","worker_063","김준혁","worker","사원","worker_063@icmp.co.kr",0),
        ("W064","이채원",11,"010-9128-4763","safe","worker_064","이채원","worker","사원","worker_064@icmp.co.kr",0),
        ("W065","박민지",13,"010-3742-9186","safe","worker_065","박민지","worker","사원","worker_065@icmp.co.kr",0),
        ("W066","강서연",7,"010-8169-3274","safe","worker_066","강서연","worker","사원","worker_066@icmp.co.kr",0),
        ("W067","조예준",4,"010-2847-6193","safe","worker_067","조예준","worker","사원","worker_067@icmp.co.kr",0),
        ("W068","한하은",10,"010-6391-8274","safe","worker_068","한하은","worker","사원","worker_068@icmp.co.kr",0),
        ("W069","정민준",3,"010-9248-1736","safe","worker_069","정민준","worker","사원","worker_069@icmp.co.kr",0),
        ("W070","신지우",6,"010-4827-9163","safe","worker_070","신지우","worker","사원","worker_070@icmp.co.kr",0),
        ("W071","임채원",8,"010-7193-2864","safe","worker_071","임채원","worker","사원","worker_071@icmp.co.kr",0),
        ("W072","오예린",1,"010-3674-8129","safe","worker_072","오예린","worker","사원","worker_072@icmp.co.kr",0),
        ("W073","황민재",5,"010-8417-2693","safe","worker_073","황민재","worker","사원","worker_073@icmp.co.kr",0),
        ("W074","김서연",9,"010-2738-6491","safe","worker_074","김서연","worker","사원","worker_074@icmp.co.kr",0),
        ("W075","이예준",11,"010-6182-3947","safe","worker_075","이예준","worker","사원","worker_075@icmp.co.kr",0),
        ("W076","박지우",13,"010-9164-2783","safe","worker_076","박지우","worker","사원","worker_076@icmp.co.kr",0),
        ("W077","강하은",7,"010-3826-7194","safe","worker_077","강하은","worker","사원","worker_077@icmp.co.kr",0),
        ("W078","조채원",4,"010-7491-2638","safe","worker_078","조채원","worker","사원","worker_078@icmp.co.kr",0),
        ("W079","한민지",10,"010-2864-9173","safe","worker_079","한민지","worker","사원","worker_079@icmp.co.kr",0),
        ("W080","정준혁",3,"010-6739-1842","safe","worker_080","정준혁","worker","대리","worker_080@icmp.co.kr",0),
        ("W081","신서연",6,"010-4218-7396","safe","worker_081","신서연","worker","사원","worker_081@icmp.co.kr",0),
        ("W082","임예린",8,"010-9347-2618","safe","worker_082","임예린","worker","사원","worker_082@icmp.co.kr",0),
        ("W083","오지우",1,"010-3826-7491","safe","worker_083","오지우","worker","사원","worker_083@icmp.co.kr",0),
        ("W084","황민준",5,"010-7194-3826","safe","worker_084","황민준","worker","사원","worker_084@icmp.co.kr",0),
        ("W085","김채원",9,"010-2638-9174","safe","worker_085","김채원","worker","사원","worker_085@icmp.co.kr",0),
        ("W086","이서윤",11,"010-6473-2918","safe","worker_086","이서윤","worker","사원","worker_086@icmp.co.kr",0),
        ("W087","박예준",13,"010-9182-7364","safe","worker_087","박예준","worker","사원","worker_087@icmp.co.kr",0),
        ("W088","강민지",7,"010-3927-1648","safe","worker_088","강민지","worker","사원","worker_088@icmp.co.kr",0),
        ("W089","조하은",4,"010-7164-2839","safe","worker_089","조하은","worker","사원","worker_089@icmp.co.kr",0),
        ("W090","한지우",10,"010-2849-3617","safe","worker_090","한지우","worker","사원","worker_090@icmp.co.kr",0),
        ("W091","정채원",3,"010-6391-7482","safe","worker_091","정채원","worker","사원","worker_091@icmp.co.kr",0),
        ("W092","신예준",6,"010-4837-2691","safe","worker_092","신예준","worker","사원","worker_092@icmp.co.kr",0),
        ("W093","임민재",8,"010-9263-1748","safe","worker_093","임민재","worker","사원","worker_093@icmp.co.kr",0),
        ("W094","오서연",1,"010-3174-9628","safe","worker_094","오서연","worker","사원","worker_094@icmp.co.kr",0),
        ("W095","황준혁",5,"010-7438-2916","safe","worker_095","황준혁","worker","대리","worker_095@icmp.co.kr",0),
        ("W096","김하은",9,"010-2691-8347","safe","worker_096","김하은","worker","사원","worker_096@icmp.co.kr",0),
        ("W097","이민지",11,"010-6814-3729","safe","worker_097","이민지","worker","사원","worker_097@icmp.co.kr",0),
        ("W098","박지아",13,"010-9472-1638","safe","worker_098","박지아","worker","사원","worker_098@icmp.co.kr",0),
        ("W099","강예린",7,"010-3618-7294","safe","worker_099","강예린","worker","사원","worker_099@icmp.co.kr",0),
        ("W100","조서윤",4,"010-7283-9164","safe","worker_100","조서윤","worker","사원","worker_100@icmp.co.kr",0),
        ("W101","한채원",10,"010-2916-8473","safe","worker_101","한채원","worker","사원","worker_101@icmp.co.kr",0),
        ("W102","정민재",3,"010-3748-1926","safe","worker_102","정민재","worker","사원","worker_102@icmp.co.kr",0),
        ("W103","신지아",6,"010-7162-3894","safe","worker_103","신지아","worker","사원","worker_103@icmp.co.kr",0),
        ("W104","임채원",12,"010-4923-7816","safe","worker_104","임채원","worker","사원","worker_104@icmp.co.kr",0),
        ("W105","오예린",2,"010-8347-2961","safe","worker_105","오예린","worker","사원","worker_105@icmp.co.kr",0),
    ]

    # dept_id → Department 객체 매핑 (코드 기반)
    dept_by_id = {i + 1: dept_map[f"DEPT_{i+1:03d}"] for i in range(13)}

    for row in BULK_USERS:
        (worker_no, worker_name, dept_id, phone, safety_status,
         uname, uname2, user_type, position, email, is_staff) = row
        u, created = User.objects.get_or_create(username=uname)
        if created or not u.has_usable_password():
            u.set_password("worker1234!")
        u.name = worker_name
        u.user_type = user_type
        u.department = dept_by_id[dept_id]
        u.position = position
        u.phone = phone
        u.email = email
        u.is_staff = bool(is_staff)
        u.save()

    print("  [accounts] ✓ done")


def seed_facilities():
    """facilities, buildings, floors, floor_grids, index_grids, zones, geofences,
       equipments, location_nodes"""
    from facilities.models import (
        Facility, Building, Floor, FloorGrid, IndexGrid,
        Zone, Geofence, Equipment, LocationNode,
    )

    print("  [facilities] facilities...")
    fac_data = [
        ("FAC-001", "제1공장"),
        ("FAC-002", "제2공장"),
        ("FAC-003", "창고동"),
    ]
    fac_map = {}
    for code, name in fac_data:
        fac, _ = Facility.objects.get_or_create(
            facility_code=code,
            defaults={"facility_name": name, "status": "active"},  # ✅ [수정 1] facility_name
        )
        fac_map[code] = fac

    print("  [facilities] buildings...")
    bld_data = [
        ("B01", "제1공장 본관", "FAC-001"),
        ("B01", "제2공장 본관", "FAC-002"),
        ("B01", "창고동 본관",  "FAC-003"),
    ]
    bld_map = {}
    for code, name, fac_code in bld_data:
        bld, _ = Building.objects.get_or_create(
            building_code=code,
            facility=fac_map[fac_code],
            defaults={"building_name": name},
        )
        bld_map[(code, fac_code)] = bld

    print("  [facilities] floors & floor_grids...")
    bld1 = bld_map[("B01", "FAC-001")]
    floor1, _ = Floor.objects.get_or_create(
        building=bld1,
        floor_no=1,
        defaults={
            "floor_name": "1층",
            "width": 50,
            "length": 30,
            "height": 4,
        },
    )
    FloorGrid.objects.get_or_create(
        floor=floor1,
        defaults={"cell_size": 1.0},
    )

    # ─────────────────────────────────────────────────────────
    # ✅ [수정 10] IndexGrid 자동 생성 (1500개 셀)
    # FloorGridService가 floor.width, floor.length, cell_size로 셀 계산
    # 이미지(plan_image)와 무관 — 건물 크기만으로 격자 생성됨
    # ─────────────────────────────────────────────────────────
    if not IndexGrid.objects.filter(floor=floor1).exists():
        from facilities.services.floor_grid_maker import FloorGridService
        from facilities.repositories import IndexGridWriter
        print("  [facilities] index_grids (auto-generate cells)...")
        service = FloorGridService(floor1)
        cells = service.generate_all_cells()
        IndexGridWriter().bulk_create(floor1, cells)
        print(f"  [facilities] {len(cells)}개 셀 생성")
    else:
        print("  [facilities] index_grids 이미 존재 (skip)")

    print("  [facilities] zones...")
    zone1, _ = Zone.objects.get_or_create(
        zone_name="작업구역A",
        floor=floor1,
        defaults={
            "zone_type": "work",
            "cell_row_start": 2,
            "cell_row_end": 8,
            "cell_col_start": 2,
            "cell_col_end": 10,
            "color": "#378ADD",
            "status": "active",
        },
    )

    print("  [facilities] geofences...")
    geofence_data = [
        # name, type, severity, description, is_active, cx, cy, radius, zone
        ("위험구역1",         "circle", "danger",  "",                          True,  25.0, 15.0, 3.0,  None),
        ("[자동] 가스센서-A", "circle", "danger",  "가스센서 자동 생성 — device_id=1", False, 10.0,  5.0, 5.0,  None),
        ("[자동] 가스센서-B", "circle", "warning", "가스센서 자동 생성 — device_id=2", True,  25.0,  5.0, 3.0,  None),
        ("[자동] 창고동 가스센서", "circle", "warning", "가스센서 자동 생성 — device_id=7", True, 15.0, 25.0, 3.0, None),
        ("[자동] 가스센서-C", "circle", "danger",  "가스센서 자동 생성 — device_id=3", True,  40.0, 15.0, 5.0,  None),
    ]
    for name, gtype, severity, desc, is_active, cx, cy, radius, zone in geofence_data:
        Geofence.objects.get_or_create(
            name=name,
            floor=floor1,
            defaults={
                "geofence_type": gtype,
                "severity": severity,
                "description": desc,
                "is_active": is_active,
                "center_x": cx,
                "center_y": cy,
                "radius": radius,
                "zone": zone,
            },
        )

    print("  [facilities] equipments...")
    eq_data = [
        ("EQ-001", "압축기-A", 2.0, 2.0, 15.0, 15.0),
        ("EQ-002", "펌프-A",   1.5, 1.5, 30.0, 15.0),
        ("EQ-003", "탱크-A",   3.0, 3.0, 40.0, 20.0),
    ]
    for code, name, w, h, x, y in eq_data:
        Equipment.objects.get_or_create(
            equipment_code=code,
            defaults={
                "equipment_name": name,
                "width": w,
                "height": h,
                "center_x": x,         # ✅ [수정 2] position_x → center_x
                "center_y": y,         # ✅ [수정 2] position_y → center_y
                "status": "active",
                "floor": floor1,
                "is_placed": True,     # ✅ [수정 2] 시드 데이터는 배치 완료 상태
                # building 인자 삭제 — Equipment 모델에 없는 필드
            },
        )

    print("  [facilities] location_nodes...")
    ln_data = [
        ("LN-001", "위치노드-A",  5.0,  5.0),
        ("LN-002", "위치노드-B", 25.0,  5.0),
        ("LN-003", "위치노드-C", 45.0,  5.0),
        ("LN-004", "위치노드-D",  5.0, 25.0),
        ("LN-005", "위치노드-E", 45.0, 25.0),
    ]
    for code, name, x, y in ln_data:
        LocationNode.objects.get_or_create(
            node_code=code,
            defaults={
                "node_name": name,
                "x": x,                # ✅ [수정 3] pos_x → x
                "y": y,                # ✅ [수정 3] pos_y → y
                "z": 0.0,              # ✅ [수정 3] altitude → z
                "status": "active",
                "floor": floor1,
                "is_placed": True,     # T1-α X3: 시드 데이터는 배치 완료 상태
            },
        )

    print("  [facilities] ✓ done")


def seed_workers():
    """workers W001~W105 + initial WorkerLocations + geofence sync"""
    from facilities.models import Worker, WorkerLocation, Floor
    from accounts.models import User, Department

    # ✅ [수정 6] dept_id(정수) → Department 객체 매핑 (코드 기반)
    dept_by_id = {
        i + 1: Department.objects.get(code=f"DEPT_{i+1:03d}")
        for i in range(13)
    }

    print("  [workers] W001~W005 (on_duty)...")
    w_on = [
        ("W001", "김철수", 10, "010-7425-1251", "worker1"),
        ("W002", "이영희", 10, "010-6631-6561", "worker_002"),
        ("W003", "박민준", 10, "010-4359-5031", "worker_003"),
        ("W004", "최수진", 10, "010-2109-9189", "worker_004"),
        ("W005", "정도현", 10, "010-8224-5510", "worker_005"),
    ]
    for worker_no, name, dept_id, phone, uname in w_on:
        user = User.objects.filter(username=uname).first()
        Worker.objects.get_or_create(
            worker_no=worker_no,
            defaults={
                "worker_name": name,
                "department": dept_by_id[dept_id],   # ✅ [수정 6] FK 객체
                "phone": phone,
                "current_state": "on_duty",
                "safety_status": "safe",
                "user": user,
            },
        )

    print("  [workers] W006~W105 (off_duty)...")
    BULK = [
        ("W006","박서연",11,"010-5251-5704","safe","worker_006"),
        ("W007","권지유",4,"010-5253-6380","warning","worker_007"),
        ("W008","한지민",2,"010-7336-7970","danger","worker_008"),
        ("W009","권민재",3,"010-9605-9661","danger","worker_009"),
        ("W010","김지아",4,"010-5833-5004","safe","worker_010"),
        ("W011","서현우",1,"010-5885-8320","danger","worker_011"),
        ("W012","서민준",3,"010-4909-5016","safe","worker_012"),
        ("W013","서채원",12,"010-7651-6223","safe","worker_013"),
        ("W014","서현우",12,"010-8842-1034","safe","worker_014"),
        ("W015","김도윤",4,"010-1131-4005","safe","worker_015"),
        ("W016","오채원",7,"010-6127-1873","safe","worker_016"),
        ("W017","정지유",13,"010-6381-7355","safe","worker_017"),
        ("W018","이서윤",1,"010-8571-3707","safe","worker_018"),
        ("W019","오민준",1,"010-5825-9702","safe","worker_019"),
        ("W020","김하은",2,"010-3545-8398","safe","worker_020"),
        ("W021","신예준",3,"010-3421-7061","safe","worker_021"),
        ("W022","오지아",6,"010-6396-4120","safe","worker_022"),
        ("W023","임채원",3,"010-7403-9647","safe","worker_023"),
        ("W024","오예준",7,"010-9316-5732","safe","worker_024"),
        ("W025","김수아",7,"010-1111-6008","safe","worker_025"),
        ("W026","황예준",5,"010-4212-2279","safe","worker_026"),
        ("W027","이민지",13,"010-4289-9183","safe","worker_027"),
        ("W028","이도윤",8,"010-2764-7960","safe","worker_028"),
        ("W029","황준혁",6,"010-3501-8736","safe","worker_029"),
        ("W030","임예린",1,"010-4408-8619","safe","worker_030"),
        ("W031","신준혁",9,"010-6573-4398","safe","worker_031"),
        ("W032","김예린",11,"010-5003-2481","safe","worker_032"),
        ("W033","강민준",4,"010-2785-7893","safe","worker_033"),
        ("W034","박예준",5,"010-4636-8218","safe","worker_034"),
        ("W035","정민지",13,"010-9217-5038","safe","worker_035"),
        ("W036","한하은",8,"010-3924-4972","safe","worker_036"),
        ("W037","이준혁",12,"010-6498-2847","safe","worker_037"),
        ("W038","김지우",2,"010-7324-6593","safe","worker_038"),
        ("W039","조현준",9,"010-8612-3471","safe","worker_039"),
        ("W040","최예린",10,"010-9183-7264","safe","worker_040"),
        ("W041","권민재",5,"010-3647-8192","safe","worker_041"),
        ("W042","박하은",7,"010-7293-4861","safe","worker_042"),
        ("W043","이서연",11,"010-4821-6374","safe","worker_043"),
        ("W044","강지우",13,"010-6147-2983","safe","worker_044"),
        ("W045","조서연",4,"010-8392-1647","safe","worker_045"),
        ("W046","한준혁",3,"010-2748-9316","safe","worker_046"),
        ("W047","정예준",6,"010-5163-4827","safe","worker_047"),
        ("W048","신지아",8,"010-9274-3618","safe","worker_048"),
        ("W049","임민준",1,"010-3816-7243","safe","worker_049"),
        ("W050","오지우",2,"010-7429-1836","safe","worker_050"),
        ("W051","황채원",5,"010-4873-2961","safe","worker_051"),
        ("W052","김민재",9,"010-6312-8497","safe","worker_052"),
        ("W053","이하은",11,"010-8147-3629","safe","worker_053"),
        ("W054","박채원",13,"010-2963-7148","safe","worker_054"),
        ("W055","강예준",7,"010-7381-4926","safe","worker_055"),
        ("W056","조민재",4,"010-4926-8371","safe","worker_056"),
        ("W057","한예린",10,"010-9147-2836","safe","worker_057"),
        ("W058","정서연",3,"010-3618-7492","safe","worker_058"),
        ("W059","신민지",6,"010-7263-4918","safe","worker_059"),
        ("W060","임준혁",12,"010-4891-3726","safe","worker_060"),
        ("W061","오예린",2,"010-8374-1629","safe","worker_061"),
        ("W062","황지우",5,"010-2916-8347","safe","worker_062"),
        ("W063","김준혁",9,"010-6483-2917","safe","worker_063"),
        ("W064","이채원",11,"010-9128-4763","safe","worker_064"),
        ("W065","박민지",13,"010-3742-9186","safe","worker_065"),
        ("W066","강서연",7,"010-8169-3274","safe","worker_066"),
        ("W067","조예준",4,"010-2847-6193","safe","worker_067"),
        ("W068","한하은",10,"010-6391-8274","safe","worker_068"),
        ("W069","정민준",3,"010-9248-1736","safe","worker_069"),
        ("W070","신지우",6,"010-4827-9163","safe","worker_070"),
        ("W071","임채원",8,"010-7193-2864","safe","worker_071"),
        ("W072","오예린",1,"010-3674-8129","safe","worker_072"),
        ("W073","황민재",5,"010-8417-2693","safe","worker_073"),
        ("W074","김서연",9,"010-2738-6491","safe","worker_074"),
        ("W075","이예준",11,"010-6182-3947","safe","worker_075"),
        ("W076","박지우",13,"010-9164-2783","safe","worker_076"),
        ("W077","강하은",7,"010-3826-7194","safe","worker_077"),
        ("W078","조채원",4,"010-7491-2638","safe","worker_078"),
        ("W079","한민지",10,"010-2864-9173","safe","worker_079"),
        ("W080","정준혁",3,"010-6739-1842","safe","worker_080"),
        ("W081","신서연",6,"010-4218-7396","safe","worker_081"),
        ("W082","임예린",8,"010-9347-2618","safe","worker_082"),
        ("W083","오지우",1,"010-3826-7491","safe","worker_083"),
        ("W084","황민준",5,"010-7194-3826","safe","worker_084"),
        ("W085","김채원",9,"010-2638-9174","safe","worker_085"),
        ("W086","이서윤",11,"010-6473-2918","safe","worker_086"),
        ("W087","박예준",13,"010-9182-7364","safe","worker_087"),
        ("W088","강민지",7,"010-3927-1648","safe","worker_088"),
        ("W089","조하은",4,"010-7164-2839","safe","worker_089"),
        ("W090","한지우",10,"010-2849-3617","safe","worker_090"),
        ("W091","정채원",3,"010-6391-7482","safe","worker_091"),
        ("W092","신예준",6,"010-4837-2691","safe","worker_092"),
        ("W093","임민재",8,"010-9263-1748","safe","worker_093"),
        ("W094","오서연",1,"010-3174-9628","safe","worker_094"),
        ("W095","황준혁",5,"010-7438-2916","safe","worker_095"),
        ("W096","김하은",9,"010-2691-8347","safe","worker_096"),
        ("W097","이민지",11,"010-6814-3729","safe","worker_097"),
        ("W098","박지아",13,"010-9472-1638","safe","worker_098"),
        ("W099","강예린",7,"010-3618-7294","safe","worker_099"),
        ("W100","조서윤",4,"010-7283-9164","safe","worker_100"),
        ("W101","한채원",10,"010-2916-8473","safe","worker_101"),
        ("W102","정민재",3,"010-3748-1926","safe","worker_102"),
        ("W103","신지아",6,"010-7162-3894","safe","worker_103"),
        ("W104","임채원",12,"010-4923-7816","safe","worker_104"),
        ("W105","오예린",2,"010-8347-2961","safe","worker_105"),
    ]
    for row in BULK:
        worker_no, name, dept_id, phone, safety, uname = row
        user = User.objects.filter(username=uname).first()
        Worker.objects.get_or_create(
            worker_no=worker_no,
            defaults={
                "worker_name": name,
                "department": dept_by_id[dept_id],   # ✅ [수정 6] FK 객체
                "phone": phone,
                "current_state": "off_duty",
                "safety_status": safety,
                "user": user,
            },
        )

    # ─────────────────────────────────────────────────────────
    # ✅ [수정 8] WorkerLocation (W001~W005 초기 위치 + geofence 자동 판정)
    # ─────────────────────────────────────────────────────────
    print("  [workers] worker_locations (initial)...")

    # floor1 조회 (seed_facilities에서 생성한 제1공장 본관 1층)
    floor1 = (Floor.objects
              .filter(building__facility__facility_code="FAC-001",
                      building__building_code="B01",
                      floor_no=1)
              .first())

    if floor1 is None:
        print("    skip — floor1 없음 (seed_facilities 먼저 실행 필요)")
    else:
        try:
            from facilities.services.geofence_checker import sync_worker_status
        except ImportError as exc:
            print(f"    warn — geofence_checker import 실패: {exc}")
            sync_worker_status = None

        # 5명을 다양한 위치에 배치 (W005는 위험구역1 내부)
        initial_locations = [
            ("W001",  5.0, 15.0),
            ("W002", 20.0, 10.0),
            ("W003", 30.0, 20.0),
            ("W004", 35.0, 15.0),
            ("W005", 25.0, 14.0),   # 위험구역1(25,15,R=3) 내부 → danger 판정
        ]

        for worker_no, x, y in initial_locations:
            worker = Worker.objects.filter(worker_no=worker_no).first()
            if not worker:
                print(f"    skip {worker_no} — Worker 없음")
                continue

            # 같은 작업자의 시드 위치가 이미 있으면 건너뜀 (중복 방지)
            if WorkerLocation.objects.filter(worker=worker).exists():
                print(f"    skip {worker_no} — WorkerLocation 이미 존재")
                continue

            loc = WorkerLocation.objects.create(
                worker=worker,
                floor=floor1,
                x=x,
                y=y,
                cell_no=f"{int(y)}-{int(x)}",
            )
            # geofence 자동 판정 → Worker.safety_status 갱신
            if sync_worker_status:
                try:
                    sync_worker_status(worker, loc)
                except Exception as exc:
                    print(f"    warn {worker_no} — sync_worker_status 실패: {exc}")

    print("  [workers] ✓ done")


def seed_monitoring():
    """devices, device_channels, threshold_policies, sensor_locations"""
    from monitoring.models import (
        Device, DeviceChannel, ThresholdPolicy,
    )
    from facilities.models import Facility, Building, Floor, SensorLocation

    fac1 = Facility.objects.get(facility_code="FAC-001")
    fac2 = Facility.objects.get(facility_code="FAC-002")
    fac3 = Facility.objects.get(facility_code="FAC-003")
    # ✅ [수정 5] building_code 명시 — MultipleObjectsReturned 위험 제거
    bld1 = Building.objects.get(facility=fac1, building_code="B01")
    bld2 = Building.objects.get(facility=fac2, building_code="B01")
    bld3 = Building.objects.get(facility=fac3, building_code="B01")
    floor1 = Floor.objects.get(building=bld1, floor_no=1)

    print("  [monitoring] devices...")
    device_data = [
        # uid, code, type, name, port, facility, building, floor
        ("GAS-001","GAS-001","gas","가스센서-A",  502, fac1, bld1, floor1),
        ("GAS-002","GAS-002","gas","가스센서-B",  502, fac1, bld1, floor1),
        ("GAS-003","GAS-003","gas","가스센서-C",  502, fac2, bld2, None),
        ("PWR-001","PWR-001","power","전력계-A",  502, fac1, bld1, floor1),
        ("PWR-002","PWR-002","power","전력계-B",  502, fac2, bld2, None),
        ("PWR-003","PWR-003","power","전력계-C",  502, fac3, bld3, None),
        ("GAS-004","GAS-004","gas","창고동 가스센서", 8084, fac3, None, None),
    ]
    device_map = {}
    for uid, code, dtype, name, port, fac, bld, flr in device_data:
        dev, _ = Device.objects.get_or_create(
            device_uid=uid,
            defaults={
                "device_code": code,
                "device_type": dtype,
                "device_name": name,
                "port": port,
                "is_active": True,
                "status": "active",
                "software_version": "",
                "model_name": "",
                "note": "",
                "facility": fac,
                "building": bld,
                "floor": flr,
            },
        )
        device_map[uid] = dev

    print("  [monitoring] device_channels...")
    pwr1_channels = [
        ("slave01", "압연기 A",      800),
        ("slave02", "압연기 B",      800),
        ("slave11", "CCTV 1번",       50),
        ("slave12", "CCTV 2번",       50),
        ("slave21", "냉각팬 A",      500),
        ("slave22", "냉각팬 B",      500),
        ("slave31", "조명 A구역",    300),
        ("slave32", "조명 B구역",    300),
        ("slave41", "컨베이어 A",    600),
        ("slave42", "컨베이어 B",    600),
        ("slave51", "환기팬 A",      400),
        ("slave52", "환기팬 B",      400),
        ("slave61", "충전스테이션 A", 1000),
        ("slave62", "충전스테이션 B", 1000),
        ("slave71", "비상조명",      100),
        ("slave72", "안전장치 전원", 200),
    ]
    for code, name, rated in pwr1_channels:
        DeviceChannel.objects.get_or_create(
            device=device_map["PWR-001"],
            channel_code=code,
            defaults={
                "channel_name": name,
                "is_active": True,
                "status": "active",
                "rated_power_w": rated,
            },
        )

    pwr2_channels = [
        ("slave01", "도장 로봇 A",   900),
        ("slave02", "도장 로봇 B",   900),
        ("slave11", "CCTV 3번",       50),
        ("slave12", "CCTV 4번",       50),
        ("slave21", "집진기 A",      700),
        ("slave22", "집진기 B",      700),
        ("slave31", "조명 C구역",    300),
        ("slave32", "조명 D구역",    300),
    ]
    for code, name, rated in pwr2_channels:
        DeviceChannel.objects.get_or_create(
            device=device_map["PWR-002"],
            channel_code=code,
            defaults={
                "channel_name": name,
                "is_active": True,
                "status": "active",
                "rated_power_w": rated,
            },
        )

    print("  [monitoring] threshold_policies...")
    threshold_data = [
        # metric_code, normal_min, normal_max, warning_min, warning_max, danger_min, danger_max, action_type
        ("co",            None, None, None, 25.0,   None, 200.0,  "alert"),
        ("h2s",           None, None, None, 10.0,   None,  15.0,  "alert"),
        ("current_value", None, None, None, 80.0,   None, 100.0,  "alert"),
        ("power_value",   None, None, None, 90.0,   None, 110.0,  "alert"),
        ("co2",           None, None, None, 1000.0, None, 5000.0, "alert"),
        ("o2",            18.0, 23.5, 16.0, 18.0,   None,  None,  "alert"),
        ("no2",           None, None, None,  3.0,   None,   5.0,  "alert"),
        ("so2",           None, None, None,  2.0,   None,   5.0,  "alert"),
        ("o3",            None, None, None,  0.06,  None,   0.12, "alert"),
        ("nh3",           None, None, None, 25.0,   None,  35.0,  "alert"),
        ("voc",           None, None, None,  0.5,   None,   1.0,  "alert"),
    ]
    for row in threshold_data:
        (code, nmin, nmax, wmin, wmax, dmin, dmax, action) = row
        ThresholdPolicy.objects.get_or_create(
            metric_code=code,
            defaults={
                "normal_min": nmin,
                "normal_max": nmax,
                "warning_min": wmin,
                "warning_max": wmax,
                "danger_min": dmin,
                "danger_max": dmax,
                "action_type": action,
                "is_active": True,
            },
        )

    print("  [monitoring] sensor_locations...")
    sl_data = [
        ("GAS-001", "gas",   10.0,  5.0, "가스센서-A"),
        ("GAS-002", "gas",   25.0,  5.0, "가스센서-B"),
        ("PWR-001", "power", 10.0, 20.0, "전력계-A"),
        ("GAS-003", "gas",   40.0, 15.0, "가스센서-C"),
        ("GAS-004", "gas",   15.0, 25.0, "창고동 가스센서"),
    ]
    for uid, stype, x, y, name in sl_data:
        dev = device_map.get(uid)
        if dev:
            SensorLocation.objects.get_or_create(
                device_id=dev.id,           # ✅ [수정 4] FK 대신 IntegerField PK
                defaults={
                    "sensor_type": stype,
                    "x": x,                  # ✅ [수정 4] pos_x → x
                    "y": y,                  # ✅ [수정 4] pos_y → y
                    "device_name": name,     # ✅ [수정 4] label → device_name
                    "is_active": True,
                    "floor": floor1,
                    "is_placed": True,       # T1-β Q1: 시드 데이터는 배치 완료 상태
                },
            )

    print("  [monitoring] ✓ done")


def seed_alerts():
    """alarm_rules (기준 룰 6개) + alarm_events (더미 10건) + event_histories"""
    from datetime import timedelta
    from django.utils import timezone
    from alerts.models import AlarmRule, AlarmEvent, EventHistory
    from monitoring.models import ThresholdPolicy, Device
    from facilities.models import Facility, Worker
    from accounts.models import User

    print("  [alerts] alarm_rules...")
    rule_data = [
        ("CO 임계치 초과 규칙",   "threshold", "notify", True,  "co"),
        ("H2S 임계치 초과 규칙",  "threshold", "notify", True,  "h2s"),
        ("전류 임계치 초과 규칙", "threshold", "notify", True,  "current_value"),
        ("전력 이상 감지 규칙",   "power",     "notify", True,  "power_value"),
        ("센서 데이터 누락 규칙", "missing",   "notify", True,  None),
        ("장비 오프라인 감지 규칙","offline",  "notify", True,  None),
    ]
    for name, rtype, action, is_active, tp_code in rule_data:
        tp = None
        if tp_code:
            tp = ThresholdPolicy.objects.filter(metric_code=tp_code).first()
        AlarmRule.objects.get_or_create(
            rule_name=name,
            defaults={
                "rule_type": rtype,
                "action_type": action,
                "is_active": is_active,
                "threshold_policy": tp,
            },
        )

    # ─────────────────────────────────────────────────────────
    # ✅ [수정 7] AlarmEvent (알람 이벤트 더미 10건) + EventHistory
    # ─────────────────────────────────────────────────────────
    print("  [alerts] alarm_events + event_histories...")

    rules = list(AlarmRule.objects.order_by("id"))
    facilities = {
        "FAC-001": Facility.objects.get(facility_code="FAC-001"),
        "FAC-002": Facility.objects.get(facility_code="FAC-002"),
        "FAC-003": Facility.objects.get(facility_code="FAC-003"),
    }
    devices = {
        d.device_uid: d
        for d in Device.objects.filter(device_uid__in=[
            "GAS-001", "GAS-002", "GAS-003", "PWR-001", "PWR-002", "PWR-003"
        ])
    }
    workers = {
        w.worker_no: w
        for w in Worker.objects.filter(worker_no__in=["W001", "W002", "W003", "W004", "W005"])
    }
    admin = User.objects.filter(username="admin").first()

    now = timezone.now()
    # (rule_idx, fac_code, device_uid, worker_no, severity, event_type,
    #  status, hours_ago, title, message)
    event_specs = [
        (0, "FAC-001", "GAS-001", None,   "danger",  "gas",      "open",
         0.5, "CO 농도 위험 수준 초과",
         "제1공장 가스센서-A에서 CO 농도 152ppm 감지. 허용 기준(100ppm) 초과."),

        (1, "FAC-001", "GAS-001", "W003", "warning", "gas",      "acknowledged",
         2,   "H2S 경고 수준 감지",
         "가스센서-A CH2에서 H2S 7.3ppm 감지. 경고 임계치(5ppm) 초과. 작업자 박민준 인근 위치."),

        (3, "FAC-002", "PWR-002", None,   "danger",  "power",    "open",
         1,   "제2공장 전력계 이상",
         "전력계-B에서 순간 과전력 감지. 정격 대비 118% 부하 발생."),

        (4, "FAC-001", "GAS-002", None,   "warning", "device",   "open",
         3,   "가스센서-B 데이터 누락",
         "가스센서-B(GAS-002)에서 5분 이상 데이터 수신 없음."),

        (5, "FAC-003", "PWR-003", None,   "warning", "device",   "acknowledged",
         5,   "창고동 전력계 오프라인",
         "전력계-C(PWR-003)가 오프라인 상태로 전환됨. 네트워크 연결 확인 필요."),

        (2, "FAC-001", "PWR-001", None,   "normal",  "power",    "closed",
         24,  "전류 임계치 경고",
         "전력계-A 전류값 83A 감지. 경고 임계치(80A) 소폭 초과. 이후 정상 복귀."),

        (0, "FAC-002", "GAS-003", "W001", "danger",  "gas",      "open",
         0.2, "CO 긴급 경보",
         "제2공장 가스센서-C에서 CO 농도 210ppm 감지. 즉각 대피 조치 필요."),

        (1, "FAC-001", "GAS-001", "W004", "warning", "gas",      "open",
         4,   "H2S 주의 수준 감지",
         "가스센서-A에서 H2S 3.1ppm 감지. 주의 단계. 환기 실시 권고."),

        (5, "FAC-001", "GAS-001", None,   "warning", "device",   "open",
         6,   "가스센서-A 간헐적 오프라인",
         "가스센서-A(GAS-001)가 주기적으로 응답 없음. 펌웨어 점검 필요."),

        (3, "FAC-003", "PWR-003", "W005", "normal",  "power",    "closed",
         48,  "창고동 전력 미세 이상",
         "전력계-C에서 미세 전압 변동 감지. 조치 후 정상 복귀."),
    ]

    for spec in event_specs:
        (ri, fac_code, dev_uid, w_no, severity, etype, status,
         hours_ago, title, msg) = spec

        rule = rules[ri] if ri < len(rules) else None
        facility = facilities.get(fac_code)
        device = devices.get(dev_uid) if dev_uid else None
        worker = workers.get(w_no) if w_no else None

        if rule is None or facility is None:
            print(f"    skip event '{title}' — rule/facility 없음")
            continue

        occurred_at = now - timedelta(hours=hours_ago)
        acknowledged_at = (now - timedelta(hours=hours_ago - 0.3)
                           if status in ("acknowledged", "closed") else None)
        closed_at = (now - timedelta(hours=hours_ago - 1)
                     if status == "closed" else None)

        ev, created = AlarmEvent.objects.get_or_create(
            title=title,
            defaults={
                "rule": rule,
                "facility": facility,
                "device": device,
                "worker": worker,
                "severity": severity,
                "event_type": etype,
                "event_status": status,
                "message": msg,
                "occurred_at": occurred_at,
                "acknowledged_by": admin if status in ("acknowledged", "closed") else None,
                "acknowledged_at": acknowledged_at,
                "closed_at": closed_at,
            },
        )

        if status in ("acknowledged", "closed"):
            EventHistory.objects.get_or_create(
                alarm_event=ev,
                action_type="acknowledge",
                defaults={
                    "action_by": admin,
                    "action_note": "현장 확인 후 조치 착수",
                },
            )
        if status == "closed":
            EventHistory.objects.get_or_create(
                alarm_event=ev,
                action_type="close",
                defaults={
                    "action_by": admin,
                    "action_note": "조치 완료 및 정상 복귀 확인",
                },
            )

    print("  [alerts] ✓ done")


def seed_safety():
    """safety_check_items — JSON fixture 로드"""
    import os
    from django.core.management import call_command

    fixture_paths = [
        "safety/fixtures/safety_check_items.json",
        "fixtures/safety_check_items.json",
    ]
    loaded = False
    for path in fixture_paths:
        if os.path.exists(path):
            print(f"  [safety] loading fixture: {path}")
            call_command("loaddata", path, verbosity=0)
            loaded = True
            break

    if not loaded:
        print("  [safety] fixture not found — skipping (run `loaddata` manually)")

    print("  [safety] ✓ done")


# ─────────────────────────────────────────────────────────────
# Management Command
# ─────────────────────────────────────────────────────────────

def seed_alarm_policies():
    """AlarmPolicy 기본 6개 정책 (이벤트 유형별 1개)"""
    from manager.models import AlarmPolicy

    defaults = [
        ("가스 경보 알림",               "가스 경보",                   "앱, 관제 실시간 알림", "관리자, 작업자", True,
         "전체 가스 센서 중 위험 상태를 1분 이상 유지한 장비가 발생하면 알림을 발송합니다.",
         "가스 경보 발생",
         "{이벤트상세}가 발생했습니다. 발생 장비: {발생대상}, 상태: {상태}, 발생 시각: {발생시각}."),

        ("전력 이상 알림",               "전력 이상",                   "앱",                  "관리자",         True,
         "전체 전력 설비 중 위험 상태로 전환된 장비가 발생하면 즉시 알림을 발송합니다.",
         "전력 이상 감지",
         "{이벤트상세}가 발생했습니다. 발생 장비: {발생대상}, 상태: {상태}, 발생 시각: {발생시각}."),

        ("위험구역 진입 알림",           "위험구역 진입",               "관제 실시간 알림",     "관리자, 작업자", True,
         "구역 단계가 위험구역인 위험구역 A에 작업자가 진입하면 관리자, 작업자에게 즉시 알림을 발송합니다.",
         "위험구역 진입 감지",
         "구역 단계가 위험구역인 {발생대상}에 작업자가 진입하였습니다. 발생 시각: {발생시각}."),

        ("PPE 미착용 경고 알림",         "PPE 미착용",                  "앱",                  "작업자",         True,
         "전체 작업자 위치 데이터 발생 후 5분 이내 PPE가 미착용 상태이면 즉시 알림을 발송합니다.",
         "PPE 미착용 감지",
         "{발생대상}의 PPE 미착용이 감지되었습니다. 발생 시각: {발생시각}."),

        ("체크리스트 미완료 알림",       "작업 안전 체크리스트 미완료", "관제 실시간 알림",     "관리자",         False,
         "전체 작업자 위치 데이터 발생 후 5분 이내 작업 안전 체크리스트가 미완료 상태이면 즉시 알림을 발송합니다.",
         "체크리스트 미완료",
         "{발생대상}의 작업 안전 체크리스트가 미완료 상태입니다. 발생 시각: {발생시각}."),

        ("VR 교육 미이수 알림",          "VR 교육 미이수",              "관제 실시간 알림",     "관리자",         True,
         "전체 작업자 위치 데이터 발생 후 5분 이내 VR 교육이 미이수 상태이면 즉시 알림을 발송합니다.",
         "VR 교육 미이수",
         "{발생대상}의 VR 교육이 미이수 상태입니다. 발생 시각: {발생시각}."),
    ]

    policy_map = {}
    for name, event, channels, targets, is_active, cond, title, content in defaults:
        p, _ = AlarmPolicy.objects.get_or_create(
            name=name,
            defaults={
                "event_type":        event,
                "channels":          channels,
                "targets":           targets,
                "is_active":         is_active,
                "condition_summary": cond,
                "alarm_title":       title,
                "alarm_content":     content,
            },
        )
        policy_map[name] = p

    print(f"  [alarm_policies] {len(policy_map)}개 정책 생성/확인")
    return policy_map


def seed_send_history():
    """AlarmSendHistory 샘플 발송 이력 — AlarmPolicy FK 연결"""
    from datetime import timedelta
    from django.utils import timezone
    from manager.models import AlarmSendHistory

    AlarmSendHistory.objects.all().delete()   # 기존 데이터 초기화 후 재생성

    # 연결할 정책 맵 확보 (없으면 생성)
    policy_map = seed_alarm_policies()

    now = timezone.now()

    # (hours_ago, channel, targets, result, policy_name, scope, content, reason)
    rows = [
        (0.04, "SMS",         "관리자",            "성공", "가스 경보 알림",         "관리자",
         "가스 센서 GS-021에서 경고 상태가 감지되었습니다. 관리자 역할에 SMS 알림이 즉시 발송되었습니다.",
         "통신사 응답 코드 200을 수신했고 추가 재시도는 발생하지 않았습니다."),

        (0.10, "이메일",      "관리자, 슈퍼관리자", "실패", "전력 이상 알림",         "관리자, 슈퍼관리자",
         "스마트전력시스템 SP-004 이상 감지에 따른 이메일 알림 발송이 실패하였습니다.",
         "이메일 서버 네트워크 연결 오류로 인해 발송에 실패하였습니다. 재발송 처리가 필요합니다."),

        (0.22, "앱 푸시",     "작업자",            "성공", "위험구역 진입 알림",     "작업자",
         "위치 노드 LN-014 관할 구역에서 작업자 위치 이탈이 감지되어 작업자 앱 푸시 알림을 발송하였습니다.",
         "앱 서버 응답 코드 200 수신. 정상 발송 완료되었습니다."),

        (0.35, "SMS",         "작업자, 관리자",     "성공", "PPE 미착용 경고 알림",   "작업자, 관리자",
         "PPE 미착용 경고 알림을 작업자 및 관리자에게 SMS로 발송하였습니다.",
         "통신사 응답 코드 200을 수신했고 추가 재시도는 발생하지 않았습니다."),

        (0.48, "이메일",      "슈퍼관리자",         "지연", "VR 교육 미이수 알림",    "슈퍼관리자",
         "VR 교육 미이수 현황 알림 이메일 발송이 정상 처리되었으나 전송 지연이 발생하였습니다.",
         "발송 서버 처리 부하로 인해 예정 시간 대비 약 12분 전송 지연이 발생하였습니다."),

        (0.57, "앱 푸시",     "관리자",            "성공", "위험구역 진입 알림",     "관리자",
         "출입문 A-03에서 제한 시간 내 접근 경보가 감지되어 관리자에게 앱 푸시 알림을 발송하였습니다.",
         "앱 서버 응답 코드 200 수신. 정상 발송 완료되었습니다."),

        (0.72, "SMS",         "관리자, 작업자",     "성공", "가스 경보 알림",         "관리자, 작업자",
         "가스 센서 GS-007 경보 상태가 해제되어 관리자 및 작업자에게 SMS 해제 알림을 발송하였습니다.",
         "통신사 응답 코드 200을 수신했고 추가 재시도는 발생하지 않았습니다."),

        (0.84, "이메일",      "슈퍼관리자",         "성공", "VR 교육 미이수 알림",    "슈퍼관리자",
         "일간 시스템 운영 리포트를 슈퍼관리자에게 이메일로 발송하였습니다.",
         "이메일 서버 응답 코드 250 수신. 정상 발송 완료되었습니다."),

        (1.02, "앱 푸시",     "작업자",            "실패", "PPE 미착용 경고 알림",   "작업자",
         "PPE 미착용 경고 알림을 작업자 앱으로 발송하려 했으나 실패하였습니다.",
         "수신 작업자 디바이스 토큰 만료로 인해 앱 푸시 발송에 실패하였습니다. 토큰 갱신 후 재발송이 필요합니다."),

        (1.17, "SMS",         "관리자",            "지연", "전력 이상 알림",         "관리자",
         "스마트전력시스템 SP-002 전력 이상 주의 알림을 관리자에게 SMS로 발송 요청하였으나 전송이 지연되었습니다.",
         "SMS 게이트웨이 트래픽 집중으로 인해 약 8분 전송 지연이 발생하였습니다."),

        (1.32, "앱 푸시",     "작업자, 관리자",     "성공", "위험구역 진입 알림",     "작업자, 관리자",
         "출입문 B-01 접근 이벤트 경보 알림을 작업자 및 관리자에게 앱 푸시로 발송하였습니다.",
         "앱 서버 응답 코드 200 수신. 정상 발송 완료되었습니다."),

        (1.49, "이메일",      "슈퍼관리자",         "성공", "체크리스트 미완료 알림", "슈퍼관리자",
         "작업 안전 체크리스트 미완료 현황 리포트를 슈퍼관리자에게 이메일로 발송하였습니다.",
         "이메일 서버 응답 코드 250 수신. 정상 발송 완료되었습니다."),
    ]

    objs = [
        AlarmSendHistory(
            sent_at      = now - timedelta(hours=h),
            channel      = channel,
            targets      = targets,
            result       = result,
            alarm_policy = policy_map.get(policy_name),
            policy_name  = policy_name,
            scope        = scope,
            content      = content,
            reason       = reason,
        )
        for h, channel, targets, result, policy_name, scope, content, reason in rows
    ]
    AlarmSendHistory.objects.bulk_create(objs)
    print(f"  [send_history] {len(objs)}건 생성 완료 (AlarmPolicy FK 연결)")


SECTIONS = {
    "accounts":       seed_accounts,
    "facilities":     seed_facilities,
    "workers":        seed_workers,
    "monitoring":     seed_monitoring,
    "alerts":         seed_alerts,
    "safety":         seed_safety,
    "alarm_policies": seed_alarm_policies,
    "send_history":   seed_send_history,
}

# 의존성 순서
ALL_ORDER = [
    "accounts", "facilities", "workers", "monitoring",
    "alerts", "safety", "alarm_policies", "send_history",
]

def seed_common_codes():
    """공통 코드 그룹 7개 및 코드값 초기 데이터"""
    from core.models import CommonCode

    groups = [
        {
            "group_code": "DEVICE_TYPE",
            "code_name": "장비 유형",
            "scope": "장비 등록 / 센서 연동",
            "description": "현장에서 운영되는 장비의 유형을 분류합니다.",
            "codes": [
                ("GAS_SENSOR",    "유해가스 센서",     10),
                ("SMART_POWER",   "스마트 전력 시스템", 20),
                ("LOCATION_NODE", "위치 노드",         30),
                ("LEGACY_SENSOR", "레거시 센서",        99),
            ],
        },
        {
            "group_code": "COMM_METHOD",
            "code_name": "통신 방식",
            "scope": "장비 등록 / 센서 연동",
            "description": "장비와 서버 간 데이터 통신 방식을 구분합니다.",
            "codes": [
                ("MQTT",    "MQTT",    10),
                ("HTTP",    "HTTP",    20),
                ("RS485",   "RS-485",  30),
                ("MODBUS",  "Modbus",  40),
            ],
        },
        {
            "group_code": "GAS_TYPE",
            "code_name": "가스 종류",
            "scope": "센서 연동 / 임계치 설정",
            "description": "유해가스 감지 센서가 측정하는 가스 종류를 분류합니다.",
            "codes": [
                ("CO",  "일산화탄소 (CO)",  10),
                ("H2S", "황화수소 (H₂S)",   20),
                ("CO2", "이산화탄소 (CO₂)", 30),
                ("O2",  "산소 (O₂)",        40),
                ("NO2", "이산화질소 (NO₂)", 50),
                ("CH4", "메탄 (CH₄)",       60),
                ("NH3", "암모니아 (NH₃)",   70),
                ("VOC", "휘발성유기화합물 (VOC)", 80),
            ],
        },
        {
            "group_code": "UNIT_CODE",
            "code_name": "측정 단위",
            "scope": "센서 연동 / 임계치 설정",
            "description": "센서 측정값의 단위를 정의합니다.",
            "codes": [
                ("PPM",  "ppm",   10),
                ("PCT",  "%",     20),
                ("PCT_LEL", "%LEL", 30),
                ("V",    "V",     40),
                ("A",    "A",     50),
                ("KW",   "kW",    60),
                ("KWH",  "kWh",   70),
            ],
        },
        {
            "group_code": "EVENT_TYPE",
            "code_name": "이벤트 구분",
            "scope": "알람 / 이벤트 관리",
            "description": "시스템에서 발생하는 이벤트의 유형을 구분합니다.",
            "codes": [
                ("THRESHOLD", "임계치 초과", 10),
                ("MISSING",   "데이터 누락", 20),
                ("OFFLINE",   "장비 오프라인", 30),
                ("POWER",     "전력 이상",   40),
                ("GEOFENCE",  "지오펜스 침범", 50),
            ],
        },
        {
            "group_code": "NOTI_CHANNEL",
            "code_name": "알림 채널",
            "scope": "알람 정책 관리",
            "description": "알람 발생 시 알림을 전송하는 채널을 정의합니다.",
            "codes": [
                ("EMAIL", "이메일",   10),
                ("SMS",   "문자(SMS)", 20),
                ("KAKAO", "카카오톡", 30),
                ("PUSH",  "앱 푸시",  40),
            ],
        },
        {
            "group_code": "WORK_TYPE",
            "code_name": "작업 유형",
            "scope": "작업자 관리 / 안전 확인",
            "description": "현장 작업자의 작업 유형을 구분합니다.",
            "codes": [
                ("INSPECTION",  "점검",   10),
                ("MAINTENANCE", "유지보수", 20),
                ("OPERATION",   "운전",   30),
                ("EMERGENCY",   "긴급",   40),
            ],
        },
    ]

    print("  [common_codes] 공통 코드 그룹 7개...")
    for g in groups:
        meta, _ = CommonCode.objects.get_or_create(
            group_code=g["group_code"], code="__meta__",
            defaults={
                "code_name":   g["code_name"],
                "sort_order":  0,
                "is_active":   True,
                "scope":       g["scope"],
                "description": g["description"],
                "updated_by":  "시스템",
            },
        )
        for code_val, code_name, sort_order in g["codes"]:
            CommonCode.objects.get_or_create(
                group_code=g["group_code"], code=code_val,
                defaults={
                    "code_name":  code_name,
                    "sort_order": sort_order,
                    "is_active":  True,
                    "updated_by": "시스템",
                },
            )
    total = CommonCode.objects.exclude(code="__meta__").count()
    print(f"  완료: 그룹 {len(groups)}개, 코드값 총 {total}개")


def seed_risk_codes():
    """위험 유형 분류 그룹 및 위험 유형 초기 데이터"""
    from core.models import CommonCode

    groups = [
        {
            "group_code": "RISK_GAS",
            "code_name": "유해가스",
            "scope": "위험구역,이벤트,알림",
            "description": "유해가스 누출 및 농도 초과와 관련된 위험 유형입니다.",
            "codes": [
                ("GAS_LEAK",     "가스 누출",       True,  10),
                ("GAS_HIGH",     "고농도 가스 감지", True,  20),
                ("GAS_SENSOR_FAIL", "가스 센서 오류", False, 30),
            ],
        },
        {
            "group_code": "RISK_POWER",
            "code_name": "전력 이상",
            "scope": "이벤트,알림",
            "description": "전력 과부하, 누전 등 전력 관련 위험 유형입니다.",
            "codes": [
                ("POWER_OVERLOAD", "전력 과부하",  True,  10),
                ("POWER_OUTAGE",   "전력 차단",    True,  20),
                ("POWER_LEAK",     "누전 감지",    True,  30),
            ],
        },
        {
            "group_code": "RISK_LOCATION",
            "code_name": "위치 이탈",
            "scope": "위험구역,알림",
            "description": "작업자의 허가 구역 이탈 및 위험 구역 진입 위험 유형입니다.",
            "codes": [
                ("LOCATION_OUT",   "허가구역 이탈", True,  10),
                ("LOCATION_ENTER", "위험구역 진입", True,  20),
                ("LOCATION_LOST",  "위치 신호 유실", False, 30),
            ],
        },
        {
            "group_code": "RISK_WORK",
            "code_name": "작업 위험",
            "scope": "이벤트,알림",
            "description": "고소 작업, 밀폐 공간 등 작업 환경에 따른 위험 유형입니다.",
            "codes": [
                ("FALL_RISK",      "추락 위험",    True,  10),
                ("CONFINED_SPACE", "밀폐 공간 작업", True,  20),
                ("HEAVY_EQUIP",    "중장비 근접",  True,  30),
            ],
        },
        {
            "group_code": "RISK_COMPLEX",
            "code_name": "복합 위험",
            "scope": "위험구역,이벤트,알림",
            "description": "가스 누출과 위치 이탈 등 복합 조건이 충족된 위험 유형입니다.",
            "codes": [
                ("COMPLEX_GAS_LOC", "가스+위치 복합", True,  10),
                ("COMPLEX_MULTI",   "다중 센서 복합", True,  20),
            ],
        },
        {
            "group_code": "RISK_SYSTEM",
            "code_name": "시스템 이상",
            "scope": "이벤트",
            "description": "장비 오프라인, 통신 단절 등 시스템 이상 위험 유형입니다.",
            "codes": [
                ("DEVICE_OFFLINE", "장비 오프라인", False, 10),
                ("COMM_LOST",      "통신 단절",    False, 20),
                ("DATA_MISSING",   "데이터 누락",  False, 30),
            ],
        },
        {
            "group_code": "RISK_COMMON",
            "code_name": "공통 위험",
            "scope": "위험구역,이벤트,알림",
            "description": "특정 유형에 속하지 않는 일반적인 현장 위험 유형입니다.",
            "codes": [
                ("GENERAL_RISK", "일반 위험", True,  10),
                ("UNKNOWN",      "미분류 위험", False, 99),
            ],
        },
    ]

    print("  [risk_codes] 위험 유형 분류 그룹 7개...")
    for g in groups:
        CommonCode.objects.get_or_create(
            group_code=g["group_code"], code="__meta__",
            defaults={
                "code_name":   g["code_name"],
                "sort_order":  0,
                "is_active":   True,
                "scope":       g["scope"],
                "description": g["description"],
                "updated_by":  "시스템",
            },
        )
        for code_val, code_name, map_reflect, sort_order in g["codes"]:
            CommonCode.objects.get_or_create(
                group_code=g["group_code"], code=code_val,
                defaults={
                    "code_name":   code_name,
                    "sort_order":  sort_order,
                    "is_active":   True,
                    "map_reflect": map_reflect,
                    "updated_by":  "시스템",
                },
            )
    print(f"  완료: 위험 분류 그룹 {len(groups)}개 seeded")


SECTIONS = {
    "accounts":      seed_accounts,
    "facilities":    seed_facilities,
    "workers":       seed_workers,
    "monitoring":    seed_monitoring,
    "alerts":        seed_alerts,
    "safety":        seed_safety,
    "common_codes":  seed_common_codes,
    "risk_codes":    seed_risk_codes,
}

# 의존성 순서
ALL_ORDER = ["accounts", "facilities", "workers", "monitoring", "alerts", "safety", "common_codes", "risk_codes"]

class Command(BaseCommand):
    help = "ICMP2 통합 시드: 기준 데이터를 DB에 삽입합니다"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="시드 대상 테이블을 초기화한 후 삽입합니다 (주의: 모든 데이터 삭제)",
        )
        parser.add_argument(
            "--section",
            choices=list(SECTIONS.keys()),
            default=None,
            help="특정 섹션만 실행합니다",
        )

    def handle(self, *args, **options):
        flush = options["flush"]
        section = options["section"]

        if flush:
            self._flush()

        targets = [section] if section else ALL_ORDER

        self.stdout.write(self.style.MIGRATE_HEADING("=== ICMP2 Seed ==="))
        with transaction.atomic():
            for sec in targets:
                self.stdout.write(f"▶ {sec}")
                try:
                    SECTIONS[sec]()
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"  ✗ {sec}: {exc}"))
                    raise

        self.stdout.write(self.style.SUCCESS("✓ 시드 완료"))

    def _flush(self):
        """시드 대상 테이블 순서대로 초기화 (FK 순서 역방향)"""
        flush_tables = [
            # alerts
            "event_histories",
            "notifications",
            "alarm_events",
            "alarm_rules",
            # monitoring
            "action_logs",
            "inspection_logs",
            "device_channels",
            "sensor_locations",
            "devices",
            "threshold_policies",
            # facilities
            "location_nodes",
            "equipments",
            "geofences",
            "zones",
            "index_grids",
            "floor_grids",
            "floors",
            "buildings",
            "worker_locations",
            "workers",
            "facilities",
            # safety
            "safety_check_item_results",
            "safety_check_sessions",
            "safety_check_items",
            # accounts
            "users",
            "departments",
        ]
        self.stdout.write(self.style.WARNING("! --flush: 테이블 초기화 중..."))
        with connection.cursor() as cur:
            for tbl in flush_tables:
                try:
                    cur.execute(f'DELETE FROM "{tbl}";')
                    self.stdout.write(f"  cleared {tbl}")
                except Exception as e:
                    self.stdout.write(f"  skip {tbl}: {e}")