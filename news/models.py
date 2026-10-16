from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from .validators import validate_video_file

class Category(models.Model):
    """Category model for posts"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='children'
    )
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    color = models.CharField(max_length=20, default='#3b82f6')
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    cached_post_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def get_post_count(self):
        if self.cached_post_count == 0:
            count = self.posts.filter(status='published').count()
            self.cached_post_count = count
            self.save(update_fields=['cached_post_count'])
        return self.cached_post_count

    def update_post_count(self):
        self.cached_post_count = self.posts.filter(status='published').count()
        self.save(update_fields=['cached_post_count'])

    def get_absolute_url(self):
        return reverse('news:category', args=[self.slug])


class Post(models.Model):
    POST_TYPES = [
        ('discussion', 'Discussion'),
        ('business', 'Business'),
        ('user_news', 'User News'),
        ('news', 'Auto-Fetched News'),
        ('profile_post', 'Profile Post'),
        ('sponsored', 'Sponsored Post'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('featured', 'Featured'),
        ('archived', 'Archived'),
    ]

    PRIVACY_CHOICES = [
        ('public', 'Public - Everyone can view'),
        ('followers', 'Followers Only - Only my followers can view'),
        ('private', 'Private - Only me'),
        ('specific', 'Specific Followers - Select specific followers'),
    ]

    # Basic Information
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    post_type = models.CharField(max_length=20, choices=POST_TYPES, default='discussion')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts'
    )

    # Privacy Settings
    privacy = models.CharField(max_length=20, choices=PRIVACY_CHOICES, default='public')
    allowed_viewers = models.ManyToManyField(
        User,
        blank=True,
        related_name='can_view_posts',
        help_text='Specific followers who can view this post (for privacy="specific")'
    )

    # Source Information (for news posts)
    source_url = models.URLField(max_length=1000, blank=True, null=True)
    source_name = models.CharField(max_length=200, blank=True)

    # External News Information (for auto-fetched news)
    external_source = models.CharField(max_length=200, blank=True)
    external_url = models.URLField(max_length=1000, blank=True)
    external_id = models.CharField(max_length=200, blank=True, null=True, unique=True)
    is_auto_fetched = models.BooleanField(default=False)
    original_published_at = models.DateTimeField(null=True, blank=True)

    # News Submission & Approval Workflow
    is_news_submission = models.BooleanField(default=False)
    submission_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('flagged', 'Flagged for Review'),
        ],
        default='pending'
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_news'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    # AI Verification Fields
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ('unverified', 'Unverified'),
            ('pending', 'Pending AI'),
            ('likely_legit', 'Likely Legit'),
            ('verified', 'Verified'),
            ('fake', 'Fake News'),
            ('questionable', 'Questionable'),
        ],
        default='unverified'
    )
    verification_score = models.FloatField(default=0.0)
    verification_details = models.JSONField(default=dict, blank=True)
    verification_method = models.CharField(max_length=50, default='manual')
    is_verified = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)

    # Source Reputation
    source_reputation_score = models.FloatField(default=0.0)
    source_trust_level = models.CharField(
        max_length=20,
        choices=[
            ('unknown', 'Unknown'),
            ('trusted', 'Trusted'),
            ('questionable', 'Questionable'),
            ('untrusted', 'Untrusted'),
        ],
        default='unknown'
    )
    # Geographic tagging
    country = models.CharField(
        max_length=2,
        blank=True,
        default='',
        help_text='ISO 3166-1 alpha-2 country code (e.g. NG for Nigeria)',
    )
    # Media Content
    image = models.ImageField(upload_to='post_images/', blank=True, null=True)
    image_url = models.URLField(max_length=1000, blank=True, null=True)

    # User-uploaded video file (optional — use video_urls for external links)
    video = models.FileField(
        upload_to='post_videos/',
        blank=True,
        null=True,
        validators=[validate_video_file],
        help_text='Upload an MP4, WebM, or MOV file (max 100MB)',
    )
    video_urls = models.JSONField(null=True, blank=True, default=list)
    audio_urls = models.JSONField(null=True, blank=True, default=list)
    has_media = models.BooleanField(default=False)

    # Special Content Types
    is_sponsored = models.BooleanField(default=False)
    is_banner = models.BooleanField(default=False)
    profile_only = models.BooleanField(default=False)
    advertisement = models.ForeignKey(
        'ads.Advertisement',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts'
    )

    # Banner-specific fields
    banner_expires_at = models.DateTimeField(null=True, blank=True)
    banner_priority = models.IntegerField(default=0)
    banner_clicks = models.PositiveIntegerField(default=0)
    banner_impressions = models.PositiveIntegerField(default=0)

    # Group association
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='group_posts'
    )

    # Interaction Settings
    allow_comments = models.BooleanField(default=True)
    allow_sharing = models.BooleanField(default=True)

    # Statistics
    views = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    repost_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    share_count = models.PositiveIntegerField(default=0)

    # Engagement & Trending
    engagement_score = models.FloatField(default=0.0)
    last_engagement_update = models.DateTimeField(auto_now=True)
    is_featured = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)

    # SEO
    meta_description = models.TextField(blank=True)
    keywords = models.CharField(max_length=500, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(default=timezone.now)

    # Many-to-Many Relationships
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    bookmarks = models.ManyToManyField(User, related_name='bookmarked_posts', blank=True)

    def save(self, *args, **kwargs):
        # Auto-flag external articles as news
        if self.external_id or self.external_url or self.external_source:
            if self.post_type != 'user_news':
                self.is_auto_fetched = True
                if self.post_type == 'discussion':
                    self.post_type = 'news'

        if self.post_type == 'profile_post':
            self.profile_only = True
            self.category = None

        if self.post_type == 'sponsored' and self.advertisement:
            self.is_sponsored = True

        # Media flag — now also accounts for uploaded video
        if self.video_urls or self.audio_urls or self.video:
            self.has_media = True

        if self.status in ['published', 'featured'] and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
            models.Index(fields=['status']),
            models.Index(fields=['post_type']),
            models.Index(fields=['category']),
            models.Index(fields=['is_auto_fetched']),
            models.Index(fields=['is_sponsored']),
            models.Index(fields=['profile_only']),
            models.Index(fields=['verification_status']),
            models.Index(fields=['submission_status']),
        ]

    def __str__(self):
        return self.title[:100]

    def like_count(self):
        return self.likes.count()

    def comment_count(self):
        return self.comments.filter(is_active=True).count()

    def bookmark_count(self):
        return self.bookmarks.count()

    def update_engagement_score(self):
        self.comments_count = self.comments.filter(is_active=True).count()
        like_weight = 1
        comment_weight = 3
        repost_weight = 5
        view_weight = 0.01
        self.engagement_score = (
            self.likes.count() * like_weight +
            self.comments_count * comment_weight +
            self.repost_count * repost_weight +
            self.views * view_weight
        )
        self.last_engagement_update = timezone.now()
        self.save(update_fields=['engagement_score', 'last_engagement_update', 'comments_count'])

    def save(self, *args, **kwargs):
        # Auto-flag external articles as news
        if self.external_id or self.external_url or self.external_source:
            # BUT don't overwrite user_news
            if self.post_type != 'user_news':
                self.is_auto_fetched = True
                if self.post_type == 'discussion':
                    self.post_type = 'news'

        # Profile posts
        if self.post_type == 'profile_post':
            self.profile_only = True
            self.category = None

        # Sponsored flag
        if self.post_type == 'sponsored' and self.advertisement:
            self.is_sponsored = True

        # Media flag
        if self.video_urls or self.audio_urls:
            self.has_media = True

        # Published timestamp
        if self.status in ['published', 'featured'] and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('news:post_detail', args=[str(self.id)])


class FetchLog(models.Model):
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class FetchSchedule(models.Model):
    FETCH_TYPES = [
        ('auto', 'Automatic'),
        ('manual', 'Manual'),
        ('custom', 'Custom'),
    ]

    scheduled_time = models.DateTimeField()
    fetch_type = models.CharField(max_length=20, choices=FETCH_TYPES, default='auto')
    days = models.IntegerField(default=1)
    limit = models.IntegerField(default=50)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_time']

    def __str__(self):
        return f"{self.fetch_type} @ {self.scheduled_time:%Y-%m-%d %H:%M}"
    
class NewsSource(models.Model):
    """A news source (RSS feed or API) that the fetcher can pull from."""
    SOURCE_TYPES = [
        ('rss', 'RSS Feed'),
        ('api', 'API'),
    ]
    STATUS_CHOICES = [
        ('unknown', 'Not Tested'),
        ('working', 'Working'),
        ('broken', 'Broken'),
        ('slow', 'Slow'),
    ]

    name = models.CharField(max_length=100)
    url = models.URLField(max_length=1000, unique=True)
    source_type = models.CharField(max_length=10, choices=SOURCE_TYPES, default='rss')
    category_hint = models.CharField(max_length=50, blank=True, help_text='e.g. general, tech, politics')
    country_hint = models.CharField(max_length=50, blank=True, help_text='e.g. Nigeria, World')
    language = models.CharField(max_length=10, default='en')

    is_active = models.BooleanField(default=True)
    is_trusted = models.BooleanField(default=False, help_text='Mark as trusted source for AI scoring')

    # Health tracking
    last_tested = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unknown')
    last_error = models.TextField(blank=True)
    last_response_ms = models.PositiveIntegerField(null=True, blank=True)

    # Stats
    total_articles_fetched = models.PositiveIntegerField(default=0)
    last_article_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', 'name']
        verbose_name = 'News Source'
        verbose_name_plural = 'News Sources'

    def __str__(self):
        return f"{self.name} ({self.url[:50]})"

    @property
    def status_color(self):
        return {
            'working': 'success',
            'broken': 'danger',
            'slow': 'warning',
            'unknown': 'secondary',
        }.get(self.last_status, 'secondary')