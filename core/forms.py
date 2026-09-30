from django import forms
from core.models import SystemSettings


class SystemSettingsForm(forms.ModelForm):
    """Admin form for SystemSettings — lenient, allows partial updates."""

    class Meta:
        model = SystemSettings
        fields = '__all__'
        exclude = ['updated_by', 'created_at', 'updated_at']
        widgets = {
            'maintenance_message': forms.Textarea(attrs={'rows': 3, 'class': 'settings-input'}),
            'meta_description': forms.Textarea(attrs={'rows': 3, 'class': 'settings-input'}),
            'meta_keywords': forms.Textarea(attrs={'rows': 2, 'class': 'settings-input'}),
            'robots_txt': forms.Textarea(attrs={'rows': 5, 'class': 'settings-input'}),
            'trusted_sources': forms.Textarea(attrs={
                'rows': 3,
                'class': 'settings-input',
                'placeholder': 'premiumtimesng.com, punchng.com, vanguardngr.com'
            }),
            'blocked_sources': forms.Textarea(attrs={
                'rows': 3,
                'class': 'settings-input',
                'placeholder': 'suspicious-site.com, spamnews.com'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply consistent class to every field + make everything optional
        for name, field in self.fields.items():
            field.required = False  # KEY FIX

            if 'class' in field.widget.attrs:
                continue
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'settings-checkbox'
            else:
                field.widget.attrs['class'] = 'settings-input'

    def clean(self):
        """Only validate the fields that actually matter."""
        cleaned = super().clean()

        # Thresholds must be 0–1 if provided
        for f in ['auto_approve_threshold', 'verification_threshold']:
            val = cleaned.get(f)
            if val is not None and (val < 0 or val > 1):
                self.add_error(f, 'Value must be between 0 and 1.')

        # Decimals must be >= 0
        for f in ['min_ad_budget', 'ad_impression_rate', 'ad_click_rate']:
            val = cleaned.get(f)
            if val is not None and val < 0:
                self.add_error(f, 'Value cannot be negative.')

        return cleaned