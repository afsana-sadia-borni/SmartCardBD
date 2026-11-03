from django import forms
from django.core.exceptions import ValidationError


class HoneypotMixin:
    """Adds a hidden 'website' field. People never see it; bots that fill every field get rejected."""

    honeypot_field = 'website'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.honeypot_field] = forms.CharField(
            required=False, label='Leave this field empty',
            widget=forms.TextInput(attrs={'autocomplete': 'off', 'tabindex': '-1', 'class': 'hp-field'}),
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get(self.honeypot_field):
            raise ValidationError('Your submission looks automated. Please try again.')
        return cleaned
