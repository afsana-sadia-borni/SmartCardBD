from django import forms

from django.conf import settings

from accounts.constants import DISTRICT_CHOICES
from accounts.forms import UpazilaMixin
from accounts.models import get_profile, phone_validator

from . import payments
from .models import Order, ReturnRequest


class CheckoutForm(UpazilaMixin, forms.Form):
    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(
        max_length=15, validators=[phone_validator],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01XXXXXXXXX'}),
    )
    district = forms.ChoiceField(
        choices=[('', 'Select district')] + DISTRICT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select js-district', 'id': 'id_district'}),
    )
    upazila = forms.CharField(
        max_length=60, label='Upazila / Thana', widget=forms.TextInput(attrs={'class': 'form-select js-upazila'}),
    )
    area = forms.CharField(
        max_length=100, label='Area', widget=forms.TextInput(attrs={'class': 'form-control',
                                                                    'placeholder': 'e.g. Road 5, Block C'}),
    )
    address_line = forms.CharField(
        max_length=255, label='Address',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'House, road, village'}),
    )
    note = forms.CharField(
        required=False, label='Order note (optional)',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': 'e.g. Please call before delivery'}),
    )
    gift_wrap = forms.BooleanField(required=False, label='Gift wrap this order')
    use_points = forms.BooleanField(required=False, label='Use my reward points')
    payment_method = forms.ChoiceField(
        choices=Order.PaymentMethod.choices, initial=Order.PaymentMethod.COD, widget=forms.RadioSelect,
    )
    save_address = forms.BooleanField(required=False, initial=True, label='Save this address to my account')

    SHIPPING_FIELDS = ['full_name', 'email', 'phone', 'district', 'upazila', 'area', 'address_line', 'note']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['gift_wrap'].help_text = f'Wrapped with a card, +৳{settings.GIFT_WRAP_PRICE}'
        self.points = 0
        if user and user.is_authenticated:
            self.points = get_profile(user).points
        if self.points < settings.POINTS_REDEEM_BLOCK:
            del self.fields['use_points']
        if not (user and user.is_authenticated):
            del self.fields['save_address']
        if not payments.is_configured():
            self.fields['payment_method'].choices = [
                c for c in Order.PaymentMethod.choices if c[0] != Order.PaymentMethod.SSLCOMMERZ
            ]

    def shipping_data(self):
        return {name: self.cleaned_data[name] for name in self.SHIPPING_FIELDS}


class TrackOrderForm(forms.Form):
    order_number = forms.CharField(max_length=20, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'e.g. SCB261101-A1B2C3'}))
    phone = forms.CharField(max_length=15, validators=[phone_validator], widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': '01XXXXXXXXX'}))


class ReturnRequestForm(forms.ModelForm):
    MAX_PHOTO_MB = 5

    class Meta:
        model = ReturnRequest
        fields = ['reason', 'details', 'photo']
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'details': forms.Textarea(attrs={'class': 'form-control', 'rows': 4,
                                             'placeholder': 'Tell us what went wrong'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > self.MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(f'Photo must be smaller than {self.MAX_PHOTO_MB} MB.')
        return photo
