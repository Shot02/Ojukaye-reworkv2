from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class Advertisement(models.Model):
    """Advertisement model."""

    AD_TYPES = [
        ('banner', 'Banner Ad'),
        ('sponsored_post', 'Sponsored Post'),
        ('sidebar', 'Sidebar Ad'),
        ('in_feed', 'In-Feed Ad'),
    ]

    AD_STATUS = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    business = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='advertisements',
        null=True,
        blank=True,
        help_text='Leave empty for house ads (owned by Ojukaye)'
    )

    ad_type = models.CharField(max_length=20, choices=AD_TYPES, default='banner')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='ads/', blank=True, null=True)
    image_url = models.URLField(max_length=1000, blank=True)
    target_url = models.URLField(max_length=1000)

    # Budget & Duration
    budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()

    # Pricing
    cost_per_impression = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_per_click = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Targeting
    target_categories = models.ManyToManyField(
        'news.Category',
        blank=True,
        related_name='advertisements'
    )
    target_locations = models.CharField(max_length=500, blank=True)
    target_keywords = models.CharField(max_length=500, blank=True)

    # Status & Approval
    status = models.CharField(max_length=20, choices=AD_STATUS, default='pending')
    is_active = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_ads'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Performance tracking
    max_clicks = models.IntegerField(default=0)
    max_impressions = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Advertisement'
        verbose_name_plural = 'Advertisements'

    def __str__(self):
        owner = self.business.username if self.business else 'House'
        return f"{self.title} ({owner})"

    @property
    def clicks(self):
        return self.analytics.aggregate(total=models.Sum('clicks'))['total'] or 0

    @property
    def impressions(self):
        return self.analytics.aggregate(total=models.Sum('impressions'))['total'] or 0

    @property
    def ctr(self):
        imp = self.impressions
        if imp == 0:
            return 0.0
        return round((self.clicks / imp) * 100, 2)

    @property
    def is_live(self):
        now = timezone.now()
        return (
            self.status in ('active', 'approved') and
            self.is_active and
            self.start_date <= now <= self.end_date and
            (self.max_clicks == 0 or self.clicks < self.max_clicks) and
            (self.max_impressions == 0 or self.impressions < self.max_impressions)
        )

    def remaining_budget(self):
        return self.budget - self.spent

    def days_remaining(self):
        if self.end_date < timezone.now():
            return 0
        return (self.end_date - timezone.now()).days


class AdAnalytics(models.Model):
    """Daily analytics for an advertisement."""
    advertisement = models.ForeignKey(
        Advertisement,
        on_delete=models.CASCADE,
        related_name='analytics'
    )
    date = models.DateField(default=timezone.now)

    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    ctr = models.FloatField(default=0)
    cpc = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        unique_together = ['advertisement', 'date']
        verbose_name = 'Ad Analytics'
        verbose_name_plural = 'Ad Analytics'

    def __str__(self):
        return f"{self.advertisement.title} - {self.date}"

    def update_metrics(self):
        if self.impressions > 0:
            self.ctr = (self.clicks / self.impressions) * 100
        if self.clicks > 0:
            self.cpc = self.cost / self.clicks
        self.save()