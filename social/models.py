from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Comment(models.Model):
    post = models.ForeignKey('news.Post', on_delete=models.CASCADE, related_name='comments')
    image = models.ImageField(upload_to='comment_images/', blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    likes = models.ManyToManyField(User, related_name='liked_comments', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Comment by {self.user.username} on {self.post.title[:50]}"

    def like_count(self):
        return self.likes.count()


class Repost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reposts')
    original_post = models.ForeignKey('news.Post', on_delete=models.CASCADE, related_name='repost_instances')
    content = models.TextField(blank=True, help_text="Optional comment when reposting")
    created_at = models.DateTimeField(auto_now_add=True)
    reposts = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['user', 'original_post']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} reposted {self.original_post.title}"


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('follow', 'Follow'),
        ('mention', 'Mention'),
        ('post', 'New Post'),
        ('reply', 'Reply'),
        ('ad_approval', 'Ad Approval'),
        ('business_verification', 'Business Verification'),
        ('group_invite', 'Group Invite'),
        ('group_post_approved', 'Group Post Approved'),
        ('group_post_rejected', 'Group Post Rejected'),
        ('news_submitted', 'News Submitted'),
        ('news_approved', 'News Approved'),
        ('news_rejected', 'News Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    message = models.CharField(max_length=500)
    post = models.ForeignKey('news.Post', on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey('social.Comment', on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notification_type} notification for {self.user.username}"