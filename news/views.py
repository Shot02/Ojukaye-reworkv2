import logging
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Count, F, Prefetch
from django.utils import timezone
from datetime import timedelta
from social.models import Comment

from ads.models import Advertisement


from .models import Post, Category
from .services.media_processor import MediaProcessor


logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
#  ONLINE NEWS  —  the public news feed
# ----------------------------------------------------------------
def online_news(request):
    """
    Public news listing.
    Filters: category, search, sort, media type, verification.
    Admins additionally get fetcher stats.
    """
    # --- base queryset ---
    posts = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news'],
    ).select_related('category', 'author')

    # --- filters from query params ---
    category_slug = request.GET.get('category', '').strip()
    search_query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'latest').strip()
    media = request.GET.get('media', '').strip()
    verification = request.GET.get('verification', '').strip()

    current_category = None
    if category_slug and category_slug != 'all':
        current_category = Category.objects.filter(slug=category_slug, is_active=True).first()
        if current_category:
            posts = posts.filter(category=current_category)

    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(external_source__icontains=search_query)
        )

    if media == 'video':
        posts = posts.filter(has_media=True).exclude(video_urls=[])
    elif media == 'audio':
        posts = posts.filter(has_media=True).exclude(audio_urls=[])

    if verification == 'verified':
        posts = posts.filter(verification_status='verified')
    elif verification == 'pending':
        posts = posts.filter(verification_status='pending')

    # --- sorting ---
    if sort == 'trending':
        cutoff = timezone.now() - timedelta(days=2)
        posts = posts.filter(created_at__gte=cutoff).annotate(
            like_count=Count('likes', distinct=True),
            comment_count_val=Count('comments', filter=Q(comments__is_active=True), distinct=True),
        ).annotate(
            engagement=F('like_count') + F('comment_count_val') * 2 + F('views') / 100
        ).order_by('-engagement', '-published_at')
    elif sort == 'popular':
        posts = posts.order_by('-views', '-published_at')
    else:
        posts = posts.order_by('-published_at')

    # --- pagination ---
    paginator = Paginator(posts, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # --- sidebar: categories ---
    categories = Category.objects.filter(is_active=True).annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).filter(post_count__gt=0).order_by('-post_count')[:10]

    # --- sidebar: top sources ---
    top_sources = Post.objects.filter(
        post_type__in=['news', 'user_news'],
        status='published',
    ).exclude(
        external_source__isnull=True
    ).exclude(
        external_source=''
    ).values('external_source').annotate(
        count=Count('id')
    ).order_by('-count')[:6]

    # --- sidebar: trending ---
    trending_posts = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news'],
        created_at__gte=timezone.now() - timedelta(days=7),
    ).annotate(
        like_count=Count('likes', distinct=True),
    ).order_by('-views', '-like_count')[:5]

    # --- banner posts (featured) ---
    banner_posts = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news'],
        is_banner=True,
    ).select_related('category').order_by('-banner_priority', '-published_at')[:5]

    # Fallback: if no banners marked, use featured posts
    if not banner_posts.exists():
        banner_posts = Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news'],
            is_featured=True,
        ).select_related('category').order_by('-published_at')[:5]

    # Fallback 2: if still nothing, use the latest 3 articles
    if not banner_posts.exists():
        banner_posts = Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news'],
        ).select_related('category').order_by('-published_at')[:3]

    # --- sponsored content ---
    sponsored_posts = Post.objects.filter(
        status='published',
        is_sponsored=True,
    ).order_by('-published_at')[:3]



    now = timezone.now()
    active_ads_qs = Advertisement.objects.filter(
        is_active=True,
        status__in=['approved', 'active'],
        start_date__lte=now,
        end_date__gte=now,
    ).select_related('business')

    banner_ads = list(active_ads_qs.filter(ad_type='banner')[:5])
    sidebar_ads = list(active_ads_qs.filter(ad_type='sidebar')[:3])

    # --- admin-only: fetcher stats ---
    fetcher_stats = None
    if request.user.is_staff:
        fetcher_stats = {
            'total_fetched': Post.objects.filter(is_auto_fetched=True).count(),
            'last_24h': Post.objects.filter(
                is_auto_fetched=True,
                created_at__gte=timezone.now() - timedelta(hours=24),
            ).count(),
            'with_media': Post.objects.filter(is_auto_fetched=True, has_media=True).count(),
            'verified': Post.objects.filter(is_auto_fetched=True, verification_status='verified').count(),
            'pending': Post.objects.filter(is_auto_fetched=True, verification_status='pending').count(),
        }

    context = {
        'posts': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'top_sources': top_sources,
        'trending_posts': trending_posts,
        'banner_posts': banner_posts,
        'sponsored_posts': sponsored_posts,
        'fetcher_stats': fetcher_stats,
        'current_category': current_category,
        'search_query': search_query,
        'banner_ads': banner_ads,
        'sidebar_ads': sidebar_ads,
        'sort': sort,
        'media': media,
        'verification': verification,
        'total_news': Post.objects.filter(
            status='published', post_type__in=['news', 'user_news']
        ).count(),
        'title': 'Online News',
    }
    return render(request, 'news/online_news.html', context)

