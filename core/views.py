import logging
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Count, F, Prefetch, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from news.models import Post, Category
from accounts.models import UserActivity, UserProfile, Follow
from social.models import Comment

logger = logging.getLogger(__name__)


SOCIAL_TYPES = ['discussion', 'profile_post', 'user_news', 'sponsored']


# ==============================================================
#  HOME
# ==============================================================
def home(request):
    """Homepage — social feed for logged-in users, news for guests."""
    if not request.user.is_authenticated:
        return redirect('news:online_news')

    feed = request.GET.get('feed', 'for-you').strip()
    if feed not in ('for-you', 'following'):
        feed = 'for-you'

    view = request.GET.get('view', 'feed').strip()
    if view not in ('feed', 'your-posts', 'interacted', 'activity'):
        view = 'feed'

    following_ids = list(
        request.user.following.values_list('following_id', flat=True)
    )

    base_qs = Post.objects.filter(
        status='published',
        post_type__in=SOCIAL_TYPES,
        privacy='public',
    ).select_related('author', 'category')

    feed_posts = []
    interacted_items = []
    activities = []

    if view == 'feed':
        if feed == 'following':
            feed_posts = base_qs.filter(
                Q(author=request.user) | Q(author_id__in=following_ids)
            ).order_by('-published_at')[:30]
        else:
            feed_posts = base_qs.order_by('-published_at')[:30]

    elif view == 'your-posts':
        feed_posts = Post.objects.filter(
            author=request.user,
            status='published',
        ).select_related('category').order_by('-published_at')[:30]

    elif view == 'interacted':
        liked_ids = list(request.user.liked_posts.values_list('id', flat=True))
        commented_ids = list(Post.objects.filter(
            comments__user=request.user, comments__is_active=True
        ).values_list('id', flat=True))
        reposted_ids = list(Post.objects.filter(
            repost_instances__user=request.user
        ).values_list('id', flat=True))

        all_ids = set(liked_ids) | set(commented_ids) | set(reposted_ids)

        posts_qs = Post.objects.filter(
            id__in=all_ids, status='published'
        ).select_related('author', 'category').order_by('-published_at')[:30]

        liked_set = set(liked_ids)
        commented_set = set(commented_ids)
        reposted_set = set(reposted_ids)

        for p in posts_qs:
            badges = []
            if p.id in liked_set: badges.append('liked')
            if p.id in commented_set: badges.append('commented')
            if p.id in reposted_set: badges.append('reposted')
            interacted_items.append({'post': p, 'badges': badges})

    elif view == 'activity':
        activities = UserActivity.objects.filter(
            user=request.user
        ).select_related('post', 'comment', 'target_user').order_by('-created_at')[:40]

    suggested_users = User.objects.exclude(
        Q(id=request.user.id) | Q(id__in=following_ids)
    ).filter(is_active=True).annotate(
        post_count=Count('posts')
    ).order_by('-post_count')[:5]

    following_preview = list(Follow.objects.filter(
        follower=request.user
    ).select_related('following', 'following__profile').order_by('-created_at')[:6])

    followers_preview = list(Follow.objects.filter(
        following=request.user
    ).select_related('follower', 'follower__profile').order_by('-created_at')[:6])

    bookmark_count = request.user.bookmarked_posts.filter(status='published').count()

    from social.models import Repost
    user_stats = {
        'posts': Post.objects.filter(author=request.user, status='published').count(),
        'followers': Follow.objects.filter(following=request.user).count(),
        'following': Follow.objects.filter(follower=request.user).count(),
        'likes_given': request.user.liked_posts.count(),
        'comments': Comment.objects.filter(user=request.user, is_active=True).count(),
        'reposts': Repost.objects.filter(user=request.user).count(),
        'bookmarks': bookmark_count,
    }

    categories = Category.objects.filter(is_active=True).annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).filter(post_count__gt=0).order_by('-post_count')[:8]

    trending_posts = Post.objects.filter(
        status='published',
        post_type__in=SOCIAL_TYPES,
        created_at__gte=timezone.now() - timedelta(days=7),
    ).annotate(
        like_count=Count('likes', distinct=True),
    ).order_by('-views', '-like_count')[:5]

    return render(request, 'core/home.html', {
        'feed': feed,
        'view': view,
        'feed_posts': feed_posts,
        'interacted_items': interacted_items,
        'activities': activities,
        'suggested_users': suggested_users,
        'following_preview': following_preview,
        'followers_preview': followers_preview,
        'bookmark_count': bookmark_count,
        'categories': categories,
        'trending_posts': trending_posts,
        'user_stats': user_stats,
        'following_count': len(following_ids),
        'title': 'Home',
    })


