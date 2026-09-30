import logging
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db.models import F
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from news.models import Post
from accounts.models import UserActivity
from social.models import Comment, Notification
from social.forms import DiscussionForm, NewsSubmissionForm, ProfilePostForm

logger = logging.getLogger(__name__)


@login_required
def create_post(request):
    """
    Unified create-post page.
    User picks a post type via ?type=discussion|news|profile
    Default: discussion.
    """
    post_type = request.GET.get('type', 'discussion').strip()
    if post_type not in ('discussion', 'news', 'profile'):
        post_type = 'discussion'

    if request.method == 'POST':
        submitted_type = request.POST.get('post_type', post_type)
        if submitted_type not in ('discussion', 'news', 'profile'):
            submitted_type = 'discussion'
        return _handle_submission(request, submitted_type)

    # GET: build the right form
    if post_type == 'news':
        form = NewsSubmissionForm()
    elif post_type == 'profile':
        form = ProfilePostForm()
    else:
        form = DiscussionForm()

    return render(request, 'social/create_post.html', {
        'form': form,
        'post_type': post_type,
        'title': 'Create Post',
    })


def _handle_submission(request, post_type):
    """Handle the actual save. Returns a redirect."""

    # ---- pick form class ----
    if post_type == 'news':
        form = NewsSubmissionForm(request.POST, request.FILES)
    elif post_type == 'profile':
        form = ProfilePostForm(request.POST, request.FILES)
    else:
        form = DiscussionForm(request.POST, request.FILES)

    if not form.is_valid():
        # Show form again with errors
        return render(request, 'social/create_post.html', {
            'form': form,
            'post_type': post_type,
            'title': 'Create Post',
        })

    with transaction.atomic():
        post = form.save(commit=False)
        post.author = request.user
        post.allow_comments = True
        post.allow_sharing = True

        # ---- set type-specific fields ----
        if post_type == 'news':
            post.post_type = 'user_news'
            post.is_news_submission = True
            post.status = 'draft'  # will become published if verified
            post.submission_status = 'pending'
            post.external_url = post.source_url or ''
            post.external_source = post.source_name or _extract_domain(post.source_url)
        elif post_type == 'profile':
            post.post_type = 'profile_post'
            post.privacy = 'private'
            post.profile_only = True
            post.status = 'published'
            if not post.published_at:
                post.published_at = timezone.now()
        else:  # discussion
            post.post_type = 'discussion'
            post.status = 'published'
            if not post.published_at:
                post.published_at = timezone.now()

        # ---- handle image ----
        if form.cleaned_data.get('image'):
            post.image = form.cleaned_data['image']

        # ---- save ----
        post.save()

        # ---- run AI verification for news ----
        ai_result = None
        if post_type == 'news':
            try:
                ai_result = _verify_news_post(post)
                logger.info(f"AI verification result for post {post.id}: {ai_result}")
            except Exception as e:
                logger.exception(f"AI verification failed for post {post.id}: {e}")
                ai_result = None

        # ---- log activity ----
        try:
            UserActivity.objects.create(
                user=request.user,
                activity_type='post_created',
                post=post,
                details={'post_type': post_type, 'title': (post.title or '')[:60]},
            )
        except Exception as e:
            logger.warning(f"Could not create UserActivity: {e}")

    # ---- flash messages based on outcome ----
    if post_type == 'news' and ai_result:
        if ai_result['status'] == 'verified':
            messages.success(request, 'Your news was verified and published! ✅')
        elif ai_result['status'] == 'fake':
            messages.error(request, 'Your submission was rejected by AI: ' + ai_result.get('reason', 'low credibility'))
        else:
            messages.info(request, 'Your news was submitted for review. You\'ll be notified when it\'s approved.')
    elif post_type == 'profile':
        messages.success(request, 'Profile post created!')
    else:
        messages.success(request, 'Post created!')

    # ---- redirect ----
    if post_type == 'news':
        return redirect('accounts:profile', username=request.user.username)
    return redirect('core:home')


# ---------- helpers ----------

def _extract_domain(url):
    if not url:
        return ''
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace('www.', '')
    except Exception:
        return ''


