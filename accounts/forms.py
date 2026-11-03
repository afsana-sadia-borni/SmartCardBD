from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms

from core.forms import HoneypotMixin
from core.middleware import REFERRAL_SESSION_KEY

from .geo import is_valid_upazila
from .models import Address, CustomerProfile, Subscriber


class UpazilaMixin:
    """Check the chosen upazila belongs to the chosen district."""

    def clean(self):
        cleaned = super().clean()
        district, upazila = cleaned.get('district'), cleaned.get('upazila')
        if district and upazila and not is_valid_upazila(district, upazila):
            self.add_error('upazila', 'Please choose an upazila / thana in the selected district.')
        return cleaned


class AddressForm(UpazilaMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = ['full_name', 'phone', 'district', 'upazila', 'area', 'address_line', 'is_default']
        labels = {'is_default': 'Make this my default address', 'upazila': 'Upazila / Thana', 'area': 'Area'}
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01XXXXXXXXX'}),
            'district': forms.Select(attrs={'class': 'form-select js-district'}),
            'upazila': forms.TextInput(attrs={'class': 'form-select js-upazila'}),
            'area': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Road 5, Block C'}),
            'address_line': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'House, road, village'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['upazila'].required = True


class SignupForm(HoneypotMixin, AllauthSignupForm):
    referral_code = forms.CharField(
        max_length=20, required=False, label='Referral code (optional)',
        widget=forms.TextInput(attrs={'placeholder': 'e.g. SCB1A2B3C'}),
    )

    def clean_referral_code(self):
        code = self.cleaned_data['referral_code'].strip().upper()
        if code and not CustomerProfile.objects.filter(referral_code=code).exists():
            raise forms.ValidationError('This referral code is not valid.')
        return code

    def save(self, request):
        user = super().save(request)
        code = self.cleaned_data.get('referral_code') or request.session.pop(REFERRAL_SESSION_KEY, '')
        referrer = CustomerProfile.objects.filter(referral_code=code.upper()).exclude(user=user).first() if code else None
        if referrer:
            CustomerProfile.objects.filter(user=user).update(referred_by=referrer.user)
        return user


class NewsletterForm(HoneypotMixin, forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ['email']
