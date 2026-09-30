from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class UserUpdateForm(forms.ModelForm):
    """Edit the basic User fields."""
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'your@email.com'}),
        }


class UserProfileForm(forms.ModelForm):
    """Edit the UserProfile fields."""
    class Meta:
        model = UserProfile
        fields = [
            'profile_pic', 'cover_photo',
            'bio', 'location', 'occupation', 'website',
            'twitter_handle', 'facebook_url', 'instagram_url', 'linkedin_url',
            'interests',
            'privacy_level', 'show_online_status',
            'email_notifications', 'receive_promo_emails', 'ad_notifications',
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'maxlength': 500, 'placeholder': 'Tell people about yourself…'}),
            'location': forms.TextInput(attrs={'placeholder': 'City, Country'}),
            'occupation': forms.TextInput(attrs={'placeholder': 'What do you do?'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://example.com'}),
            'twitter_handle': forms.TextInput(attrs={'placeholder': 'username (no @)'}),
            'facebook_url': forms.URLInput(attrs={'placeholder': 'https://facebook.com/yourpage'}),
            'instagram_url': forms.URLInput(attrs={'placeholder': 'https://instagram.com/you'}),
            'linkedin_url': forms.URLInput(attrs={'placeholder': 'https://linkedin.com/in/you'}),
            'interests': forms.TextInput(attrs={'placeholder': 'Technology, Sports, Politics'}),
        }

    def clean_bio(self):
        bio = self.cleaned_data.get('bio', '')
        if bio and len(bio) > 500:
            raise forms.ValidationError('Bio must be 500 characters or less.')
        return bio