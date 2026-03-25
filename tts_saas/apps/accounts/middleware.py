from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages
import uuid

class SingleSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            # Get or create session token
            if not request.session.get('session_token'):
                request.session['session_token'] = str(uuid.uuid4())
            
            # Check if this session is active
            try:
                profile = request.user.profile
                current_token = request.session.get('session_token')
                
                if profile.session_token and profile.session_token != current_token:
                    # Another session is active, logout this one
                    logout(request)
                    messages.warning(request, 'You have been logged out because another session was started.')
                    return redirect('accounts:login')
                elif not profile.session_token:
                    # Set this as the active session
                    profile.session_token = current_token
                    profile.save()
            except:
                # Profile doesn't exist, create it
                from .models import UserProfile
                profile = UserProfile.objects.create(user=request.user)
                profile.session_token = request.session.get('session_token')
                profile.save()
        
        response = self.get_response(request)
        return response