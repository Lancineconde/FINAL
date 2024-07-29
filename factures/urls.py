from django.urls import path
from .views import InvoiceListView, create_or_edit_invoice, view_PDF, generate_PDF

app_name = 'factures'  # Ensure the app name is specified for namespacing

urlpatterns = [
    path('', InvoiceListView.as_view(), name='invoice-list'),
    path('create/', create_or_edit_invoice, name='invoice-create'),
    path('edit/<int:id>/', create_or_edit_invoice, name='invoice-edit'),
    path('pdf/<int:id>/', view_PDF, name='view-pdf'),
    path('generate-pdf/<int:id>/', generate_PDF, name='generate-pdf'),
]
