from django.db import models
import datetime
from decimal import Decimal
import jsonfield


class Invoice(models.Model):
    customer = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(null=True, blank=True)
    billing_address = models.TextField(null=True, blank=True)
    date = models.DateField(blank=True, null=True)
    due_date = models.DateField(null=True, blank=True)
    message = models.TextField(default="This is a default message.", blank=True)
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    status = models.CharField(max_length=20, default="Non payé")
    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    draft = models.BooleanField(default=True)
    tax_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=20.00, blank=True
    )
    unique_id = models.PositiveIntegerField(editable=False, null=True, blank=True)
    log = jsonfield.JSONField(default=list)
    remaining_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    def __str__(self):
        return str(self.customer)

    def get_status(self):
        return self.status

    def can_edit(self):
        return self.draft

    def save(self, *args, **kwargs):
        if not self.invoice_number or self._state.adding:
            self.generate_invoice_number()
        else:
            if self.pk is not None:
                orig = Invoice.objects.get(pk=self.pk)
                if orig.date != self.date:
                    self.generate_invoice_number(update_unique_id=False)

        # Ensure total_amount and remaining_amount are not None
        if self.total_amount is None:
            self.total_amount = Decimal("0.00")
        if self.remaining_amount is None:
            self.remaining_amount = self.total_amount

        # Update payment status
        if self.remaining_amount < self.total_amount and self.remaining_amount > 0:
            self.status = "Partiellement payé"
        elif self.remaining_amount == 0:
            self.status = "Payé"
        else:
            self.status = "Non payé"

        super().save(*args, **kwargs)

    def generate_invoice_number(self, update_unique_id=True):
        if self.date:
            invoice_year = self.date.year
            invoice_month = self.date.month
        else:
            current_date = datetime.datetime.now()
            invoice_year = current_date.year
            invoice_month = current_date.month

        if update_unique_id or not self.unique_id:
            last_invoice = (
                Invoice.objects.filter(date__year=invoice_year)
                .order_by("-unique_id")
                .first()
            )
            self.unique_id = (last_invoice.unique_id if last_invoice else 0) + 1

        self.invoice_number = (
            f"FAC/{invoice_year}/{invoice_month:02d}/{self.unique_id:04d}"
        )

    def add_log_entry(self, user, message):
        username = getattr(
            user, "username", getattr(user, "users_name", "Unknown User")
        )
        log_entry = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": username,
            "message": message,
        }
        self.log.append(log_entry)
        self.save()


class LineItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    service = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(blank=True, null=True)
    rate = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.service} for {self.invoice}"

    def save(self, *args, **kwargs):
        self.amount = (
            Decimal(self.quantity) * Decimal(self.rate)
            if self.quantity and self.rate
            else Decimal("0.00")
        )
        super().save(*args, **kwargs)
