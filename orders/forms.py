from django import forms

from accounts.constants import DISTRICT_CHOICES
from accounts.models import phone_validator

from . import payments
from .models import Order


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(
        max_length=15, validators=[phone_validator],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01XXXXXXXXX'}),
    )
    district = forms.ChoiceField(
        choices=[('', 'Select district')] + DISTRICT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_district'}),
    )
    area = forms.CharField(
        max_length=100, label='Thana / Area', widget=forms.TextInput(attrs={'class': 'form-control'}),
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
    payment_method = forms.ChoiceField(
        choices=Order.PaymentMethod.choices, initial=Order.PaymentMethod.COD, widget=forms.RadioSelect,
    )
    save_address = forms.BooleanField(required=False, initial=True, label='Save this address to my account')

    SHIPPING_FIELDS = ['full_name', 'email', 'phone', 'district', 'area', 'address_line', 'note']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not (user and user.is_authenticated):
            del self.fields['save_address']
        if not payments.is_configured():
            self.fields['payment_method'].choices = [
                c for c in Order.PaymentMethod.choices if c[0] != Order.PaymentMethod.SSLCOMMERZ
            ]

    def shipping_data(self):
        return {name: self.cleaned_data[name] for name in self.SHIPPING_FIELDS}
