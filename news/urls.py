from django.urls import path
from . import views

app_name = 'news'

urlpatterns = [
    path('online-news/', views.online_news, name='online_news'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('category/<slug:slug>/', views.category_view, name='category'),
]