# ==============================================================
#  SEARCH
# ==============================================================
def search_view(request):
    """Search across posts, users, and categories with highlighting."""
    import re

    query = (request.GET.get('q') or '').strip()
    filter_type = (request.GET.get('type') or 'all').strip()

    # Build regex pattern for highlighting (case-insensitive)
    def make_pattern(q):
        if not q:
            return None
        # Escape regex special chars
        escaped = re.escape(q)
        return re.compile(f'({escaped})', re.IGNORECASE)

    pattern = make_pattern(query)

    def highlight(text, max_len=None):
        """Wrap matches in <mark> tags. Optionally truncate around first match."""
        if not text:
            return ''
        if not pattern:
            return text[:max_len] + '…' if max_len and len(text) > max_len else text

        # Find first match to build a snippet around it
        match = pattern.search(text)
        if max_len and match:
            start = max(0, match.start() - 60)
            end = min(len(text), match.start() + 140)
            snippet = ('…' if start > 0 else '') + text[start:end] + ('…' if end < len(text) else '')
        elif max_len and len(text) > max_len:
            snippet = text[:max_len] + '…'
        else:
            snippet = text

        # Escape HTML first, then apply highlight
        from django.utils.html import escape
        escaped = escape(snippet)
        # Re-run pattern on escaped text
        return pattern.sub(r'<mark>\1</mark>', escaped)

    context = {
        'query': query,
        'filter_type': filter_type,
        'results': {
            'posts': [],
            'users': [],
            'categories': [],
            'counts': {'posts': 0, 'users': 0, 'categories': 0, 'all': 0},
        },
        'title': f'Search: {query}' if query else 'Search',
    }

    if not query or len(query) < 2:
        return render(request, 'core/search.html', context)

    # ---- Posts ----
    posts_qs = Post.objects.filter(
        status='published',
        privacy='public',
    ).filter(
        Q(title__icontains=query) |
        Q(content__icontains=query) |
        Q(author__username__icontains=query) |
        Q(category__name__icontains=query)
    ).select_related('author', 'category').order_by('-published_at').distinct()

    posts_count = posts_qs.count()

    # ---- Users ----
    users_qs = list(User.objects.filter(is_active=True).filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(profile__bio__icontains=query)
    ).select_related('profile').distinct()[:30])

    for u in users_qs:
        u.highlighted_name = highlight(u.get_full_name() or u.username)
        u.highlighted_username = highlight(u.username)

    users_count = len(users_qs)

    # ---- Categories ----
    categories_qs = list(Category.objects.filter(is_active=True).filter(
        Q(name__icontains=query) |
        Q(description__icontains=query)
    ).annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).order_by('-post_count')[:20])

    for c in categories_qs:
        c.highlighted_name = highlight(c.name)

    categories_count = len(categories_qs)

    # ---- Filter ----
    if filter_type == 'posts':
        users_qs = []
        categories_qs = []
    elif filter_type == 'users':
        posts_qs = Post.objects.none()
        categories_qs = []
    elif filter_type == 'categories':
        posts_qs = Post.objects.none()
        users_qs = []

    # ---- Paginate posts ----
    if filter_type in ('all', 'posts'):
        paginator = Paginator(posts_qs, 15)
        page_obj = paginator.get_page(request.GET.get('page', 1))
    else:
        page_obj = None

    # Apply highlighting to posts
    posts_list = list(page_obj) if page_obj else list(posts_qs[:15])
    for p in posts_list:
        p.highlighted_title = highlight(p.title)
        p.highlighted_snippet = highlight(p.content, max_len=200)

    context['results'] = {
        'posts': posts_list,
        'page_obj': page_obj,
        'users': users_qs,
        'categories': categories_qs,
        'counts': {
            'posts': posts_count,
            'users': users_count,
            'categories': categories_count,
            'all': posts_count + users_count + categories_count,
        },
    }
    return render(request, 'core/search.html', context)