def _verify_news_post(post):
    """
    Run AI verification with two-tier thresholds:
      score >= auto_approve_threshold → verified + published
      score >= min_publish_threshold  → published, unverified
      score >= 0.4                    → pending manual review
      score <  0.4                    → fake
    """
    from news.services.verifier import EnhancedNewsVerifier
    from core.models import SystemSettings

    settings = SystemSettings.get_settings()

    if not settings.auto_verify_news:
        post.verification_status = 'pending'
        post.submission_status = 'pending'
        post.save()
        return {'status': 'pending', 'score': 0.0, 'reason': 'AI disabled'}

    verifier = EnhancedNewsVerifier()
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

    verify_at = settings.auto_approve_threshold     # default 0.7
    publish_at = settings.min_publish_threshold     # default 0.5

    if score >= verify_at:
        # FULL VERIFY — publish with badge
        post.verification_status = 'verified'
        post.is_verified = True
        post.submission_status = 'approved'
        post.status = 'published'
        post.is_approved = True
        if not post.published_at:
            post.published_at = timezone.now()
        post.save()
        return {'status': 'verified', 'score': score, 'reason': 'Auto-verified'}

    elif score >= publish_at:
        # LIKELY LEGIT — publish without badge
        post.verification_status = 'likely_legit'
        post.is_verified = False
        post.submission_status = 'approved'
        post.status = 'published'
        post.is_approved = True
        if not post.published_at:
            post.published_at = timezone.now()
        post.save()
        return {'status': 'likely_legit', 'score': score, 'reason': 'Published (unverified)'}

    elif score >= 0.4:
        # BORDERLINE — hold for review
        post.verification_status = 'pending'
        post.submission_status = 'pending'
        post.save()

        try:
            from django.contrib.auth.models import User as AuthUser
            for staff in AuthUser.objects.filter(is_staff=True):
                Notification.objects.create(
                    user=staff,
                    notification_type='news_submitted',
                    message=f'Needs review: "{post.title[:60]}"',
                    post=post,
                )
        except Exception:
            pass
        return {'status': 'pending', 'score': score, 'reason': 'Needs manual review'}

    else:
        # FAKE — reject
        post.verification_status = 'fake'
        post.submission_status = 'rejected'
        post.rejection_reason = 'AI verification indicated low credibility.'
        post.save()

        try:
            Notification.objects.create(
                user=post.author,
                notification_type='news_rejected',
                message=f'Your submission "{post.title[:60]}" was rejected by AI.',
                post=post,
            )
        except Exception:
            pass
        return {'status': 'fake', 'score': score, 'reason': 'Low credibility'}
    
# ==============================================================
#  POST INTERACTIONS (AJAX)
# ==============================================================

@login_required
@require_POST
def toggle_like(request, post_id):
    """Like or unlike a post."""
    post = Post.objects.filter(id=post_id, status='published').first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    if request.user in post.likes.all():
        post.likes.remove(request.user)
        liked = False
    else:
        post.likes.add(request.user)
        liked = True

        # Notify the author (don't notify yourself)
        if post.author != request.user:
            try:
                Notification.objects.create(
                    user=post.author,
                    from_user=request.user,
                    notification_type='like',
                    message=f'{request.user.username} liked your post',
                    post=post,
                )
            except Exception:
                pass

    return JsonResponse({
        'success': True,
        'liked': liked,
        'like_count': post.likes.count(),
    })


@login_required
@require_POST
def toggle_bookmark(request, post_id):
    """Bookmark or un-bookmark a post."""
    post = Post.objects.filter(id=post_id, status='published').first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    if request.user in post.bookmarks.all():
        post.bookmarks.remove(request.user)
        bookmarked = False
    else:
        post.bookmarks.add(request.user)
        bookmarked = True

    return JsonResponse({
        'success': True,
        'bookmarked': bookmarked,
        'bookmark_count': post.bookmarks.count(),
    })


