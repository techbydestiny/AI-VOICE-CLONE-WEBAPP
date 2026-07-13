from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('subscribe/', views.subscribe_view, name='subscribe'),
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('reset-password/<str:token>/', views.password_reset_confirm, name='password_reset_confirm'),
]