# ==============================================================
#  ADMIN — DASHBOARD
# ==============================================================
@staff_member_required
def admin_dashboard(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_posts = Post.objects.count()
    total_users = User.objects.filter(is_active=True).count()

    pending_user_news = Post.objects.filter(
        Q(is_news_submission=True) | Q(post_type='user_news'),
        submission_status='pending',
    ).count()

    pending_ai_news = Post.objects.filter(
        is_auto_fetched=True,
        verification_status='pending',
    ).count()

    pending_news = pending_user_news + pending_ai_news

    auto_fetched = Post.objects.filter(is_auto_fetched=True).count()
    auto_fetched_today = Post.objects.filter(
        is_auto_fetched=True,
        created_at__gte=today_start,
    ).count()

    verified_posts = Post.objects.filter(verification_status='verified').count()
    fake_posts = Post.objects.filter(verification_status='fake').count()

    posts_today = Post.objects.filter(created_at__gte=today_start).count()
    users_today = User.objects.filter(date_joined__gte=today_start).count()

    verified_percent = round((verified_posts / total_posts * 100), 1) if total_posts else 0
    fake_percent = round((fake_posts / total_posts * 100), 1) if total_posts else 0

    recent_activities = UserActivity.objects.select_related(
        'user', 'post', 'target_user'
    ).order_by('-created_at')[:10]

    pending_submissions = Post.objects.filter(
        Q(is_news_submission=True) | Q(post_type='user_news'),
        submission_status='pending',
    ).select_related('author', 'category').order_by('-created_at')[:5]

    pending_ai_submissions = Post.objects.filter(
        is_auto_fetched=True,
        verification_status='pending',
    ).select_related('category').order_by('-created_at')[:5]

    recent_users = User.objects.filter(is_active=True).select_related('profile').order_by('-date_joined')[:5]

    context = {
        'total_posts': total_posts,
        'total_users': total_users,
        'pending_news': pending_news,
        'pending_user_news': pending_user_news,
        'pending_ai_news': pending_ai_news,
        'auto_fetched': auto_fetched,
        'auto_fetched_today': auto_fetched_today,
        'verified_posts': verified_posts,
        'fake_posts': fake_posts,
        'verified_percent': verified_percent,
        'fake_percent': fake_percent,
        'posts_today': posts_today,
        'users_today': users_today,
        'recent_activities': recent_activities,
        'pending_submissions': pending_submissions,
        'pending_ai_submissions': pending_ai_submissions,
        'recent_users': recent_users,
        'title': 'Admin Dashboard',
    }
    return render(request, 'admin_ui/dashboard.html', context)


# ==============================================================
#  ADMIN — MANAGE POSTS
# ==============================================================
@staff_member_required
def admin_posts(request):
    posts = Post.objects.select_related('author', 'category').order_by('-created_at')

    filter_type = request.GET.get('filter', 'all').strip()
    search = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '').strip()
    post_type = request.GET.get('type', '').strip()
    verification = request.GET.get('verification', '').strip()

    if filter_type == 'pending':
        posts = posts.filter(verification_status='pending')
    elif filter_type == 'verified':
        posts = posts.filter(verification_status='verified')
    elif filter_type == 'likely':
        posts = posts.filter(verification_status='likely_legit')
    elif filter_type == 'fake':
        posts = posts.filter(verification_status='fake')
    elif filter_type == 'news':
        posts = posts.filter(post_type__in=['news', 'user_news'])
    elif filter_type == 'discussions':
        posts = posts.filter(post_type='discussion')
    elif filter_type == 'profile':
        posts = posts.filter(post_type='profile_post')
    elif filter_type == 'user_news':
        posts = posts.filter(Q(post_type='user_news') | Q(is_news_submission=True))
    elif filter_type == 'auto_news':
        posts = posts.filter(Q(is_auto_fetched=True) | Q(post_type='news'))

    if search:
        posts = posts.filter(
            Q(title__icontains=search) |
            Q(content__icontains=search) |
            Q(author__username__icontains=search) |
            Q(external_source__icontains=search)
        )

    if category_id and category_id.isdigit():
        posts = posts.filter(category_id=int(category_id))

    if post_type:
        posts = posts.filter(post_type=post_type)

    if verification:
        posts = posts.filter(verification_status=verification)

    base = Post.objects.all()
    stats = {
        'total': base.count(),
        'verified': base.filter(verification_status='verified').count(),
        'likely': base.filter(verification_status='likely_legit').count(),
        'pending': base.filter(verification_status='pending').count(),
        'fake': base.filter(verification_status='fake').count(),
        'news': base.filter(post_type__in=['news', 'user_news']).count(),
        'user_news': base.filter(Q(post_type='user_news') | Q(is_news_submission=True)).count(),
        'auto_news': base.filter(Q(is_auto_fetched=True) | Q(post_type='news')).count(),
    }

    categories = Category.objects.all().order_by('name')

    paginator = Paginator(posts, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'posts': page_obj,
        'stats': stats,
        'categories': categories,
        'filter_type': filter_type,
        'search': search,
        'category_id': category_id,
        'post_type': post_type,
        'verification': verification,
        'title': 'Manage Posts',
    }
    return render(request, 'admin_ui/posts.html', context)


# ==============================================================
#  ADMIN — BULK ACTIONS
# ==============================================================
@staff_member_required
@require_POST
def admin_bulk_action(request):
    from news.services.verifier import EnhancedNewsVerifier
    from core.models import SystemSettings

    action = request.POST.get('action', '').strip()
    post_ids = request.POST.getlist('post_ids')
    scope = request.POST.get('scope', '').strip()

    if scope == 'all_pending':
        qs = Post.objects.filter(verification_status='pending')
    elif scope == 'all_user':
        qs = Post.objects.filter(Q(post_type='user_news') | Q(is_news_submission=True))
    elif scope == 'all_auto':
        qs = Post.objects.filter(Q(is_auto_fetched=True) | Q(post_type='news'))
    elif post_ids:
        qs = Post.objects.filter(id__in=post_ids)
    else:
        return JsonResponse({'success': False, 'error': 'Nothing selected'}, status=400)

    posts = list(qs[:100])

    if not posts:
        return JsonResponse({'success': False, 'error': 'No posts to process'}, status=400)

    settings = SystemSettings.get_settings()
    verify_at = settings.auto_approve_threshold
    publish_at = settings.min_publish_threshold

    if action in ('mark_verified', 'mark_fake', 'mark_pending'):
        status_map = {
            'mark_verified': 'verified',
            'mark_fake': 'fake',
            'mark_pending': 'pending',
        }
        new_status = status_map[action]
        for post in posts:
            post.verification_status = new_status
            post.is_verified = (new_status == 'verified')
            post.save(update_fields=['verification_status', 'is_verified'])

        return JsonResponse({'success': True, 'count': len(posts), 'action': new_status})

    if action in ('run_ai', 'run_ai_pending'):
        verifier = EnhancedNewsVerifier()
        updated = 0
        for post in posts:
            if action == 'run_ai_pending' and post.verification_status != 'pending':
                continue
            try:
                article = {
                    'title': post.title or '',
                    'content': post.content or '',
                    'url': post.external_url or post.source_url or '',
                    'source': post.external_source or '',
                }
                result = verifier.verify_article(article)
                score = result.get('overall_score', 0.0)

                post.verification_score = score
                post.verification_details = result
                post.verification_method = 'ai_assisted'

                if score >= verify_at:
                    post.verification_status = 'verified'
                    post.is_verified = True
                elif score >= publish_at:
                    post.verification_status = 'likely_legit'
                    post.is_verified = False
                elif score >= 0.4:
                    post.verification_status = 'pending'
                else:
                    post.verification_status = 'fake'

                post.save()
                updated += 1
            except Exception as e:
                logger.exception(f"Bulk verify failed for post {post.id}: {e}")

        return JsonResponse({'success': True, 'count': updated, 'action': 'run_ai'})

    return JsonResponse({'success': False, 'error': 'Unknown action'}, status=400)