@login_required
@require_POST
def add_comment(request, post_id):
    """Add a comment to a post (with flat threading)."""
    post = Post.objects.filter(id=post_id, status='published').first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    content = (request.POST.get('content') or '').strip()
    parent_id = request.POST.get('parent_id') or None
    top_id = request.POST.get('top_id') or None

    if not content:
        return JsonResponse({'success': False, 'error': 'Comment cannot be empty'}, status=400)
    if len(content) > 1000:
        return JsonResponse({'success': False, 'error': 'Comment too long (max 1000 characters)'}, status=400)

    # ---- Determine the actual parent for FLAT threading ----
    # If top_id is provided, that's the top-level comment we attach to.
    # This makes all replies live under the top-level comment, no matter how deep.
    parent = None
    top_comment = None

    if top_id:
        top_comment = Comment.objects.filter(id=top_id, post=post).first()
    elif parent_id:
        # Fallback: if only parent_id was sent, walk up to find the top-level
        parent_comment = Comment.objects.filter(id=parent_id, post=post).first()
        if parent_comment:
            top_comment = parent_comment
            # walk up to the real top
            while top_comment.parent is not None:
                top_comment = top_comment.parent

    # ---- Create the comment ----
    # parent is the top-level comment (or None for a root comment)
    if top_comment:
        comment = Comment.objects.create(
            post=post,
            user=request.user,
            content=content,
            parent=top_comment,
        )
    else:
        comment = Comment.objects.create(
            post=post,
            user=request.user,
            content=content,
        )

    # Increment post comment count
    Post.objects.filter(id=post.id).update(comments_count=F('comments_count') + 1)

    # Notify post author
    if post.author != request.user:
        try:
            Notification.objects.create(
                user=post.author,
                from_user=request.user,
                notification_type='comment',
                message=f'{request.user.username} commented on your post',
                post=post,
                comment=comment,
            )
        except Exception:
            pass

    # Notify the person being replied to
    reply_target_user = None
    if parent_id:
        replied_to = Comment.objects.filter(id=parent_id).first()
        if replied_to:
            reply_target_user = replied_to.user

    if reply_target_user and reply_target_user != request.user:
        try:
            Notification.objects.create(
                user=reply_target_user,
                from_user=request.user,
                notification_type='reply',
                message=f'{request.user.username} replied to your comment',
                post=post,
                comment=comment,
            )
        except Exception:
            pass

    profile_pic = None
    if hasattr(request.user, 'profile') and request.user.profile.profile_pic:
        profile_pic = request.user.profile.profile_pic.url

    return JsonResponse({
        'success': True,
        'comment': {
            'id': comment.id,
            'content': comment.content,
            'username': request.user.username,
            'full_name': request.user.get_full_name() or request.user.username,
            'profile_pic': profile_pic,
            'created_at': comment.created_at.isoformat(),
            'top_id': top_comment.id if top_comment else comment.id,
            'is_reply': bool(top_comment),
        },
        'comment_count': post.comments.count(),
    })
    
@login_required
@require_POST
def toggle_comment_like(request, comment_id):
    """Like or unlike a comment."""
    comment = Comment.objects.filter(id=comment_id, is_active=True).first()
    if not comment:
        return JsonResponse({'success': False, 'error': 'Comment not found'}, status=404)

    if request.user in comment.likes.all():
        comment.likes.remove(request.user)
        liked = False
    else:
        comment.likes.add(request.user)
        liked = True
        # Notify the comment author
        if comment.user != request.user:
            try:
                Notification.objects.create(
                    user=comment.user,
                    from_user=request.user,
                    notification_type='like',
                    message=f'{request.user.username} liked your comment',
                    post=comment.post,
                    comment=comment,
                )
            except Exception:
                pass

    return JsonResponse({
        'success': True,
        'liked': liked,
        'like_count': comment.likes.count(),
    })


@login_required
@require_POST
def delete_comment(request, comment_id):
    """Delete a comment (author or staff only)."""
    comment = Comment.objects.filter(id=comment_id).first()
    if not comment:
        return JsonResponse({'success': False, 'error': 'Comment not found'}, status=404)

    if comment.user != request.user and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    post = comment.post
    # Soft delete — set is_active=False so replies stay intact
    comment.is_active = False
    comment.save(update_fields=['is_active'])

    # Update post comment count
    Post.objects.filter(id=post.id).update(
        comments_count=F('comments_count') - 1
    )

    return JsonResponse({
        'success': True,
        'comment_count': post.comments.filter(is_active=True).count(),
    })
    

