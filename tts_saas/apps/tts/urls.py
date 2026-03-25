from django.urls import path
from . import views

app_name = 'tts'

urlpatterns = [
    path('', views.index, name='index'),
    path('generate/', views.generate_audio_api, name='generate_api'),
    path('history/', views.history_view, name='history'),
    path('delete-voice/<int:sample_id>/', views.delete_voice_sample, name='delete_voice'),
]