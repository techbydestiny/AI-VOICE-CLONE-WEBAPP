from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.urls import reverse_lazy
from django.core.mail import send_mail
from datetime import timedelta
import requests
import json
import uuid
from .forms import UserRegistrationForm, UserLoginForm, CustomPasswordResetForm
from .models import UserProfile, PasswordResetToken
from .decorators import anonymous_required

@anonymous_required
def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('accounts:login')
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})

def verify_email(request, token):
    try:
        profile = UserProfile.objects.get(email_verification_token=token)
        profile.email_verified = True
        profile.email_verification_token = None
        profile.save()
        
        # Activate user
        user = profile.user
        user.is_active = True
        user.save()
        
        messages.success(request, 'Email verified successfully! You can now login.')
    except UserProfile.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
    
    return redirect('accounts:login')

@anonymous_required
def login_view(request):
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                if not user.profile.email_verified:
                    messages.error(request, 'Please verify your email before logging in.')
                    return redirect('accounts:login')
                
                # Clear any existing session for this user
                try:
                    profile = user.profile
                    profile.session_token = None
                    profile.save()
                except:
                    pass
                
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                return redirect('tts:index')
        messages.error(request, 'Invalid username or password.')
    else:
        form = UserLoginForm()
    return render(request, 'accounts/login.html', {'form': form})

@login_required
def logout_view(request):
    try:
        profile = request.user.profile
        profile.session_token = None
        profile.save()
    except:
        pass
    
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('tts:index')

@login_required
def profile_view(request):
    context = {
        'premium_price': getattr(settings, 'PREMIUM_PRICE_NGN', 5000),
    }
    
    try:
        profile = request.user.profile
    except:
        from .models import UserProfile
        profile = UserProfile.objects.create(
            user=request.user,
            subscription_tier='basic',
            generations_limit=4
        )
    
    return render(request, 'accounts/profile.html', context)

def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            # Generate reset token
            token = str(uuid.uuid4())
            reset_token = PasswordResetToken.objects.create(
                user=user,
                token=token
            )
            
            # Send email
            reset_url = f"{settings.BASE_URL}/accounts/reset-password/{token}/"
            send_mail(
                'Password Reset - VoiceClone',
                f'Click this link to reset your password: {reset_url}',
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            messages.success(request, 'Password reset link sent to your email.')
        except User.DoesNotExist:
            messages.error(request, 'No user found with this email.')
        
        return redirect('accounts:login')
    
    return render(request, 'accounts/password_reset.html')

def password_reset_confirm(request, token):
    try:
        reset_token = PasswordResetToken.objects.get(token=token, is_used=False)
        if not reset_token.is_valid():
            messages.error(request, 'This reset link has expired.')
            return redirect('accounts:password_reset')
        
        if request.method == 'POST':
            password = request.POST.get('password')
            confirm_password = request.POST.get('confirm_password')
            
            if password != confirm_password:
                messages.error(request, 'Passwords do not match.')
                return render(request, 'accounts/password_reset_confirm.html', {'token': token})
            
            if len(password) < 8:
                messages.error(request, 'Password must be at least 8 characters.')
                return render(request, 'accounts/password_reset_confirm.html', {'token': token})
            
            # Set new password
            user = reset_token.user
            user.set_password(password)
            user.save()
            
            # Mark token as used
            reset_token.is_used = True
            reset_token.save()
            
            messages.success(request, 'Password reset successful! You can now login.')
            return redirect('accounts:login')
        
    except PasswordResetToken.DoesNotExist:
        messages.error(request, 'Invalid reset link.')
        return redirect('accounts:password_reset')
    
    return render(request, 'accounts/password_reset_confirm.html', {'token': token})

@login_required
def subscribe_view(request):
    try:
        profile = request.user.profile
    except:
        from .models import UserProfile
        profile = UserProfile.objects.create(
            user=request.user,
            subscription_tier='basic',
            generations_limit=4
        )
    
    price = getattr(settings, 'PREMIUM_PRICE_NGN', 5000)
    
    if request.method == 'POST':
        korapay_secret = getattr(settings, 'KORAPAY_SECRET_KEY', '')
        if not korapay_secret:
            # Demo mode
            messages.success(request, 'Demo mode: Subscription activated!')
            profile.subscription_tier = 'premium'
            profile.subscription_expiry = timezone.now() + timedelta(days=30)
            profile.save()
            return redirect('accounts:profile')
        
        # Initialize Korapay transaction
        headers = {
            'Authorization': f'Bearer {korapay_secret}',
            'Content-Type': 'application/json',
        }
        
        reference = f"SUB-{uuid.uuid4().hex[:10].upper()}"
        
        data = {
            'reference': reference,
            'amount': price,
            'currency': 'NGN',
            'redirect_url': request.build_absolute_uri('/accounts/payment/callback/'),
            'customer': {
                'email': request.user.email,
                'name': request.user.get_full_name() or request.user.username
            },
            'metadata': {
                'user_id': request.user.id,
                'subscription_type': 'premium'
            }
        }
        
        try:
            response = requests.post(
                f'{settings.KORAPAY_API_URL}/charges/initialize',
                headers=headers,
                data=json.dumps(data)
            )
            
            if response.status_code == 200:
                result = response.json()
                if result['status']:
                    return redirect(result['data']['checkout_url'])
            messages.error(request, 'Payment initialization failed. Please try again.')
        except Exception as e:
            print(f"Korapay error: {e}")
            messages.error(request, 'Payment service unavailable. Please try again.')
    
    return render(request, 'accounts/subscribe.html', {'price': price})

def payment_callback(request):
    reference = request.GET.get('reference')
    
    if reference:
        korapay_secret = getattr(settings, 'KORAPAY_SECRET_KEY', '')
        
        if korapay_secret:
            headers = {
                'Authorization': f'Bearer {korapay_secret}',
            }
            
            try:
                response = requests.get(
                    f'{settings.KORAPAY_API_URL}/charges/{reference}',
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result['status'] and result['data']['status'] == 'success':
                        user_id = result['data']['metadata']['user_id']
                        try:
                            user = User.objects.get(id=user_id)
                            profile = user.profile
                            profile.subscription_tier = 'premium'
                            profile.subscription_expiry = timezone.now() + timedelta(days=30)
                            profile.save()
                            
                            messages.success(request, 'Payment successful! You now have premium access for 30 days.')
                        except:
                            messages.error(request, 'Error updating subscription.')
            except:
                messages.error(request, 'Error verifying payment.')
        else:
            # Demo mode
            messages.success(request, 'Demo mode: Payment successful!')
    
    return redirect('accounts:profile')