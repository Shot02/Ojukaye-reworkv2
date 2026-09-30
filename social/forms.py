from django import forms
from news.models import Post, Category


class DiscussionForm(forms.ModelForm):
    """Free-form social post."""
    class Meta:
        model = Post
        fields = ['title', 'content', 'category', 'image']
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False
        self.fields['category'].required = False
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['category'].empty_label = '-- No category --'
        # Image upload field – not a model field, we handle it manually
        self.fields['image'].required = False


class NewsSubmissionForm(forms.ModelForm):
    """User-submitted news — must have a source URL."""
    source_url = forms.URLField(
        required=True,
        widget=forms.URLInput(attrs={
            'placeholder': 'https://example.com/article',
        }),
        help_text="The original article link. AI will verify it.",
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
        fields = ['content', 'image']
        widgets = {
            'content': forms.Textarea(attrs={
                'placeholder': "What's on your mind? (visible only on your profile)",
                'rows': 6,
                'maxlength': 3000,
            }),
            'image': forms.FileInput(attrs={}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['image'].required = False