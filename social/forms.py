from django import forms
from news.models import Post, Category


class DiscussionForm(forms.ModelForm):
    """Free-form social post."""
    class Meta:
        model = Post
        fields = ['title', 'content', 'category', 'image', 'video']
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'Give it a title (optional)',
                'maxlength': 200,
            }),
            'content': forms.Textarea(attrs={
                'placeholder': "What's on your mind?",
                'rows': 6,
                'maxlength': 5000,
            }),
            'category': forms.Select(attrs={}),
            'image': forms.FileInput(attrs={}),
            'video': forms.FileInput(attrs={'accept': 'video/mp4,video/webm,video/quicktime'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False
        self.fields['category'].required = False
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['category'].empty_label = '-- No category --'
        self.fields['image'].required = False
        self.fields['video'].required = False


class NewsSubmissionForm(forms.ModelForm):
    """User-submitted news — must have a source URL."""
    source_url = forms.URLField(
        required=True,
        widget=forms.URLInput(attrs={
            'placeholder': 'https://example.com/article',
        }),
        help_text="The original article link. AI will verify it.",
    )

    video_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'placeholder': 'https://www.youtube.com/watch?v=...',
        }),
        help_text="Optional. Paste a YouTube, Vimeo, or direct video link.",
    )

    class Meta:
        model = Post
        fields = ['title', 'source_url', 'source_name', 'content', 'category', 'image']
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'News headline',
                'maxlength': 200,
            }),
            'source_name': forms.TextInput(attrs={
                'placeholder': 'e.g. BBC News, Premium Times',
            }),
            'content': forms.Textarea(attrs={
                'placeholder': 'Paste the article summary or your own explanation…',
                'rows': 6,
                'maxlength': 10000,
            }),
            'category': forms.Select(attrs={}),
            'image': forms.FileInput(attrs={}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['category'].empty_label = '-- Select a category --'
        self.fields['category'].required = True
        self.fields['source_name'].required = False
        self.fields['image'].required = False

    def clean_source_url(self):
        url = self.cleaned_data.get('source_url', '').strip()
        if not url:
            raise forms.ValidationError('Source URL is required for news posts.')
        return url

    def clean_video_url(self):
        """Optional field, but if provided, must be a valid http(s) URL."""
        url = (self.cleaned_data.get('video_url') or '').strip()
        if not url:
            return ''
        if not url.startswith(('http://', 'https://')):
            raise forms.ValidationError('Video URL must start with http:// or https://')
        return url

    def clean(self):
        cleaned = super().clean()
        content = cleaned.get('content', '') or ''
        if len(content.strip()) < 30:
            raise forms.ValidationError('Please write at least 30 characters of content for news posts.')
        return cleaned


class ProfilePostForm(forms.ModelForm):
    """Personal profile-only post."""
    class Meta:
        model = Post
        fields = ['content', 'image', 'video']
        widgets = {
            'content': forms.Textarea(attrs={
                'placeholder': "What's on your mind? (visible only on your profile)",
                'rows': 6,
                'maxlength': 3000,
            }),
            'image': forms.FileInput(attrs={}),
            'video': forms.FileInput(attrs={'accept': 'video/mp4,video/webm,video/quicktime'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['image'].required = False
        self.fields['video'].required = False