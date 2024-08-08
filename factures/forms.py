from django import forms
from django.forms import modelformset_factory
from .models import LineItem, Invoice


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "customer",
            "customer_email",
            "billing_address",
            "date",
            "due_date",
            "message",
            "draft",
            "tax_percentage",
        ]
        widgets = {
            "customer": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Customer/Company Name"}
            ),
            "customer_email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "customer@company.com"}
            ),
            "billing_address": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Billing Address"}
            ),
            "date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "dd-MM-yyyy",
                    "type": "date",
                }
            ),
            "due_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "dd-MM-yyyy",
                    "type": "date",
                }
            ),
            "message": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Message"}
            ),
            "draft": forms.HiddenInput(),
            "tax_percentage": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Tax Percentage"}
            ),
        }

    def clean_tax_percentage(self):
        tax_percentage = self.cleaned_data.get("tax_percentage") or 0
        if tax_percentage < 0 or tax_percentage > 100:
            raise forms.ValidationError("Tax percentage must be between 0 and 100")
        return tax_percentage


class LineItemForm(forms.ModelForm):
    class Meta:
        model = LineItem
        fields = ["service", "description", "quantity", "rate", "amount"]
        widgets = {
            "service": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Service Name"}
            ),
            "description": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Description"}
            ),
            "quantity": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Quantity"}
            ),
            "rate": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Rate"}
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control amount",
                    "placeholder": "Amount",
                    "readonly": "readonly",
                }
            ),
        }


LineItemFormset = modelformset_factory(
    LineItem, form=LineItemForm, extra=1, can_delete=True
)


class PaymentForm(forms.Form):
    journal = forms.CharField(label="Journal", initial="Banque", required=False)
    payment_mode = forms.CharField(
        label="Mode de paiement", initial="Manual", required=False
    )
    bank_account = forms.CharField(
        label="Compte bancaire du bénéficiaire", required=False
    )
    amount_paid = forms.DecimalField(
        max_digits=10, decimal_places=2, label="Montant", required=True
    )
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date de règlement",
        required=True,
    )
    memo = forms.CharField(label="Mémo", initial="FAC/YYYY/MM/XXXX", required=False)
