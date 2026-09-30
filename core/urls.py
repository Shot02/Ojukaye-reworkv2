from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search_view, name='search'),
    path('search/suggestions/', views.search_suggestions, name='search_suggestions'),
    path('newsletter/signup/', views.newsletter_signup, name='newsletter_signup'),

    path('manage/', views.admin_dashboard, name='admin_dashboard'),
    path('manage/posts/', views.admin_posts, name='admin_posts'),
    path('manage/posts/bulk-action/', views.admin_bulk_action, name='admin_bulk_action'),
    path('manage/posts/<int:post_id>/run-ai/', views.admin_run_ai_single, name='admin_run_ai_single'),
    path('manage/posts/<int:post_id>/set-verification/', views.admin_set_verification_status, name='admin_set_verification_status'),
    path('manage/posts/<int:post_id>/toggle-banner/', views.admin_toggle_banner, name='admin_toggle_banner'),
    path('manage/posts/<int:post_id>/toggle-featured/', views.admin_toggle_featured, name='admin_toggle_featured'),

    path('manage/fetch/', views.admin_quick_fetch, name='admin_quick_fetch'),
    path('manage/fetch/run/', views.admin_run_fetch, name='admin_run_fetch'),

    path('manage/scheduler/status/', views.admin_scheduler_status, name='admin_scheduler_status'),
    path('manage/scheduler/update/', views.admin_scheduler_update, name='admin_scheduler_update'),
    path('manage/scheduler/toggle/', views.admin_scheduler_toggle, name='admin_scheduler_toggle'),
    path('manage/scheduler/run-now/', views.admin_scheduler_run_now, name='admin_scheduler_run_now'),

    path('manage/sources/', views.admin_sources, name='admin_sources'),
    path('manage/sources/add/', views.admin_source_add, name='admin_source_add'),
    path('manage/sources/<int:source_id>/test/', views.admin_source_test, name='admin_source_test'),
    path('manage/sources/<int:source_id>/toggle/', views.admin_source_toggle, name='admin_source_toggle'),
    path('manage/sources/<int:source_id>/delete/', views.admin_source_delete, name='admin_source_delete'),
    path('manage/sources/test-all/', views.admin_source_test_all, name='admin_source_test_all'),
    path('manage/sources/discover/', views.admin_source_discover, name='admin_source_discover'),
    path('manage/sources/seed-defaults/', views.admin_source_seed_defaults, name='admin_source_seed_defaults'),

    path('manage/subscribers/', views.admin_subscribers, name='admin_subscribers'),
    path('manage/settings/', views.admin_settings, name='admin_settings'),
    
    path('manage/ads/', views.admin_ads, name='admin_ads'),
    path('manage/ads/create/', views.admin_ad_create, name='admin_ad_create'),
    path('manage/ads/<int:ad_id>/', views.admin_ad_detail, name='admin_ad_detail'),
    path('manage/ads/<int:ad_id>/toggle/', views.admin_ad_toggle, name='admin_ad_toggle'),
    path('manage/ads/<int:ad_id>/delete/', views.admin_ad_delete, name='admin_ad_delete'),

    path('api/track-ad-impression/<uuid:ad_id>/', views.track_ad_impression, name='track_ad_impression'),
    path('api/track-ad-click/<uuid:ad_id>/', views.track_ad_click, name='track_ad_click'),
    
    path('about/', views.about_page, name='about'),
    path('contact/', views.contact_page, name='contact'),
    path('help/', views.help_page, name='help_center'),
    path('privacy/', views.privacy_page, name='privacy'),
    path('terms/', views.terms_page, name='terms'),
]