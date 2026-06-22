from django.urls import path

from .views import (
    AuditExportView,
    BalanceSheetView,
    IncomeStatementView,
    StatementOfAccountView,
    TrialBalanceView,
)

urlpatterns = [
    path('reports/trial-balance/',    TrialBalanceView.as_view()),
    path('reports/balance-sheet/',    BalanceSheetView.as_view()),
    path('reports/income-statement/', IncomeStatementView.as_view()),
    path('reports/statement/',        StatementOfAccountView.as_view()),
    path('reports/export/',           AuditExportView.as_view()),
]
