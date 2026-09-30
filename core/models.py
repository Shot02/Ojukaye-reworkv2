from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from decimal import Decimal


class SystemSettings(models.Model):
    """System-wide settings controlled by admin"""

    # News verification settings
    auto_approve_threshold = models.FloatField(default=0.8, help_text="AI score threshold for auto-approval (0.0-1.0)")
    require_manual_review_for_fake = models.BooleanField(default=True, help_text="Require manual review for posts marked as fake")
    notify_admin_on_submission = models.BooleanField(default=True)
    notify_user_on_approval = models.BooleanField(default=True)

    # Source reputation settings
    trusted_sources = models.TextField(blank=True, help_text="Comma-separated list of trusted news sources")
    blocked_sources = models.TextField(blank=True, help_text="Comma-separated list of blocked sources")

    # AI & Automation Settings
    auto_verify_news = models.BooleanField(default=True, help_text='Automatically verify news articles using AI')
    auto_post_verified_news = models.BooleanField(default=False, help_text='Automatically post verified news to online news page')
    auto_delete_fake_news = models.BooleanField(default=False, help_text='Automatically delete/archive news detected as fake')
    verification_threshold = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text='Minimum confidence score (0-1) for auto-approval'
    )
    min_publish_threshold = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text='Minimum score to publish (without "Verified" badge)'
    )
    verification_schedule = models.CharField(
        max_length=20,
        choices=[
            ('hourly', 'Hourly'),
            ('every_6_hours', 'Every 6 Hours'),
            ('every_12_hours', 'Every 12 Hours'),
            ('daily', 'Daily'),
            ('manual', 'Manual Only'),
        ],
        default='daily',
        help_text='How often to run automatic verification'
    )
    max_posts_to_verify = models.IntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text='Maximum number of posts to verify per batch'
    )

    # News Fetching Settings
    enable_auto_fetch = models.BooleanField(
        default=True,
        help_text='Automatically fetch news from RSS feeds'
    )
    fetch_schedule = models.CharField(
        max_length=20,
        choices=[
            ('hourly', 'Hourly'),
            ('every_3_hours', 'Every 3 Hours'),
            ('every_6_hours', 'Every 6 Hours'),
            ('daily', 'Daily'),
            ('manual', 'Manual Only'),
        ],
        default='daily'
    )
    max_news_per_fetch = models.IntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(200)]
    )

    # Auto-fetch scheduler
    auto_fetch_interval = models.CharField(
        max_length=20,
        choices=[
            ('30min', 'Every 30 minutes'),
            ('1h', 'Every 1 hour'),
            ('3h', 'Every 3 hours'),
            ('6h', 'Every 6 hours'),
            ('12h', 'Every 12 hours'),
            ('24h', 'Every 24 hours'),
        ],
        default='6h',
        help_text='How often to auto-fetch news'
    )
    auto_fetch_last_run = models.DateTimeField(null=True, blank=True)
    auto_fetch_next_run = models.DateTimeField(null=True, blank=True)

    # Post & Content Settings
    enable_guest_access = models.BooleanField(default=True, help_text='Allow non-logged-in users to view content')
    max_posts_per_day = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text='Maximum posts per user per day'
    )
    require_post_approval = models.BooleanField(default=True, help_text='Require admin approval for user posts')
    max_post_length = models.IntegerField(
        default=10000,
        validators=[MinValueValidator(100)],
        help_text='Maximum characters per post'
    )
    max_image_size = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text='Maximum image size in MB'
    )
    allowed_image_types = models.CharField(
        max_length=200,
        default='jpg,jpeg,png,gif,webp',
        help_text='Comma-separated list of allowed image formats'
    )

    # User Settings
    allow_registrations = models.BooleanField(default=True, help_text='Allow new user registrations')
    require_email_verification = models.BooleanField(default=False, help_text='Require email verification for new accounts')
    default_user_role = models.CharField(
        max_length=20,
        choices=[
            ('user', 'User'),
            ('contributor', 'Contributor'),
            ('editor', 'Editor'),
        ],
        default='user'
    )

    # Advertisement Settings
    max_ads_per_business = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text='Maximum active ads per business'
    )
    banner_rotation_interval = models.IntegerField(
        default=30,
        validators=[MinValueValidator(5)],
        help_text='Banner rotation interval in seconds'
    )
    ad_approval_required = models.BooleanField(default=True, help_text='Require admin approval for new ads')
    min_ad_budget = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1000.00'),
        validators=[MinValueValidator(Decimal('100.00'))],
        help_text='Minimum budget per advertisement'
    )
    ad_impression_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('0.0010'),
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text='Cost per impression (in NGN)'
    )
    ad_click_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('0.0500'),
        validators=[MinValueValidator(Decimal('0.0100'))],
        help_text='Cost per click (in NGN)'
    )

    # Group Settings
    allow_group_creation = models.BooleanField(default=True, help_text='Allow users to create groups')
    max_groups_per_user = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text='Maximum groups a user can create'
    )
    min_members_for_public_group = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text='Minimum members required to become a public group'
    )
    require_group_approval = models.BooleanField(default=False, help_text='Require admin approval for new groups')

    # Trending & Analytics
    trending_calculation_interval = models.IntegerField(
        default=6,
        validators=[MinValueValidator(1)],
        help_text='Trending calculation interval in hours'
    )
    trending_time_window = models.IntegerField(
        default=48,
        validators=[MinValueValidator(1)],
        help_text='Time window for trending posts in hours'
    )
    engagement_weight_like = models.FloatField(default=1.0, help_text='Weight multiplier for likes in trending calculation')
    engagement_weight_comment = models.FloatField(default=2.0, help_text='Weight multiplier for comments in trending calculation')
    engagement_weight_share = models.FloatField(default=3.0, help_text='Weight multiplier for shares in trending calculation')
    engagement_weight_view = models.FloatField(default=0.01, help_text='Weight multiplier for views in trending calculation')

    # Cache & Performance
    cache_timeout = models.IntegerField(
        default=300,
        validators=[MinValueValidator(0)],
        help_text='Cache timeout in seconds'
    )
    compress_images = models.BooleanField(default=True, help_text='Automatically compress uploaded images')

    # Maintenance
    maintenance_mode = models.BooleanField(default=False, help_text='Put site in maintenance mode')
    maintenance_message = models.TextField(
        default='Site is under maintenance. Please check back soon.',
        blank=True
    )
    allow_admin_during_maintenance = models.BooleanField(default=True, help_text='Allow admin access during maintenance')

    # SEO Settings
    meta_description = models.TextField(blank=True, help_text='Default meta description for SEO')
    meta_keywords = models.TextField(blank=True, help_text='Default meta keywords for SEO')
    robots_txt = models.TextField(
        default='User-agent: *\nDisallow: /admin/\nDisallow: /private/\nAllow: /\nSitemap: /sitemap.xml',
        blank=True
    )

    # Social Media Links
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    telegram_url = models.URLField(blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)

    # Contact Information
    contact_email = models.EmailField(blank=True)
    support_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    # Notification Settings
    enable_email_notifications = models.BooleanField(default=True)
    enable_push_notifications = models.BooleanField(default=False)
    notify_admin_on_new_post = models.BooleanField(default=True)
    notify_admin_on_new_user = models.BooleanField(default=True)
    notify_admin_on_fake_news = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_settings_updates'
    )

    class Meta:
        verbose_name_plural = "System Settings"

    def save(self, *args, **kwargs):
        if not self.pk and SystemSettings.objects.exists():
            existing = SystemSettings.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)

    def __str__(self):
        return f"System Settings (Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M')})"

    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(pk=1)
        return settings

    def get_trusted_sources_list(self):
        if self.trusted_sources:
            return [s.strip() for s in self.trusted_sources.split(',') if s.strip()]
        return []

    def get_blocked_sources_list(self):
        if self.blocked_sources:
            return [s.strip() for s in self.blocked_sources.split(',') if s.strip()]
        return []

    def get_allowed_image_types_list(self):
        return [t.strip().lower() for t in self.allowed_image_types.split(',') if t.strip()]

    def is_ai_verification_active(self):
        return self.auto_verify_news

    def should_auto_post(self):
        return self.auto_verify_news and self.auto_post_verified_news


class NewsletterSubscriber(models.Model):
    """Newsletter email subscribers."""
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=50, blank=True, help_text='Where they signed up')

    class Meta:
        ordering = ['-subscribed_at']
        verbose_name = 'Newsletter subscriber'
        verbose_name_plural = 'Newsletter subscribers'

    def __str__(self):
        return self.email