@login_required
def notifications_view(request):
    """List all notifications for the current user."""
    # Mark all unread as read when the page is visited
    Notification.objects.filter(
        user=request.user, is_read=False
    ).update(is_read=True)

    # Now fetch the notifications
    notifications = Notification.objects.filter(
        user=request.user
    ).select_related('from_user', 'post', 'comment').order_by('-created_at')

    # Filter by type
    filter_type = request.GET.get('filter', 'all').strip()
    if filter_type == 'unread':
        notifications = notifications.filter(is_read=False)
    elif filter_type == 'mentions':
        notifications = notifications.filter(notification_type='mention')
    elif filter_type == 'follows':
        notifications = notifications.filter(notification_type='follow')
    elif filter_type == 'likes':
        notifications = notifications.filter(notification_type='like')
    elif filter_type == 'comments':
        notifications = notifications.filter(
            notification_type__in=['comment', 'reply']
        )

    # Counts for tabs
    base_qs = Notification.objects.filter(user=request.user)
    counts = {
        'all': base_qs.count(),
        'unread': base_qs.filter(is_read=False).count(),
        'mentions': base_qs.filter(notification_type='mention').count(),
        'follows': base_qs.filter(notification_type='follow').count(),
        'likes': base_qs.filter(notification_type='like').count(),
        'comments': base_qs.filter(notification_type__in=['comment', 'reply']).count(),
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(notifications, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'social/notifications.html', {
        'notifications': page_obj,
        'page_obj': page_obj,
        'filter_type': filter_type,
        'counts': counts,
        'title': 'Notifications',
    })


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Mark a single notification as read."""
    notif = Notification.objects.filter(
        id=notification_id, user=request.user
    ).first()
    if not notif:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    notif.is_read = True
    notif.save(update_fields=['is_read'])

    unread_count = Notification.objects.filter(
        user=request.user, is_read=False
    ).count()

    return JsonResponse({'success': True, 'unread_count': unread_count})


@login_required
@require_POST
def mark_all_read(request):
    """Mark all notifications for the current user as read."""
    updated = Notification.objects.filter(
        user=request.user, is_read=False
    ).update(is_read=True)

    return JsonResponse({'success': True, 'marked': updated, 'unread_count': 0})


@login_required
@require_POST
def delete_notification(request, notification_id):
    """Delete a notification."""
    notif = Notification.objects.filter(
        id=notification_id, user=request.user
    ).first()
    if not notif:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    notif.delete()
    unread_count = Notification.objects.filter(
        user=request.user, is_read=False
    ).count()

    return JsonResponse({'success': True, 'unread_count': unread_count})


@login_required
@require_GET
def notifications_count(request):
    """AJAX: get unread count for header badge."""
    count = Notification.objects.filter(
        user=request.user, is_read=False
    ).count()
    return JsonResponse({'count': count})

@login_required
@require_POST
def track_share(request, post_id):
    """Increment the share count for a post."""
    post = Post.objects.filter(id=post_id).first()
    if not post:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    Post.objects.filter(id=post.id).update(shares=F('shares') + 1)
    post.refresh_from_db(fields=['shares'])

    return JsonResponse({'success': True, 'share_count': post.shares})

@login_required
def saved_posts_view(request):
    """List all posts the current user has bookmarked."""
    from news.models import Post

    filter_type = request.GET.get('filter', 'all').strip()

    # Base queryset: posts this user bookmarked
    posts = Post.objects.filter(
        bookmarks=request.user,
        status='published',
    ).select_related('author', 'category').order_by('-published_at')

    # Filter by post type
    if filter_type == 'news':
        posts = posts.filter(post_type__in=['news', 'user_news'])
    elif filter_type == 'discussions':
        posts = posts.filter(post_type='discussion')
    elif filter_type == 'profile':
        posts = posts.filter(post_type='profile_post')

    # Counts for tabs
    base_qs = Post.objects.filter(bookmarks=request.user, status='published')
    counts = {
        'all': base_qs.count(),
        'news': base_qs.filter(post_type__in=['news', 'user_news']).count(),
        'discussions': base_qs.filter(post_type='discussion').count(),
        'profile': base_qs.filter(post_type='profile_post').count(),
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(posts, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'social/saved_posts.html', {
        'posts': page_obj,
        'page_obj': page_obj,
        'filter_type': filter_type,
        'counts': counts,
        'title': 'Saved Posts',
    })