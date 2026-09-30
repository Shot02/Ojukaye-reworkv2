from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .models import UserProfile, Follow
from .forms import RegistrationForm
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .forms import RegistrationForm, UserUpdateForm, UserProfileForm

def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('core:home')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form, 'title': 'Login'})


def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('core:home')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created! Welcome to Ojukaye.')
            return redirect('core:home')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form, 'title': 'Register'})


def profile_view(request, username):
    user = get_object_or_404(User, username=username)
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Only show published posts, newest first
    posts = user.posts.filter(status='published').select_related('category').order_by('-published_at')[:20]

    # Follow state
    is_following = False
    if request.user.is_authenticated and request.user != user:
        is_following = Follow.objects.filter(follower=request.user, following=user).exists()

    # Stats
    followers_count = Follow.objects.filter(following=user).count()
    following_count = Follow.objects.filter(follower=user).count()
    posts_count = user.posts.filter(status='published').count()

    is_own_profile = request.user.is_authenticated and request.user == user

    return render(request, 'accounts/profile.html', {
        'profile_user': user,
        'profile': profile,
        'posts': posts,
        'is_following': is_following,
        'is_own_profile': is_own_profile,
        'followers_count': followers_count,
        'following_count': following_count,
        'posts_count': posts_count,
        'title': f'{user.username} · Profile',
    })
    
@login_required
def edit_profile(request):
    """Edit current user's profile."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile', username=request.user.username)
        else:
            messages.error(request, 'Please fix the errors below.')

    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)

    return render(request, 'accounts/edit_profile.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'profile': profile,
        'title': 'Edit Profile',
    })


@require_POST
def follow_user(request, username):
    """AJAX endpoint: toggle follow/unfollow."""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Login required'}, status=401)

    target = get_object_or_404(User, username=username)

    if target == request.user:
        return JsonResponse({'success': False, 'error': "You can't follow yourself"}, status=400)

    follow, created = Follow.objects.get_or_create(
        follower=request.user,
        following=target,
    )

    if not created:
        follow.delete()
        followed = False
    else:
        followed = True

    followers_count = Follow.objects.filter(following=target).count()

    return JsonResponse({
        'success': True,
        'followed': followed,
        'followers_count': followers_count,
    })
    
@login_required
@require_POST
def set_theme(request):
    """Save the user's theme preference."""
    theme = request.POST.get('theme', '').strip()
    if theme not in ('default', 'original', 'dark'):
        return JsonResponse({'success': False, 'error': 'Invalid theme'}, status=400)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.theme_preference = theme
    profile.save(update_fields=['theme_preference'])

    return JsonResponse({'success': True, 'theme': theme})