# ==============================================================
#  ADMIN — ROW ACTIONS
# ==============================================================
@staff_member_required
@require_POST
def admin_run_ai_single(request, post_id):
    from news.services.verifier import EnhancedNewsVerifier
    from core.models import SystemSettings

    post = Post.objects.filter(id=post_id).first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    try:
        verifier = EnhancedNewsVerifier()
        article = {
            'title': post.title or '',
            'content': post.content or '',
            'url': post.external_url or post.source_url or '',
            'source': post.external_source or '',
        }
        result = verifier.verify_article(article)
        score = result.get('overall_score', 0.0)

        settings = SystemSettings.get_settings()
        verify_at = settings.auto_approve_threshold
        publish_at = settings.min_publish_threshold

        post.verification_score = score
        post.verification_details = result
        post.verification_method = 'ai_assisted'

        if score >= verify_at:
            post.verification_status = 'verified'
            post.is_verified = True
        elif score >= publish_at:
            post.verification_status = 'likely_legit'
            post.is_verified = False
        elif score >= 0.4:
            post.verification_status = 'pending'
        else:
            post.verification_status = 'fake'

        post.save()

        return JsonResponse({'success': True, 'status': post.verification_status, 'score': score})
    except Exception as e:
        logger.exception(f"AI verification failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
@require_POST
def admin_set_verification_status(request, post_id):
    post = Post.objects.filter(id=post_id).first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    new_status = request.POST.get('status', '').strip()
    if new_status not in ('verified', 'fake', 'pending', 'likely_legit', 'unverified'):
        return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)

    post.verification_status = new_status
    post.is_verified = (new_status == 'verified')
    post.save(update_fields=['verification_status', 'is_verified'])

    return JsonResponse({'success': True, 'status': new_status})


@staff_member_required
@require_POST
def admin_toggle_banner(request, post_id):
    post = Post.objects.filter(id=post_id).first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
    post.is_banner = not post.is_banner
    post.save(update_fields=['is_banner'])
    return JsonResponse({'success': True, 'is_banner': post.is_banner})


@staff_member_required
@require_POST
def admin_toggle_featured(request, post_id):
    post = Post.objects.filter(id=post_id).first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
    post.is_featured = not post.is_featured
    post.save(update_fields=['is_featured'])
    return JsonResponse({'success': True, 'is_featured': post.is_featured})


# ==============================================================
#  ADMIN — QUICK FETCH
# ==============================================================
@staff_member_required
def admin_quick_fetch(request):
    base = Post.objects.filter(is_auto_fetched=True)
    stats = {
        'total': base.count(),
        'today': base.filter(created_at__gte=timezone.now() - timedelta(hours=24)).count(),
        'with_video': base.exclude(video_urls=[]).exclude(video_urls__isnull=True).count(),
        'with_audio': base.exclude(audio_urls=[]).exclude(audio_urls__isnull=True).count(),
        'verified': base.filter(verification_status='verified').count(),
        'pending': base.filter(verification_status='pending').count(),
    }

    from news.models import FetchLog
    recent_logs = FetchLog.objects.all().order_by('-created_at')[:15]

    context = {'stats': stats, 'recent_logs': recent_logs, 'title': 'Quick Fetch'}
    return render(request, 'admin_ui/quick_fetch.html', context)


@staff_member_required
@require_POST
def admin_run_fetch(request):
    from news.services.pipeline import NewsPipeline

    try:
        days = int(request.POST.get('days', 1))
        limit = int(request.POST.get('limit', 20))
        workers = int(request.POST.get('workers', 5))
        extract_full = request.POST.get('extract_full', 'true').lower() == 'true'
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid parameters'}, status=400)

    if days < 1 or days > 30:
        return JsonResponse({'success': False, 'error': 'days must be 1-30'}, status=400)
    if limit < 1 or limit > 200:
        return JsonResponse({'success': False, 'error': 'limit must be 1-200'}, status=400)

    try:
        pipeline = NewsPipeline()
        stats = pipeline.run(days=days, limit=limit, workers=workers, extract_full=extract_full)

        from news.models import FetchLog
        FetchLog.objects.create(
            action='manual_fetch',
            details=f"Saved {stats.get('saved', 0)} articles from {stats.get('total_raw', 0)} raw",
            user=request.user,
        )

        return JsonResponse({'success': True, 'stats': stats})
    except Exception as e:
        logger.exception(f"Manual fetch failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==============================================================
#  ADMIN — SETTINGS
# ==============================================================
@staff_member_required
def admin_settings(request):
    from core.models import SystemSettings
    from core.forms import SystemSettingsForm

    settings_obj = SystemSettings.get_settings()

    if request.method == 'POST':
        form = SystemSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, 'System settings saved successfully.')
            return redirect('core:admin_settings')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = SystemSettingsForm(instance=settings_obj)

    context = {'form': form, 'settings': settings_obj, 'title': 'System Settings'}
    return render(request, 'admin_ui/settings.html', context)


