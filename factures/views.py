from datetime import datetime, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.http import HttpResponse, JsonResponse
from django.views import View
from .models import LineItem, Invoice
from .forms import LineItemFormset, InvoiceForm, PaymentForm
import pdfkit
from pulls.utils import login_required_connect, CustomLoginRequiredMixin
from tests.views import recup_infos_users
from django.db.models import Q
from django.core.paginator import Paginator

class InvoiceListView(CustomLoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "")
        status_filter = request.GET.get("status", "")
        date_filter = request.GET.get("date", "")
        completion_filter = request.GET.get("completion", "")
        page = request.GET.get("page", 1)

        invoices = Invoice.objects.all()

        if query:
            invoices = invoices.filter(
                Q(customer__icontains=query) | Q(invoice_number__icontains=query)
            )

        if status_filter:
            invoices = invoices.filter(status=(status_filter == "1"))

        if date_filter:
            today = datetime.now().date()
            if date_filter == "past":
                invoices = invoices.filter(due_date__lt(today))
            elif date_filter == "future":
                invoices = invoices.filter(due_date__gt(today))

        if completion_filter:
            if completion_filter == "completed":
                invoices = invoices.filter(draft=False)
            elif completion_filter == "draft":
                invoices = invoices.filter(draft=True)

        today = datetime.now().date()
        for invoice in invoices:
            if invoice.due_date:
                invoice.days_remaining = (invoice.due_date - today).days

            if invoice.total_amount:
                tax_rate = invoice.tax_percentage / 100
                invoice.subtotal = invoice.total_amount / (1 + tax_rate)
                invoice.tax = invoice.total_amount - invoice.subtotal
            else:
                invoice.subtotal = Decimal("0.00")
                invoice.tax = Decimal("0.00")

            # Calculate the payment status
            if invoice.remaining_amount == 0:
                invoice.payment_status = "Payé"
            elif invoice.remaining_amount < invoice.total_amount:
                invoice.payment_status = "Partiellement payé"
            else:
                invoice.payment_status = "Non payé"

        # Pagination
        paginator = Paginator(invoices, 10)  # Show 10 invoices per page
        paginated_invoices = paginator.get_page(page)

        context = {
            "invoices": paginated_invoices,
            "query": query,
            "status_filter": status_filter,
            "date_filter": date_filter,
            "completion_filter": completion_filter,
        }
        return render(request, "factures/invoice_list.html", context)

