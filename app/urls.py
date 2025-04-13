#app/urls.py
from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('register/', views.registration, name='register'),
    path('', views.user_login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('predict/<str:symbol>/', views.predict_stock, name='predict_stock'),
    path('logout/', views.logout_view, name='logout'),
    path('forecast/', views.forecast_stock, name='forecast_stock'),
    path('company/<str:symbol>/reviews/', views.company_reviews, name='company_reviews'),
    path('company/<str:symbol>/add-review/', views.add_review, name='add_review'),
    path('review/<int:review_id>/delete/', views.delete_review, name='delete_review'),
    # path('admin/companies/', views.admin_manage_companies, name='manage_companies'),
    # path('admin/predictions/', views.admin_view_predictions, name='view_predictions'),
]