def search_suggestions(request):
    """AJAX endpoint for search autocomplete."""
    query = (request.GET.get('q') or '').strip()

    if len(query) < 2:
        return JsonResponse({'suggestions': []})

    suggestions = []

    # ---- Post title matches ----
    posts = Post.objects.filter(
        status='published',
        title__icontains=query,
    ).exclude(title='').order_by('-views')[:5]

    for p in posts:
        suggestions.append({
            'type': 'post',
            'label': p.title,
            'url': p.get_absolute_url() if hasattr(p, 'get_absolute_url') else f'/news/post/{p.id}/',
            'icon': 'file-alt',
        })

    # ---- User matches ----
    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).filter(is_active=True).order_by('username')[:5]

    for u in users:
        suggestions.append({
            'type': 'user',
            'label': f'{u.get_full_name() or u.username} (@{u.username})',
            'url': f'/accounts/profile/{u.username}/',
            'icon': 'user',
            'avatar': u.profile.profile_pic.url if hasattr(u, 'profile') and u.profile.profile_pic else None,
        })

    # ---- Category matches ----
    cats = Category.objects.filter(
        name__icontains=query, is_active=True
    )[:3]

    for c in cats:
        suggestions.append({
            'type': 'category',
            'label': c.name,
            'url': f'/news/category/{c.slug}/',
            'icon': 'hashtag',
        })

    return JsonResponse({'suggestions': suggestions})


@require_POST
def newsletter_signup(request):
    """Handle newsletter signup from footer."""
    from core.models import NewsletterSubscriber

    email = (request.POST.get('email') or '').strip().lower()

    if not email:
        return JsonResponse({'success': False, 'error': 'Email is required'}, status=400)

    # Basic email validation
    import re
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return JsonResponse({'success': False, 'error': 'Please enter a valid email'}, status=400)

    subscriber, created = NewsletterSubscriber.objects.get_or_create(
        email=email,
        defaults={'source': 'footer'},
    )

    if not created and not subscriber.is_active:
        subscriber.is_active = True
        subscriber.save(update_fields=['is_active'])
        return JsonResponse({'success': True, 'message': 'Welcome back! You\'re re-subscribed.'})

    if created:
        return JsonResponse({'success': True, 'message': 'Thanks for subscribing!'})

    return JsonResponse({'success': True, 'message': 'You\'re already subscribed.'})

@staff_member_required
def admin_subscribers(request):
    """Admin — view newsletter subscribers."""
    from core.models import NewsletterSubscriber

    subscribers = NewsletterSubscriber.objects.all().order_by('-subscribed_at')

    # Stats
    total = subscribers.count()
    active = subscribers.filter(is_active=True).count()
    last_7 = subscribers.filter(
        subscribed_at__gte=timezone.now() - timedelta(days=7)
    ).count()

    from django.core.paginator import Paginator
    paginator = Paginator(subscribers, 50)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'admin_ui/subscribers.html', {
        'page_obj': page_obj,
        'subscribers': page_obj,
        'total': total,
        'active': active,
        'last_7': last_7,
        'title': 'Newsletter Subscribers',
    })
    
# ==============================================================
#  ADMIN — NEWS SOURCES (Scanner)
# ==============================================================
@staff_member_required
def admin_sources(request):
    """Admin — list all news sources."""
    from news.models import NewsSource

    sources = NewsSource.objects.all().order_by('-is_active', 'name')

    stats = {
        'total': sources.count(),
        'working': sources.filter(last_status='working').count(),
        'broken': sources.filter(last_status='broken').count(),
        'untested': sources.filter(last_status='unknown').count(),
        'active': sources.filter(is_active=True).count(),
    }

    return render(request, 'admin_ui/sources.html', {
        'sources': sources,
        'stats': stats,
        'title': 'News Sources',
    })


@staff_member_required
@require_POST
def admin_source_add(request):
    """Add a new news source."""
    from news.models import NewsSource

    name = (request.POST.get('name') or '').strip()
    url = (request.POST.get('url') or '').strip()
    source_type = (request.POST.get('source_type') or 'rss').strip()
    category_hint = (request.POST.get('category_hint') or '').strip()
    country_hint = (request.POST.get('country_hint') or '').strip()

    if not name or not url:
        return JsonResponse({'success': False, 'error': 'Name and URL are required'}, status=400)

    if NewsSource.objects.filter(url=url).exists():
        return JsonResponse({'success': False, 'error': 'This URL already exists'}, status=400)

    source = NewsSource.objects.create(
        name=name,
        url=url,
        source_type=source_type,
        category_hint=category_hint,
        country_hint=country_hint,
    )

    return JsonResponse({
        'success': True,
        'id': source.id,
        'message': f'Added {source.name}',
    })