@login_required_connect
def create_or_edit_invoice(request, id=None):
    if id:
        invoice = get_object_or_404(Invoice, id=id)
        heading_message = "Edit Invoice"
    else:
        invoice = Invoice(
            date=datetime.now().date(),
            due_date=datetime.now().date() + timedelta(days=30),
            draft=True,
        )
        heading_message = "Create Invoice"

    if request.method == "POST":
        form = InvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            invoice = form.save(commit=False)
            if not invoice.pk:
                invoice.save()  # Save the invoice to generate the primary key if not already saved

            formset = LineItemFormset(request.POST, queryset=LineItem.objects.filter(invoice=invoice))
            if formset.is_valid():
                if "create" in request.POST:
                    invoice.draft = False  # Mark as finalized

                total = Decimal("0.00")
                invoice.lineitem_set.all().delete()  # Delete existing line items
                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                        service = form.cleaned_data.get("service")
                        description = form.cleaned_data.get("description")
                        quantity = form.cleaned_data.get("quantity")
                        rate = form.cleaned_data.get("rate")
                        if service and description and quantity and rate:
                            amount = Decimal(rate) * Decimal(quantity)
                            total += amount
                            line_item = LineItem(
                                invoice=invoice,
                                service=service,
                                description=description,
                                quantity=quantity,
                                rate=rate,
                                amount=amount,
                            )
                            line_item.save()

                tax = total * (invoice.tax_percentage / 100)
                total_with_tax = total + tax
                original_total = invoice.total_amount
                invoice.total_amount = total_with_tax

                # Set remaining amount for new invoices or reset to total_amount if not partially paid
                if invoice.draft:
                    invoice.remaining_amount = total_with_tax

                # Add log entry for total amount change
                if original_total != invoice.total_amount:
                    invoice.add_log_entry(
                        request.user,
                        f"Total changed from {original_total or '0'} to {invoice.total_amount}",
                    )

                # Add log entry for draft status change
                if not invoice.draft:
                    invoice.add_log_entry(request.user, "Status changed to Terminé")
                else:
                    invoice.add_log_entry(request.user, "Invoice created")

                # Save the invoice with logs
                invoice.save()

                # Debugging info
                print(f"Invoice {invoice.pk} saved successfully.")
                return redirect(reverse("factures:invoice-list"))
            else:
                print("Formset is invalid")
                for i, form in enumerate(formset):
                    print(f"Formset form {i} errors: {form.errors}")
        else:
            print("Form is invalid")
            print(f"Form errors: {form.errors}")

    else:
        form = InvoiceForm(instance=invoice)
        if invoice.pk:
            formset = LineItemFormset(queryset=LineItem.objects.filter(invoice=invoice))
        else:
            formset = LineItemFormset(queryset=LineItem.objects.none())

    payment_form = PaymentForm()  # Initialize the payment form

    context = {
        "title": heading_message,
        "form": form,
        "formset": formset,
        "payment_form": payment_form,  # Add the payment form to the context
        "invoice_id": invoice.invoice_number if invoice else None,
        "invoice": invoice,
    }
    return render(
        request,
        "factures/invoice_edit.html" if id else "factures/invoice_create.html",
        context,
    )
@login_required_connect
def register_payment(request, id):
    invoice = get_object_or_404(Invoice, id=id)

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            # Process the form data
            journal = form.cleaned_data['journal']
            payment_mode = form.cleaned_data['payment_mode']
            bank_account = form.cleaned_data['bank_account']
            amount_paid = form.cleaned_data['amount_paid']
            payment_date = form.cleaned_data['payment_date']
            memo = form.cleaned_data['memo']

            invoice.remaining_amount -= amount_paid
            if invoice.remaining_amount <= 0:
                invoice.remaining_amount = 0
                invoice.status = 'payé'
            elif invoice.remaining_amount < invoice.total_amount:
                invoice.status = 'partiellement payé'
            invoice.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'errors': form.errors})
    else:
        form = PaymentForm()

    context = {
        "invoice": invoice,
        "form": form
    }
    return render(request, "factures/register_payment.html", context)
@login_required_connect
def view_PDF(request, id=None):
    invoice = get_object_or_404(Invoice, id=id)
    lineitem = invoice.lineitem_set.all()

    tax_rate = (
        invoice.tax_percentage / 100 if invoice.tax_percentage else Decimal("0.00")
    )

    if invoice.total_amount is None:
        subtotal = Decimal("0.00")
        tax = Decimal("0.00")
    else:
        subtotal = invoice.total_amount / (1 + tax_rate)
        tax = invoice.total_amount - subtotal

    context = {
        "company": {
            "name": "R & S TELECOM ",
            "address": "8 rue des frères caudron 78140 vélizy-villacoublay",
            "phone": "(818) XXX XXXX",
            "email": "contact@rs-telecom.fr",
        },
        "invoice_id": invoice.invoice_number,
        "invoice_total": invoice.total_amount,
        "customer": invoice.customer,
        "customer_email": invoice.customer_email,
        "date": invoice.date,
        "due_date": invoice.due_date,
        "billing_address": invoice.billing_address,
        "message": invoice.message,
        "lineitem": lineitem,
        "tax": tax,
        "subtotal": subtotal,
    }
    return render(request, "factures/pdf_template.html", context)


@login_required_connect
def generate_PDF(request, id):
    invoice = get_object_or_404(Invoice, id=id)
    pdf = pdfkit.from_url(
        request.build_absolute_uri(reverse("factures:view-pdf", args=[id])), False
    )
    filename = f"{invoice.invoice_number}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
