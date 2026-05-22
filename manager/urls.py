from django.urls import path
from . import views

urlpatterns = [
    # 사용자 관리
    path('', views.user_list, name='user_list'),
    path('create/', views.user_create, name='user_create'),
    path('check-username/', views.check_username, name='check_username'),
    path('bulk-delete/', views.user_bulk_delete, name='user_bulk_delete'),
    path('bulk-lock/', views.user_bulk_lock, name='user_bulk_lock'),
    path('bulk-unlock/', views.user_bulk_unlock, name='user_bulk_unlock'),
    path('create/error/', views.user_create_error, name='user_create_error'),
    path('detail/', views.user_detail, name='user_detail'),
    path('<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('logout/complete/', views.logout_complete, name='logout_complete'),
    path('filter/', views.user_list_filter, name='user_list_filter'),
    # 직위 관리
    path('positions/', views.position_list, name='position_list'),
    path('positions/create/', views.position_create, name='position_create'),
    path('positions/bulk-delete/', views.position_bulk_delete, name='position_bulk_delete'),
    path('positions/<int:pk>/edit/', views.position_edit, name='position_edit'),

    # 조직 관리
    path('organizations/', views.org_list, name='org_list'),
    path('organizations/all/api/', views.org_all_api, name='org_all_api'),
    path('organizations/add-members/', views.org_add_members, name='org_add_members'),
    path('organizations/exclude-members/', views.org_exclude_members, name='org_exclude_members'),
    path('organizations/appoint-leader/', views.org_appoint_leader, name='org_appoint_leader'),
    path('organizations/revoke-leader/', views.org_revoke_leader, name='org_revoke_leader'),
    path('organizations/<int:pk>/api/', views.org_dept_api, name='org_dept_api'),
    path('organizations/member-select/', views.org_member_select, name='org_member_select'),
    path('organizations/dept-move/', views.org_dept_move, name='org_dept_move'),
    path('organizations/confirm/', views.org_confirm, name='org_confirm'),

    # 공통 코드 관리
    path('codes/', views.code_list, name='code_list'),
    path('codes/group/create/', views.code_group_create, name='code_group_create'),
    path('codes/group/<str:group_code>/edit/', views.code_group_edit, name='code_group_edit'),
    path('codes/value/create/', views.code_value_create, name='code_value_create'),
    path('codes/value/<int:pk>/edit/', views.code_value_edit, name='code_value_edit'),
    path('codes/value/delete/', views.code_value_delete, name='code_value_delete'),

    # 위험 유형 관리
    path('risks/', views.risk_list, name='risk_list'),
    path('risks/create/', views.risk_create, name='risk_create'),
    path('risks/<int:pk>/edit/', views.risk_edit, name='risk_edit'),
    path('risks/group/create/', views.risk_group_create, name='risk_group_create'),
    path('risks/group/<str:group_code>/edit/', views.risk_group_edit, name='risk_group_edit'),
    path('risks/delete/', views.risk_delete, name='risk_delete'),

    # 위험 기준 관리
    path('risk-criteria/', views.risk_criteria_list, name='risk_criteria_list'),
    path('risk-criteria/create/', views.risk_criteria_create, name='risk_criteria_create'),
    path('risk-criteria/<int:pk>/edit/', views.risk_criteria_edit, name='risk_criteria_edit'),
    path('risk-criteria/delete/', views.risk_criteria_delete, name='risk_criteria_delete'),

    # 임계치 기준 관리
    path('thresholds/', views.threshold_list, name='threshold_list'),
    path('thresholds/group/create/', views.threshold_group_create, name='threshold_group_create'),
    path('thresholds/group/<str:cat_code>/edit/', views.threshold_group_edit, name='threshold_group_edit'),
    path('thresholds/create/', views.threshold_create, name='threshold_create'),
    path('thresholds/<int:pk>/edit/', views.threshold_edit, name='threshold_edit'),
    path('thresholds/delete/', views.threshold_delete, name='threshold_delete'),

    # 안전 확인 관리
    path('safety-checklist/', views.safety_checklist_list, name='safety_checklist_list'),
    path('safety-checklist/save/', views.safety_checklist_save, name='safety_checklist_save'),

    # VR 교육 관리
    path('vr-education/', views.vr_education_list, name='vr_education_list'),
    path('vr-education/save/', views.vr_education_save, name='vr_education_save'),

    # 설비 관리
    path('facilities/', views.facility_list, name='facility_list'),
    path('facilities/create/', views.facility_create, name='facility_create'),
    path('facilities/bulk-delete/', views.facility_bulk_delete, name='facility_bulk_delete'),
    path('facilities/<int:pk>/edit/', views.facility_edit, name='facility_edit'),
    path('gas/', views.gas_list, name='gas_list'),
    path('gas/create/', views.gas_create, name='gas_create'),
    path('gas/bulk-delete/', views.gas_bulk_delete, name='gas_bulk_delete'),
    path('gas/<int:pk>/edit/', views.gas_edit, name='gas_edit'),
    path('gas/<int:pk>/inspections/', views.gas_inspections_api, name='gas_inspections_api'),
    path('gas/inspect/create/', views.gas_inspect_create, name='gas_inspect_create'),
    path('gas/inspect/<int:inspection_id>/action/', views.gas_action_create, name='gas_action_create'),
    path('power/', views.power_list, name='power_list'),
    path('power/bulk-delete/', views.power_bulk_delete, name='power_bulk_delete'),
    path('power/inspect/create/', views.power_inspect_create, name='power_inspect_create'),
    path('power/inspect/<int:inspection_id>/action/', views.power_action_create, name='power_action_create'),
    path('power/<int:pk>/edit/', views.power_edit, name='power_edit'),
    path('power/<int:pk>/inspections/', views.power_inspections_api, name='power_inspections_api'),
    path('node/', views.node_list, name='node_list'),
    path('node/bulk-delete/', views.node_bulk_delete, name='node_bulk_delete'),
    path('node/<int:pk>/edit/', views.node_edit, name='node_edit'),
    path('node/<int:pk>/inspections/', views.node_inspections_api, name='node_inspections_api'),
    path('node/inspect/create/', views.node_inspect_create, name='node_inspect_create'),
    path('node/inspect/<int:inspection_id>/action/', views.node_action_create, name='node_action_create'),

    # 데이터 관리
    path('data/gas/', views.gas_data_list, name='gas_data_list'),
    path('data/gas/export/', views.gas_data_export, name='gas_data_export'),
    path('data/power/', views.power_data_list, name='power_data_list'),
    path('data/power/export/', views.power_data_export, name='power_data_export'),
    path('data/node/', views.node_data_list, name='node_data_list'),
    path('data/node/export/', views.node_data_export, name='node_data_export'),
    path('data/worker/', views.worker_data_list, name='worker_data_list'),
    path('data/worker/export/', views.worker_data_export, name='worker_data_export'),
    path('data/retention/', views.retention_list, name='retention_list'),
    path('data/retention/create/', views.retention_create, name='retention_create'),
    path('data/retention/<int:pk>/update/', views.retention_update, name='retention_update'),
    path('data/retention/delete/', views.retention_delete, name='retention_delete'),

    # 공지사항 관리
    path('notice/', views.notice_list, name='notice_list'),
    path('notice/create/', views.notice_create, name='notice_create'),
    path('notice/bulk-delete/', views.notice_bulk_delete, name='notice_bulk_delete'),
    path('notice/attachment/<int:pk>/download/', views.notice_attachment_download, name='notice_attachment_download'),
    path('notice/<int:pk>/', views.notice_detail, name='notice_detail'),
    path('notice/<int:pk>/edit/', views.notice_edit, name='notice_edit'),
    path('notice/<int:pk>/delete/', views.notice_delete, name='notice_delete'),

    # 메뉴 관리
    path('menu-manage/', views.menu_manage, name='menu_manage'),

    # 알림/이벤트 관리
    path('alarm/policy/', views.alarm_policy_list, name='alarm_policy_list'),
    path('alarm/policy/create/', views.alarm_policy_create, name='alarm_policy_create'),
    path('alarm/policy/bulk-delete/', views.alarm_policy_bulk_delete, name='alarm_policy_bulk_delete'),
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