@staff_member_required
@require_POST
def admin_source_test(request, source_id):
    """Test a single source."""
    from news.models import NewsSource
    from news.services.source_scanner import SourceScanner

    source = NewsSource.objects.filter(id=source_id).first()
    if not source:
        return JsonResponse({'success': False, 'error': 'Source not found'}, status=404)

    scanner = SourceScanner()
    result = scanner.test_source(source.url)

    source.last_tested = timezone.now()
    source.last_response_ms = result['response_ms']
    source.last_article_count = result['count']

    if result['ok']:
        source.last_status = 'working' if result['response_ms'] < 5000 else 'slow'
        source.last_error = ''
    else:
        source.last_status = 'broken'
        source.last_error = result['error']

    source.save()

    return JsonResponse({
        'success': result['ok'],
        'status': source.last_status,
        'count': result['count'],
        'response_ms': result['response_ms'],
        'error': result['error'],
        'sample': result['sample'],
    })


@staff_member_required
@require_POST
def admin_source_toggle(request, source_id):
    """Enable / disable a source."""
    from news.models import NewsSource

    source = NewsSource.objects.filter(id=source_id).first()
    if not source:
        return JsonResponse({'success': False, 'error': 'Source not found'}, status=404)

    source.is_active = not source.is_active
    source.save(update_fields=['is_active'])

    return JsonResponse({'success': True, 'is_active': source.is_active})


@staff_member_required
@require_POST
def admin_source_delete(request, source_id):
    """Delete a source."""
    from news.models import NewsSource

    source = NewsSource.objects.filter(id=source_id).first()
    if not source:
        return JsonResponse({'success': False, 'error': 'Source not found'}, status=404)

    source.delete()
    return JsonResponse({'success': True})


@staff_member_required
@require_POST
def admin_source_test_all(request):
    """Test all sources."""
    from news.models import NewsSource
    from news.services.source_scanner import SourceScanner

    sources = NewsSource.objects.all()
    scanner = SourceScanner()

    results = []
    working = 0
    broken = 0

    for source in sources:
        result = scanner.test_source(source.url)

        source.last_tested = timezone.now()
        source.last_response_ms = result['response_ms']
        source.last_article_count = result['count']

        if result['ok']:
            source.last_status = 'working' if result['response_ms'] < 5000 else 'slow'
            source.last_error = ''
            working += 1
        else:
            source.last_status = 'broken'
            source.last_error = result['error']
            broken += 1

        source.save()

        results.append({
            'name': source.name,
            'status': source.last_status,
            'count': result['count'],
            'error': result['error'],
        })

    return JsonResponse({
        'success': True,
        'tested': sources.count(),
        'working': working,
        'broken': broken,
        'results': results,
    })


@staff_member_required
@require_POST
def admin_source_discover(request):
    """Auto-discover RSS feeds from a website URL."""
    from news.services.source_scanner import SourceScanner

    site_url = (request.POST.get('site_url') or '').strip()
    if not site_url:
        return JsonResponse({'success': False, 'error': 'Website URL is required'}, status=400)

    scanner = SourceScanner()
    candidates = scanner.discover_feeds(site_url)

    return JsonResponse({
        'success': True,
        'count': len(candidates),
        'candidates': candidates,
    })


@staff_member_required
@require_POST
def admin_source_seed_defaults(request):
    """Seed the database with default trusted sources."""
    from news.models import NewsSource

    defaults = [
        # BBC
        {'name': 'BBC Africa', 'url': 'https://feeds.bbci.co.uk/news/world/africa/rss.xml', 'country_hint': 'Africa'},
        {'name': 'BBC World', 'url': 'https://feeds.bbci.co.uk/news/world/rss.xml', 'country_hint': 'World'},
        {'name': 'BBC Business', 'url': 'https://feeds.bbci.co.uk/news/business/rss.xml', 'category_hint': 'business'},
        {'name': 'BBC Technology', 'url': 'https://feeds.bbci.co.uk/news/technology/rss.xml', 'category_hint': 'tech'},
        # Al Jazeera
        {'name': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'country_hint': 'World'},
        # Nigerian
        {'name': 'Premium Times', 'url': 'https://www.premiumtimesng.com/feed', 'country_hint': 'Nigeria'},
        {'name': 'Punch', 'url': 'https://punchng.com/feed', 'country_hint': 'Nigeria'},
        {'name': 'Vanguard', 'url': 'https://www.vanguardngr.com/feed', 'country_hint': 'Nigeria'},
        {'name': 'The Guardian NG', 'url': 'https://guardian.ng/feed/', 'country_hint': 'Nigeria'},
        {'name': 'The Cable', 'url': 'https://www.thecable.ng/feed', 'country_hint': 'Nigeria'},
    ]

    added = 0
    skipped = 0

    for d in defaults:
        if NewsSource.objects.filter(url=d['url']).exists():
            skipped += 1
            continue
        NewsSource.objects.create(
            name=d['name'],
            url=d['url'],
            source_type='rss',
            country_hint=d.get('country_hint', ''),
            category_hint=d.get('category_hint', ''),
            is_trusted=True,
        )
        added += 1

    return JsonResponse({
        'success': True,
        'added': added,
        'skipped': skipped,
    })
    
