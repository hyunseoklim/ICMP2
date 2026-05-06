from django.urls import path
from . import views

urlpatterns = [
    # 사용자 관리
    path('', views.user_list, name='user_list'),
    path('create/', views.user_create, name='user_create'),
    path('create/error/', views.user_create_error, name='user_create_error'),
    path('detail/', views.user_detail, name='user_detail'),
    path('edit/', views.user_edit, name='user_edit'),
    path('logout/complete/', views.logout_complete, name='logout_complete'),
    path('filter/', views.user_list_filter, name='user_list_filter'),
    # 직위 관리
    path('positions/', views.position_list, name='position_list'),
    path('positions/create/', views.position_create, name='position_create'),
    path('positions/<int:pk>/edit/', views.position_edit, name='position_edit'),

    # 조직 관리
    path('organizations/', views.org_list, name='org_list'),
    path('organizations/member-select/', views.org_member_select, name='org_member_select'),
    path('organizations/dept-move/', views.org_dept_move, name='org_dept_move'),
    path('organizations/confirm/', views.org_confirm, name='org_confirm'),

    # 공통 코드 관리
    path('codes/', views.code_list, name='code_list'),
    path('codes/group/create/', views.code_group_create, name='code_group_create'),
    path('codes/group/edit/', views.code_group_edit, name='code_group_edit'),
    path('codes/value/create/', views.code_value_create, name='code_value_create'),
    path('codes/value/edit/', views.code_value_edit, name='code_value_edit'),

    # 위험 유형 관리
    path('risks/', views.risk_list, name='risk_list'),
    path('risks/create/', views.risk_create, name='risk_create'),
    path('risks/edit/', views.risk_edit, name='risk_edit'),
    path('risks/group/create/', views.risk_group_create, name='risk_group_create'),
    path('risks/group/edit/', views.risk_group_edit, name='risk_group_edit'),

    # 위험 기준 관리
    path('risk-criteria/', views.risk_criteria_list, name='risk_criteria_list'),

    # 임계치 기준 관리
    path('thresholds/', views.threshold_list, name='threshold_list'),

    # 안전 확인 관리
    path('safety-checklist/', views.safety_checklist_list, name='safety_checklist_list'),

    # VR 교육 관리
    path('vr-education/', views.vr_education_list, name='vr_education_list'),

    # 설비 관리
    path('facilities/', views.facility_list, name='facility_list'),
    path('gas/', views.gas_list, name='gas_list'),
    path('power/', views.power_list, name='power_list'),
    path('node/', views.node_list, name='node_list'),

    # 데이터 관리
    path('data/gas/', views.gas_data_list, name='gas_data_list'),
    path('data/power/', views.power_data_list, name='power_data_list'),
    path('data/node/', views.node_data_list, name='node_data_list'),
    path('data/worker/', views.worker_data_list, name='worker_data_list'),
    path('data/retention/', views.retention_list, name='retention_list'),

    # 공지사항 관리
    path('notice/', views.notice_list, name='notice_list'),
    path('notice/detail/', views.notice_detail, name='notice_detail'),
    path('notice/create/', views.notice_create, name='notice_create'),
    path('notice/edit/', views.notice_edit, name='notice_edit'),

    # 메뉴 관리
    path('menu-manage/', views.menu_manage, name='menu_manage'),

    # 알림/이벤트 관리
    path('alarm/policy/', views.alarm_policy_list, name='alarm_policy_list'),
    path('alarm/event-history/', views.event_history_list, name='event_history_list'),
    path('alarm/send-history/', views.alarm_send_history_list, name='alarm_send_history_list'),

    # 로그 및 연동 관리
    path('log/system/', views.system_log_list, name='system_log_list'),
    path('log/user-activity/', views.user_activity_log_list, name='user_activity_log_list'),
    path('log/integration/', views.integration_log_list, name='integration_log_list'),
    path('log/map-edit/', views.map_edit_log_list, name='map_edit_log_list'),

    # 지도 관리
    path('map/', views.map_editor, name='map_editor'),
]
