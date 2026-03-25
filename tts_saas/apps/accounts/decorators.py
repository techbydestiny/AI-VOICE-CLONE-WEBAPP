from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def anonymous_required(view_func):
    """Decorator to ensure user is not authenticated"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.info(request, 'You are already logged in.')
            return redirect('tts:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def check_generation_limit(view_func):
    """Decorator to check if user can generate audio"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            profile = request.user.profile
            if not profile.can_generate():
                messages.error(request, 'You have reached your generation limit. Please upgrade to continue.')
                return redirect('accounts:subscribe')
        return view_func(request, *args, **kwargs)
    return _wrapped_view