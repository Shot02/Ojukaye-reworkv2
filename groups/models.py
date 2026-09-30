from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


class Group(models.Model):
    GROUP_TYPES = [
        ('public', 'Public - Anyone can join'),
        ('private', 'Private - Approval required'),
        ('secret', 'Secret - Invitation only'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    group_type = models.CharField(max_length=20, choices=GROUP_TYPES, default='public')

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_groups')
    admins = models.ManyToManyField(User, related_name='administered_groups', blank=True)
    moderators = models.ManyToManyField(User, related_name='moderated_groups', blank=True)

    allow_member_posts = models.BooleanField(default=True)
    require_post_approval = models.BooleanField(default=False)

    cover_image = models.ImageField(upload_to='groups/covers/', blank=True, null=True)
    icon = models.ImageField(upload_to='groups/icons/', blank=True, null=True)

    member_count = models.PositiveIntegerField(default=0)
    post_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def update_member_count(self):
        self.member_count = self.members.count()
        self.save(update_fields=['member_count'])

    def update_post_count(self):
        self.post_count = self.group_posts.count()
        self.save(update_fields=['post_count'])


class GroupMember(models.Model):
    ROLE_CHOICES = [
        ('member', 'Member'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_banned = models.BooleanField(default=False)
    banned_at = models.DateTimeField(null=True, blank=True)
    banned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='banned_members'
    )

    class Meta:
        unique_together = ['group', 'user']

    def __str__(self):
        return f"{self.user.username} in {self.group.name}"


class GroupPost(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='posts')
    post = models.ForeignKey('news.Post', on_delete=models.CASCADE, related_name='group_posts')
    posted_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['group', 'post']

    def __str__(self):
        return f"{self.post.title} in {self.group.name}"