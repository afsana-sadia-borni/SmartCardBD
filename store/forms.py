from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory

from orders.models import Coupon, ReturnRequest
from products.models import Banner, FlashSale, Product, ProductImage, ProductVariant

from .roles import ROLES


class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'

    def __init__(self, **kwargs):
        super().__init__(format='%Y-%m-%dT%H:%M', **kwargs)


class StyledFormMixin:
    """Bootstrap classes on every widget, so templates can render fields in a loop."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                css = 'form-check-input' if isinstance(widget, forms.CheckboxInput) else ''
            elif isinstance(widget, forms.Select):
                css = 'form-select'
            else:
                css = 'form-control'
            if css:
                widget.attrs['class'] = (widget.attrs.get('class', '') + ' ' + css).strip()


class ProductForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ['title', 'category', 'brand', 'description', 'price', 'discount_price', 'stock', 'image',
                  'is_active', 'is_featured']
        widgets = {'description': forms.Textarea(attrs={'rows': 5}), 'image': forms.FileInput}
        labels = {'price': 'Regular price (৳)', 'discount_price': 'Sale price (৳)', 'is_active': 'Visible in the shop',
                  'is_featured': 'Show on the home page', 'image': 'Main photo'}
        help_texts = {'stock': 'Ignored when the product has options below: their stock is added up.'}

    def clean(self):
        data = super().clean()
        price, sale = data.get('price'), data.get('discount_price')
        if price is not None and sale is not None and sale >= price:
            self.add_error('discount_price', 'The sale price must be lower than the regular price.')
        return data


class VariantForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ['color', 'size', 'storage', 'sku', 'price', 'discount_price', 'stock', 'is_active']
        widgets = {'color': forms.TextInput(attrs={'placeholder': 'e.g. Black'}),
                   'size': forms.TextInput(attrs={'placeholder': 'e.g. XL'}),
                   'storage': forms.TextInput(attrs={'placeholder': 'e.g. 128GB'}),
                   'price': forms.NumberInput(attrs={'placeholder': 'Same'}),
                   'discount_price': forms.NumberInput(attrs={'placeholder': '-'})}


class GalleryImageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'color', 'alt', 'sort_order']
        widgets = {'image': forms.FileInput}
        labels = {'alt': 'Description', 'sort_order': 'Order'}


VariantFormSet = inlineformset_factory(Product, ProductVariant, form=VariantForm, extra=1, can_delete=True)
GalleryFormSet = inlineformset_factory(Product, ProductImage, form=GalleryImageForm, extra=2, can_delete=True)


class CouponForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ['code', 'discount_type', 'value', 'max_discount', 'min_order_amount', 'valid_from', 'valid_to',
                  'usage_limit', 'is_active']
        widgets = {'valid_from': DateTimeInput(), 'valid_to': DateTimeInput()}
        labels = {'value': 'Discount (% or ৳)', 'max_discount': 'Maximum discount (৳)',
                  'min_order_amount': 'Minimum order (৳)', 'valid_to': 'Valid until'}

    def clean(self):
        data = super().clean()
        if data.get('valid_from') and data.get('valid_to') and data['valid_to'] <= data['valid_from']:
            self.add_error('valid_to', 'Must be after the start.')
        if data.get('discount_type') == Coupon.PERCENT and data.get('value') and data['value'] > 90:
            self.add_error('value', 'A percentage discount can be at most 90%.')
        return data


class FlashSaleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FlashSale
        fields = ['title', 'discount_percent', 'starts_at', 'ends_at', 'products', 'is_active']
        widgets = {'starts_at': DateTimeInput(), 'ends_at': DateTimeInput(),
                   'products': forms.CheckboxSelectMultiple}
        labels = {'discount_percent': 'Discount (%)', 'is_active': 'Active'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['products'].queryset = Product.objects.active().order_by('title')

    def clean(self):
        data = super().clean()
        if data.get('starts_at') and data.get('ends_at') and data['ends_at'] <= data['starts_at']:
            self.add_error('ends_at', 'Must be after the start.')
        return data


class BannerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Banner
        fields = ['title', 'subtitle', 'image', 'link_url', 'button_text', 'sort_order', 'starts_at', 'ends_at',
                  'is_active']
        widgets = {'starts_at': DateTimeInput(), 'ends_at': DateTimeInput(), 'image': forms.FileInput}
        labels = {'link_url': 'Button link', 'sort_order': 'Position', 'starts_at': 'Show from (optional)',
                  'ends_at': 'Show until (optional)'}
        help_texts = {'image': 'Wide photo, about 1600 × 640 pixels.'}


class ReturnDecisionForm(StyledFormMixin, forms.Form):
    status = forms.ChoiceField(choices=[c for c in ReturnRequest.Status.choices if c[0] != 'pending'])
    admin_note = forms.CharField(required=False, label='Message to the customer',
                                 widget=forms.Textarea(attrs={'rows': 2}))


class AnswerForm(StyledFormMixin, forms.Form):
    answer = forms.CharField(widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Write your answer...'}))


class TeamMemberForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(help_text='They must sign up on the shop first.')
    role = forms.ChoiceField(choices=[(name, name) for name in ROLES])

    def clean_email(self):
        user = get_user_model().objects.filter(email__iexact=self.cleaned_data['email']).first()
        if user is None:
            raise forms.ValidationError('No account with this email. Ask them to sign up first.')
        if user.is_superuser:
            raise forms.ValidationError('This is an owner account.')
        self.user = user
        return user.email
