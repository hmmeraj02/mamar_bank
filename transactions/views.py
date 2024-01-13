from typing import Any
from django.shortcuts import redirect, get_object_or_404, render
from django.views.generic import ListView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Transaction, Bankrupt
from .forms import DepositForm, WithdrawForm, LoanRequestForm, TransferForm
from .constants import DEPOSIT, WITHDRAWAL, LOAN, LOAN_PAID, TRANSFER
from django.contrib import messages
from django.http import HttpResponse
from datetime import datetime
from django.db.models import Sum
from django.views import View
from django.urls import reverse_lazy
from .models import Transaction
from django.contrib.auth.models import User
from accounts.models import UserBankAccount
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
# Create your views here.

def send_transaction_email(user, amount, subject, template):
    # Gather users to notify about the transaction
    message = render_to_string(template, {
            'user': user,
            'amount': amount,
        })
    send_email = EmailMultiAlternatives(subject, '', to=[user.email])
    send_email.attach_alternative(message, "text/html")
    send_email.send()

class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    title = ''
    success_url = reverse_lazy('transaction_report')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'account': self.request.user.account,
        })
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title,
        })
        return context
    
class DepositMoneyView(TransactionCreateMixin):
    form_class = DepositForm
    title = 'Deposit'

    def get_initial(self):
        initial = {'transaction_type' : DEPOSIT}
        return initial
    
    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = self.request.user.account
        account.balance += amount
        account.save(
            update_fields = ['balance']
        )
        messages.success(
            self.request,
            f'{"{:,.2f}".format(float(amount))}$ was deposited to your account successfully',
        )

        send_transaction_email(self.request.user, amount, "Deposit Message", "transactions/deposit_email.html")
        return super().form_valid(form)
    
class WithdrawMoneyView(TransactionCreateMixin):
    form_class = WithdrawForm
    title = 'Withdraw Money'

    def get_initial(self):
        initial = {'transaction_type' : WITHDRAWAL}
        return initial
    
    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        if Bankrupt.objects.filter(is_bankrupt=True).exists():
            messages.error(self.request, f"Bank is currently closed due to bankruptcy")
            return redirect('transaction_report')
        account = self.request.user.account
        account.balance -= amount
        account.save(
            update_fields = ['balance']
        )
        messages.success(self.request, f'${amount} was withdrawn from your account successfully')

        send_transaction_email(self.request.user, amount, "Withdrawal Message", "transactions/withdraw_email.html")
        return super().form_valid(form)

class LoanRequestView(TransactionCreateMixin):
    form_class = LoanRequestForm
    title = 'Request For Loan'
    success_url = reverse_lazy('loan_list')

    def get_initial(self):
        initial = {'transaction_type' : LOAN}
        return initial
    
    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        current_loan_count = Transaction.objects.filter(account=self.request.user.account, transaction_type=3, loan_approve = True).count()
        if current_loan_count >= 3:
            return HttpResponse('Loan limit exceeded')
        messages.success(self.request, f'${amount} will be deposited to your account as LOAN after accepting it from Bank Manager')

        send_transaction_email(self.request.user, amount, "Loan Request Message", "transactions/loan_email.html")
        return super().form_valid(form)

class TransactionReportView(LoginRequiredMixin, ListView):
    template_name = 'transactions/transaction_report.html'
    model = Transaction
    balance = 0
    context_object_name = 'report_list'

    def get_queryset(self):
        queryset = super().get_queryset().filter(
            account = self.request.user.account
        )
        
        start_date_str = self.request.GET.get('start_date')
        end_date_str = self.request.GET.get('end_date')

        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            queryset = queryset.filter(timestamp__date__gte = start_date, timestamp__date__lte = end_date)
            self.balance = Transaction.objects.filter(timestamp__date__gte = start_date, timestamp__date__lte = end_date).aggregate(Sum('amount'))['amount__sum']
        else:
            self.balance = self.request.user.account.balance
        return queryset.distinct()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'account': self.request.user.account,
        })
        return context
    
class PayLoanView(LoginRequiredMixin, View):
    def get(self, request, loan_id):
        loan = get_object_or_404(Transaction, id=loan_id)

        if loan.loan_approve:
            user_account = loan.account
            if loan.loan_approve:
                user_account = loan.account
                if loan.amount < user_account.balance:
                    user_account.balance -= loan.amount
                    loan.balance_after_transaction = user_account.balance
                    user_account.save()
                    loan.transaction_type = LOAN_PAID
                    loan.save()
                    return redirect('loan_list')
                else:
                    messages.success(request,'You do not have enough money in your account to pay this loan!')
                    return redirect('loan_list')
                
class LoanListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = "transactions/loan_request.html"
    context_object_name = 'loans'

    def get_queryset(self):
        user_account = self.request.user.account
        queryset = Transaction.objects.filter(account=user_account, transaction_type = LOAN)
        return queryset
    
class TransferMoneyView(TransactionCreateMixin):
    form_class = TransferForm
    title = "Transfer Money"

    def get_initial(self):
        initial = {"transaction_type": TRANSFER}
        return initial
    
    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        receiver = form.cleaned_data.get('receiver')

        try:
            receiver_account = UserBankAccount.objects.get(account_no = receiver)
        except UserBankAccount.DoesNotExist:
            messages.success(self.request, f"User with account number {receiver} not found.")
            return redirect('transfer')

        account = self.request.user.account
        account.balance -= amount
        account.save(
            update_fields = ['balance']
        )
        receiver_account.balance += amount
        receiver_account.save(
            update_fields = ['balance']
        )
        messages.success(self.request, f'${amount} is transferred from your account successfully')
        return super().form_valid(form)