# ----------------------------------------------------------------
#  POST DETAIL  —  the article reader
# ----------------------------------------------------------------
def post_detail(request, post_id):
    """
    Single article view.
    - Logged in: full content.
    - Guest: preview + signup gate.
    """
    post = get_object_or_404(
        Post.objects.select_related('category', 'author'),
        id=post_id,
    )

    # Only show published content to non-staff
    if post.status != 'published' and not (request.user.is_staff):
        return render(request, 'news/not_available.html', {
            'title': 'Not available',
        }, status=404)

    # Increment views
    Post.objects.filter(pk=post.pk).update(views=F('views') + 1)
    post.refresh_from_db(fields=['views'])

    # Guest gate
    is_guest = not request.user.is_authenticated

    # Process media (full for logged-in, skip for guests to save bandwidth)
    if is_guest:
        media = {'videos': [], 'audios': [], 'has_video': False, 'has_audio': False,
                 'video_count': 0, 'audio_count': 0}
        comments = []
        related_posts = []
        preview_content = post.content[:400] if post.content else ''
    else:
        try:
            media = MediaProcessor(post).process()
        except Exception as e:
            logger.exception(f"Media processing failed for post {post.id}: {e}")
            media = {'videos': [], 'audios': [], 'has_video': False, 'has_audio': False,
                     'video_count': 0, 'audio_count': 0}

        related_posts = Post.objects.filter(
            status='published',
            category=post.category,
        ).exclude(id=post.id).order_by('-published_at')[:5] if post.category else []

        try:
            comments = Comment.objects.filter(
                post=post,
                parent__isnull=True,
                is_active=True,
            ).select_related(
                'user', 'user__profile'
            ).prefetch_related(
                Prefetch('replies', queryset=Comment.objects.filter(is_active=True).select_related('user', 'user__profile').order_by('created_at'))
            ).order_by('-created_at')
        except Exception:
            comments = []

        preview_content = post.content

    context = {
        'post': post,
        'media': media,
        'related_posts': related_posts,
        'comments': comments,
        'is_guest': is_guest,
        'preview_content': preview_content,
        'full_content': post.content,
        'title': post.title,
        'meta_description': post.meta_description or (post.content[:160] if post.content else ''),
        'meta_image': post.image_url or (post.image.url if post.image else ''),
    }
    return render(request, 'news/post_detail.html', context)


# ----------------------------------------------------------------
#  CATEGORY VIEW  —  posts in one category
# ----------------------------------------------------------------
def category_view(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    posts = Post.objects.filter(
        status='published', category=category
    ).select_related('author').order_by('-published_at')

    paginator = Paginator(posts, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'news/category.html', {
        'category': category,
        'posts': page_obj,
        'page_obj': page_obj,
        'title': category.name,
    })