@staff_member_required
def admin_scheduler_status(request):
    """Get scheduler status (AJAX)."""
    from core.models import SystemSettings
    from news.services.scheduler import auto_fetcher
    from news.models import NewsSource

    settings = SystemSettings.get_settings()

    now = timezone.now()
    seconds_until = None
    if settings.auto_fetch_next_run:
        delta = (settings.auto_fetch_next_run - now).total_seconds()
        seconds_until = max(0, int(delta))

    active_source_count = NewsSource.objects.filter(
        is_active=True, source_type='rss'
    ).exclude(last_status='broken').count()

    return JsonResponse({
        'enabled': settings.enable_auto_fetch,
        'running': auto_fetcher.is_running,
        'interval': settings.auto_fetch_interval,
        'interval_display': settings.get_auto_fetch_interval_display(),
        'last_run': settings.auto_fetch_last_run.isoformat() if settings.auto_fetch_last_run else None,
        'next_run': settings.auto_fetch_next_run.isoformat() if settings.auto_fetch_next_run else None,
        'seconds_until': seconds_until,
        'max_per_fetch': settings.max_news_per_fetch,
        'source_count': active_source_count,
    })


@staff_member_required
@require_POST
def admin_scheduler_update(request):
    """Update scheduler settings."""
    from core.models import SystemSettings
    from news.services.scheduler import INTERVALS

    interval = request.POST.get('interval', '').strip()
    max_fetch = request.POST.get('max_fetch', '').strip()

    if interval not in INTERVALS:
        return JsonResponse({'success': False, 'error': 'Invalid interval'}, status=400)

    try:
        max_fetch = int(max_fetch)
        if max_fetch < 10 or max_fetch > 500:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Max fetch must be 10-500'}, status=400)

    settings = SystemSettings.get_settings()
    settings.auto_fetch_interval = interval
    settings.max_news_per_fetch = max_fetch

    # Recalculate next run
    settings.auto_fetch_next_run = timezone.now() + INTERVALS[interval]
    settings.save()

    return JsonResponse({
        'success': True,
        'interval': interval,
        'next_run': settings.auto_fetch_next_run.isoformat(),
    })


@staff_member_required
@require_POST
def admin_scheduler_toggle(request):
    """Start or stop the background scheduler thread."""
    from news.services.scheduler import auto_fetcher
    from core.models import SystemSettings

    action = request.POST.get('action', '').strip()

    if action == 'start':
        auto_fetcher.start()
        settings = SystemSettings.get_settings()
        settings.enable_auto_fetch = True
        settings.save(update_fields=['enable_auto_fetch'])
        return JsonResponse({'success': True, 'running': True})

    elif action == 'stop':
        auto_fetcher.stop()
        settings = SystemSettings.get_settings()
        settings.enable_auto_fetch = False
        settings.save(update_fields=['enable_auto_fetch'])
        return JsonResponse({'success': True, 'running': False})

    return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)

