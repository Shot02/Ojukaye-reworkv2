from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse


class UserProfile(models.Model):
    ACCOUNT_TYPES = [
        ('individual', 'Individual'),
        ('business', 'Business'),
        ('group', 'Group Account'),
        ('admin', 'Admin'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    cover_photo = models.ImageField(upload_to='cover_photos/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(max_length=1000, blank=True)
    twitter_handle = models.CharField(max_length=50, blank=True)
    
    theme_preference = models.CharField(
        max_length=20,
        choices=[
            ('default', 'Default'),
            ('original', 'Original'),
            ('dark', 'Dark'),
        ],
        default='default',
        help_text='User\'s preferred theme'
    )

    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    interests = models.TextField(blank=True, help_text="Comma separated list of interests")

    facebook_url = models.URLField(max_length=1000, blank=True)
    instagram_url = models.URLField(max_length=1000, blank=True)
    linkedin_url = models.URLField(max_length=1000, blank=True)

    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='individual')
    is_verified_business = models.BooleanField(default=False)
    ad_credits = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    business_name = models.CharField(max_length=200, blank=True)
    business_registration = models.CharField(max_length=100, blank=True)
    business_address = models.TextField(blank=True)
    business_phone = models.CharField(max_length=20, blank=True)
    business_email = models.EmailField(blank=True)
    business_website = models.URLField(max_length=1000, blank=True)

    business_verified_at = models.DateTimeField(null=True, blank=True)
    business_verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_businesses'
    )

    receive_promo_emails = models.BooleanField(default=True)
    ad_notifications = models.BooleanField(default=True)

    is_group_account = models.BooleanField(default=False)
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profile'
    )

    total_posts = models.PositiveIntegerField(default=0)
    total_comments = models.PositiveIntegerField(default=0)
    total_likes_received = models.PositiveIntegerField(default=0)
    followers_count = models.PositiveIntegerField(default=0)
    following_count = models.PositiveIntegerField(default=0)

    email_notifications = models.BooleanField(default=True)
    show_online_status = models.BooleanField(default=True)
    privacy_level = models.CharField(
        max_length=20,
        choices=[
            ('public', 'Public'),
            ('private', 'Private'),
            ('friends_only', 'Friends Only')
        ],
        default='public'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(default=timezone.now)

    def __str__(self):
        if self.account_type == 'business' and self.business_name:
            return f"{self.business_name} ({self.user.username})"
        return f"{self.user.username}'s Profile"

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username

    def update_stats(self):
        self.total_posts = self.user.posts.count()
        self.total_comments = self.user.comment_set.count()
        self.total_likes_received = self.user.posts.aggregate(
            total_likes=models.Sum('likes')
        )['total_likes'] or 0
        self.save()

    def get_interests_list(self):
        if self.interests:
            return [interest.strip() for interest in self.interests.split(',')]
        return []

    def can_submit_ads(self):
        return self.account_type == 'business' and self.is_verified_business

    def get_remaining_ad_credits(self):
        from ads.models import Advertisement
        active_ads = Advertisement.objects.filter(
            business=self.user,
            status__in=['active', 'approved'],
            is_active=True
        )
        total_budget = sum(ad.budget for ad in active_ads)
        return self.ad_credits - total_budget

    def get_absolute_url(self):
        return reverse('accounts:profile', args=[self.user.username])


class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['follower', 'following']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


class UserActivity(models.Model):
    ACTIVITY_TYPES = [
        ('post_created', 'Post Created'),
        ('comment_created', 'Comment Created'),
        ('post_liked', 'Post Liked'),
        ('post_shared', 'Post Shared'),
        ('post_saved', 'Post Saved'),
        ('post_reposted', 'Post Reposted'),
        ('profile_updated', 'Profile Updated'),
        ('followed_user', 'Followed User'),
        ('ad_submitted', 'Ad Submitted'),
        ('group_created', 'Group Created'),
        ('group_joined', 'Group Joined'),
        ('ad_approved', 'Ad Approved'),
        ('ad_rejected', 'Ad Rejected'),
        ('business_verified', 'Business Verified'),
        ('group_post_created', 'Group Post Created'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    post = models.ForeignKey(
        'news.Post',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='activities'
    )
    comment = models.ForeignKey(
        'social.Comment',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='activities'
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='target_activities'
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'User Activities'

    def __str__(self):
        return f"{self.user.username} - {self.get_activity_type_display()}"