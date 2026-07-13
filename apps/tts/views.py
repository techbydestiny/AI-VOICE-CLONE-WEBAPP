from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse
import torch
from TTS.api import TTS
import os
import uuid
from ..accounts.models import VoiceSample, GenerationHistory

device = "cuda" if torch.cuda.is_available() else "cpu"
tts_model = None

def get_tts_model():
    global tts_model
    if tts_model is None:
        try:
            tts_model = TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2').to(device)
        except Exception as e:
            print(f"Error loading TTS model: {e}")
            tts_model = None
    return tts_model

def index(request):
    """Main TTS page"""
    context = {
        'free_limit': getattr(settings, 'FREE_TIER_LIMIT', 1),  # 1 for non-logged in
        'basic_limit': getattr(settings, 'BASIC_TIER_LIMIT', 4),  # 4 for logged in free users
        'premium_price': getattr(settings, 'PREMIUM_PRICE_NGN', 5000),  # ₦5,000 for premium
    }
    
    if request.user.is_authenticated:
        try:
            # Try to get the profile
            profile = request.user.profile
            context['generations_used'] = profile.generations_used
            context['generations_limit'] = profile.generations_limit
            context['subscription_tier'] = profile.subscription_tier
            context['voice_samples'] = VoiceSample.objects.filter(user=request.user)
        except Exception as e:
            # If profile doesn't exist, create one with basic tier (4 generations)
            from ..accounts.models import UserProfile
            profile = UserProfile.objects.create(
                user=request.user,
                subscription_tier='basic',
                generations_limit=4
            )
            context['generations_used'] = 0
            context['generations_limit'] = 4
            context['subscription_tier'] = 'basic'
            context['voice_samples'] = []
            print(f"Created missing profile for user: {request.user.username}")
    
    return render(request, 'tts/index.html', context)

