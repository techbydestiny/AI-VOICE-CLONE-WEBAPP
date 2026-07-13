from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import uuid

class UserProfile(models.Model):
    SUBSCRIPTION_TIERS = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    subscription_tier = models.CharField(max_length=20, choices=SUBSCRIPTION_TIERS, default='free')
    generations_used = models.IntegerField(default=0)
    generations_limit = models.IntegerField(default=1)
    subscription_expiry = models.DateTimeField(null=True, blank=True)
    korapay_customer_code = models.CharField(max_length=100, blank=True)
    korapay_subscription_code = models.CharField(max_length=100, blank=True)
    session_token = models.CharField(max_length=100, blank=True, null=True)
    
    # Email verification fields
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def can_generate(self):
        """Check if user can generate more audio"""
        if self.subscription_tier == 'premium':
            if self.subscription_expiry and self.subscription_expiry < timezone.now():
                self.subscription_tier = 'basic'
                self.generations_limit = 4
                self.save()
                return self.generations_used < self.generations_limit
            return True
        
        if self.subscription_tier == 'basic':
            return self.generations_used < self.generations_limit
        
        return self.generations_used < self.generations_limit
    
    def increment_generations(self):
        self.generations_used += 1
        self.save()
    
    def reset_monthly_limit(self):
        if self.subscription_tier == 'basic':
            self.generations_used = 0
            self.save()

class VoiceSample(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='voice_samples')
    audio_file = models.FileField(upload_to='voice_samples/')
    name = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username}'s voice: {self.name}"

class GenerationHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generations')
    text = models.TextField()
    voice_sample = models.ForeignKey(VoiceSample, on_delete=models.SET_NULL, null=True, blank=True)
    output_file = models.FileField(upload_to='outputs/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Generation by {self.user.username} on {self.created_at}"

class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    
    def is_valid(self):
        # Token expires after 24 hours
        return (not self.is_used) and (timezone.now() - self.created_at).days < 1

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(
            user=instance,
            subscription_tier='basic',
            generations_limit=4
        )

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except:
        pass