@staff_member_required
@require_POST
def admin_scheduler_run_now(request):
    """Force an immediate fetch."""
    from news.services.pipeline import NewsPipeline
    from core.models import SystemSettings

    settings = SystemSettings.get_settings()

    try:
        pipeline = NewsPipeline()
        stats = pipeline.run(
            days=1,
            limit=settings.max_news_per_fetch,
            workers=5,
            extract_full=True,
        )

        settings.auto_fetch_last_run = timezone.now()
        settings.save(update_fields=['auto_fetch_last_run'])

        return JsonResponse({'success': True, 'stats': stats})
    except Exception as e:
        logger.exception(f"Manual scheduler run failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
# ==============================================================
#  ADMIN — ADS
# ==============================================================
@staff_member_required
def admin_ads(request):
    """Admin — manage all advertisements."""
    from ads.models import Advertisement, AdAnalytics

    ads = Advertisement.objects.select_related('business').order_by('-created_at')

    # Filters
    ad_type = request.GET.get('type', '').strip()
    status = request.GET.get('status', '').strip()

    if ad_type:
        ads = ads.filter(ad_type=ad_type)
    if status:
        ads = ads.filter(status=status)

    # Stats
    base = Advertisement.objects.all()
    stats = {
        'total': base.count(),
        'active': base.filter(is_active=True, status__in=['approved', 'active']).count(),
        'pending': base.filter(status='pending').count(),
        'banner': base.filter(ad_type='banner').count(),
        'sidebar': base.filter(ad_type='sidebar').count(),
        'in_feed': base.filter(ad_type='in_feed').count(),
    }

    # Analytics totals (sum across all ads)
    total_impressions = AdAnalytics.objects.aggregate(
        total=Sum('impressions')
    )['total'] or 0
    total_clicks = AdAnalytics.objects.aggregate(
        total=Sum('clicks')
    )['total'] or 0
    total_cost = AdAnalytics.objects.aggregate(
        total=Sum('cost')
    )['total'] or 0

    # Attach analytics to each ad
    for ad in ads:
        ad.total_impressions = ad.analytics.aggregate(t=Sum('impressions'))['t'] or 0
        ad.total_clicks = ad.analytics.aggregate(t=Sum('clicks'))['t'] or 0
        if ad.total_impressions > 0:
            ad.ctr_display = round((ad.total_clicks / ad.total_impressions) * 100, 2)
        else:
            ad.ctr_display = 0.0

    return render(request, 'admin_ui/ads.html', {
        'ads': ads,
        'stats': stats,
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_cost': total_cost,
        'filter_type': ad_type,
        'filter_status': status,
        'title': 'Advertisements',
    })


@staff_member_required
@require_POST
def admin_ad_create(request):
    """Create a new advertisement from admin."""
    from ads.models import Advertisement
    from decimal import Decimal

    title = (request.POST.get('title') or '').strip()
    ad_type = (request.POST.get('ad_type') or 'banner').strip()
    target_url = (request.POST.get('target_url') or '').strip()
    image_url = (request.POST.get('image_url') or '').strip()
    description = (request.POST.get('description') or '').strip()

    if not title or not target_url:
        return JsonResponse({'success': False, 'error': 'Title and target URL are required'}, status=400)

    if ad_type not in ('banner', 'sidebar', 'in_feed', 'sponsored_post'):
        return JsonResponse({'success': False, 'error': 'Invalid ad type'}, status=400)

    # Default dates: now to 30 days from now
    now = timezone.now()
    end = now + timedelta(days=30)

    try:
        budget = Decimal(request.POST.get('budget') or '0')
    except Exception:
        budget = Decimal('0')

    ad = Advertisement.objects.create(
        title=title,
        ad_type=ad_type,
        description=description,
        target_url=target_url,
        image_url=image_url[:1000],
        business=None,  # house ad
        budget=budget,
        start_date=now,
        end_date=end,
        status='approved',
        is_active=True,
        approved_by=request.user,
        approved_at=now,
    )

    # Handle image upload if provided
    if request.FILES.get('image'):
        ad.image = request.FILES['image']
        ad.save(update_fields=['image'])

    return JsonResponse({
        'success': True,
        'id': ad.id,
        'message': f'Created "{ad.title}"',
    })


@staff_member_required
@require_POST
def admin_ad_toggle(request, ad_id):
    """Toggle active status."""
    from ads.models import Advertisement

    ad = Advertisement.objects.filter(id=ad_id).first()
    if not ad:
        return JsonResponse({'success': False, 'error': 'Ad not found'}, status=404)

    ad.is_active = not ad.is_active
    if ad.is_active and ad.status not in ('approved', 'active'):
        ad.status = 'active'
    ad.save(update_fields=['is_active', 'status'])

    return JsonResponse({'success': True, 'is_active': ad.is_active})


@staff_member_required
@require_POST
def admin_ad_delete(request, ad_id):
    """Delete an ad."""
    from ads.models import Advertisement

    ad = Advertisement.objects.filter(id=ad_id).first()
    if not ad:
        return JsonResponse({'success': False, 'error': 'Ad not found'}, status=404)

    ad.delete()
    return JsonResponse({'success': True})


@staff_member_required
def admin_ad_detail(request, ad_id):
    """View single ad details + analytics."""
    from ads.models import Advertisement, AdAnalytics

    ad = get_object_or_404(Advertisement, id=ad_id)
    analytics = AdAnalytics.objects.filter(advertisement=ad).order_by('-date')[:30]

    total_impressions = analytics.aggregate(t=Sum('impressions'))['t'] or 0
    total_clicks = analytics.aggregate(t=Sum('clicks'))['t'] or 0
    total_cost = analytics.aggregate(t=Sum('cost'))['t'] or 0

    ctr = round((total_clicks / total_impressions) * 100, 2) if total_impressions else 0

    return render(request, 'admin_ui/ad_detail.html', {
        'ad': ad,
        'analytics': analytics,
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_cost': total_cost,
        'ctr': ctr,
        'title': ad.title,
    })


# ==============================================================
#  PUBLIC — AD TRACKING
# ==============================================================
@require_POST
def track_ad_impression(request, ad_id):
    """Increment impression count for an ad (AJAX)."""
    from ads.models import Advertisement, AdAnalytics

    ad = Advertisement.objects.filter(uuid=ad_id).first()
    if not ad:
        return JsonResponse({'success': False}, status=404)

    today = timezone.now().date()
    analytics, _ = AdAnalytics.objects.get_or_create(
        advertisement=ad,
        date=today,
        defaults={'impressions': 0, 'clicks': 0, 'cost': 0},
    )
    analytics.impressions += 1
    analytics.cost += ad.cost_per_impression or 0
    analytics.update_metrics()

    return JsonResponse({'success': True})


@require_POST
def track_ad_click(request, ad_id):
    """Increment click count for an ad (AJAX)."""
    from ads.models import Advertisement, AdAnalytics

    ad = Advertisement.objects.filter(uuid=ad_id).first()
    if not ad:
        return JsonResponse({'success': False}, status=404)

    today = timezone.now().date()
    analytics, _ = AdAnalytics.objects.get_or_create(
        advertisement=ad,
        date=today,
        defaults={'impressions': 0, 'clicks': 0, 'cost': 0},
    )
    analytics.clicks += 1
    analytics.cost += ad.cost_per_click or 0
    analytics.update_metrics()

    return JsonResponse({'success': True})

# ==============================================================
#  STATIC PAGES
# ==============================================================

def about_page(request):
    return render(request, 'core/about.html', {'title': 'About Us'})


def contact_page(request):
    submitted = False
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        message = (request.POST.get('message') or '').strip()

        if name and email and message:
            # For now, log it. You can later wire this to email or a ContactMessage model.
            logger.info(f"Contact form: {name} <{email}> — {subject}")
            submitted = True

    return render(request, 'core/contact.html', {
        'submitted': submitted,
        'title': 'Contact Us',
    })


def help_page(request):
    return render(request, 'core/help.html', {'title': 'Help Center'})


def privacy_page(request):
    return render(request, 'core/privacy.html', {'title': 'Privacy Policy'})


def terms_page(request):
    return render(request, 'core/terms.html', {'title': 'Terms of Service'})