def generate_audio_api(request):
    """API endpoint for audio generation"""
    import traceback
    
    print(f"=== GENERATE API CALLED ===")
    print(f"Method: {request.method}")
    
    # Only accept POST requests
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed. Use POST.'}, status=405)
    
    # Get text from request
    text = request.POST.get('text', '')
    voice_file = request.FILES.get('voice_sample')
    
    print(f"Text received: {text[:50] if text else 'No text'}")
    print(f"Voice file: {voice_file}")
    
    if not text:
        return JsonResponse({'error': 'Text is required'}, status=400)
    
    # Handle non-logged in users (1 generation free)
    if not request.user.is_authenticated:
        print("User is not authenticated")
        # Check session-based limit for anonymous users
        if not request.session.session_key:
            request.session.create()
        
        generations = request.session.get('generations', 0)
        free_limit = getattr(settings, 'FREE_TIER_LIMIT', 1)
        
        print(f"Session generations: {generations}, Free limit: {free_limit}")
        
        if generations >= free_limit:
            return JsonResponse({
                'error': 'free_limit_reached',
                'message': 'You have used your free generation. Please login or subscribe to continue.'
            }, status=403)
    
    # Handle logged in users (4 generations per month, or unlimited for premium)
    else:
        print(f"User: {request.user.username}")
        try:
            # Try to get the profile
            profile = request.user.profile
            print(f"Profile found: {profile.subscription_tier}, Used: {profile.generations_used}, Limit: {profile.generations_limit}")
        except:
            # Create profile if it doesn't exist - give them basic tier (4 generations)
            from ..accounts.models import UserProfile
            profile = UserProfile.objects.create(
                user=request.user,
                subscription_tier='basic',
                generations_limit=4
            )
            print(f"Created new profile for {request.user.username}")
        
        if not profile.can_generate():
            return JsonResponse({
                'error': 'limit_reached',
                'message': f'You have reached your monthly limit of {profile.generations_limit} generations. Please upgrade to premium for unlimited access.',
            }, status=403)
    
    # Save voice sample if provided
    voice_sample = None
    if voice_file and request.user.is_authenticated:
        from ..accounts.models import VoiceSample
        print(f"Saving voice sample: {voice_file.name}")
        voice_sample = VoiceSample.objects.create(
            user=request.user,
            audio_file=voice_file,
            name=voice_file.name
        )
        print(f"Voice sample saved with ID: {voice_sample.id}")
    
    # Generate audio
    try:
        # Create output directory if it doesn't exist
        output_dir = os.path.join(settings.MEDIA_ROOT, 'outputs')
        os.makedirs(output_dir, exist_ok=True)
        print(f"Output directory: {output_dir}")
        
        output_filename = f"{uuid.uuid4()}.wav"
        output_path = os.path.join(output_dir, output_filename)
        print(f"Output path: {output_path}")
        
        tts = get_tts_model()
        print(f"TTS model loaded: {tts is not None}")
        
        if tts is None:
            return JsonResponse({'error': 'TTS model not available'}, status=500)
        
        # Use uploaded voice or default voice from media folder
        if voice_sample and voice_sample.audio_file:
            speaker_wav = [voice_sample.audio_file.path]
            print(f"Using uploaded voice: {speaker_wav}")
        else:
            # Check if default voice exists in media folder (simple.wav)
            default_voice = os.path.join(settings.MEDIA_ROOT, 'simple.wav')
            print(f"Looking for default voice at: {default_voice}")
            
            if os.path.exists(default_voice):
                speaker_wav = [default_voice]
                print(f"Using default voice: {default_voice}")
            else:
                # If no default voice, return error
                error_msg = 'No voice sample provided and no default voice available. Please upload a voice sample.'
                print(error_msg)
                return JsonResponse({'error': error_msg}, status=400)
        
        print(f"Generating TTS with text length: {len(text)}")
        tts.tts_to_file(
            text=text,
            file_path=output_path,
            speaker_wav=speaker_wav,
            language="en",
            split_sentences=True
        )
        print(f"TTS generation complete, file size: {os.path.getsize(output_path) if os.path.exists(output_path) else 'file not found'}")
        
        # Update generation count
        if request.user.is_authenticated:
            profile.increment_generations()
            print(f"Incremented generations for user, now at: {profile.generations_used}")
            
            # Save to history
            from ..accounts.models import GenerationHistory
            history = GenerationHistory.objects.create(
                user=request.user,
                text=text,
                voice_sample=voice_sample,
                output_file=f'outputs/{output_filename}'
            )
            print(f"Saved to history with ID: {history.id}")
            
            generations_left = profile.generations_limit - profile.generations_used
        else:
            # Update session count
            request.session['generations'] = request.session.get('generations', 0) + 1
            free_limit = getattr(settings, 'FREE_TIER_LIMIT', 1)
            generations_left = free_limit - request.session.get('generations', 0)
            print(f"Updated session generations, now at: {request.session.get('generations')}")
        
        # Return the file URL
        file_url = f"{settings.MEDIA_URL}outputs/{output_filename}"
        absolute_url = request.build_absolute_uri(file_url)
        print(f"File URL: {absolute_url}")
        
        return JsonResponse({
            'success': True,
            'audio_url': absolute_url,
            'generations_left': generations_left
        })
        
    except Exception as e:
        print(f"ERROR in generate_audio_api: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)
    
@login_required
def history_view(request):
    """View generation history"""
    generations = GenerationHistory.objects.filter(user=request.user)
    return render(request, 'tts/history.html', {'generations': generations})

@login_required
def delete_voice_sample(request, sample_id):
    """Delete a voice sample"""
    try:
        sample = VoiceSample.objects.get(id=sample_id, user=request.user)
        sample.delete()
        messages.success(request, 'Voice sample deleted successfully.')
    except VoiceSample.DoesNotExist:
        messages.error(request, 'Voice sample not found.')
    
    return redirect('tts:index')