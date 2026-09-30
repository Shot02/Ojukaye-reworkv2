from django.urls import path
from . import views

app_name = 'socialapp'

urlpatterns = [
    path('create/', views.create_post, name='create_post'),

    path('post/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('post/<int:post_id>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),
    path('post/<int:post_id>/comment/', views.add_comment, name='add_comment'),
    path('post/<int:post_id>/share/', views.track_share, name='track_share'),

    path('comment/<int:comment_id>/like/', views.toggle_comment_like, name='toggle_comment_like'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),

    path('notifications/', views.notifications_view, name='notifications'),
    path('notifications/count/', views.notifications_count, name='notifications_count'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/<int:notification_id>/delete/', views.delete_notification, name='delete_notification'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),

    path('saved/', views.saved_posts_view, name='saved_posts'),
]