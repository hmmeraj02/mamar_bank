from typing import Any
from django import forms
from .models import Transaction

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['amount', 'transaction_type']

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account')
        super().__init__(*args, **kwargs)
        self.fields['transaction_type'].disabled = True
        self.fields['transaction_type'].widget = forms.HiddenInput()

    def save(self, commit = True):
        self.instance.account = self.account
        self.instance.balance_after_transaction = self.account.balance
        return super().save()
    
class DepositForm(TransactionForm):
    def clean_amount(self):
        min_deposit_amount = 100
        amount = self.cleaned_data.get('amount')
        if amount < min_deposit_amount:
            raise forms.ValidationError(f"Deposits must be at least ${min_deposit_amount}")
        return amount
    
class WithdrawForm(TransactionForm):
    def clean_amount(self):
        account = self.account
        min_withdraw_amount = 500
        max_withdraw_amount = 20000
        balance = account.balance
        amount = self.cleaned_data.get('amount')
        if amount < min_withdraw_amount:
            raise forms.ValidationError(f"Withdrawal amounts must be greater than ${min_withdraw_amount}")
        
        if amount > max_withdraw_amount:
            raise forms.ValidationError(f"You can only withdraw up to ${max_withdraw_amount}")
        
        if amount > balance:
            raise forms.ValidationError(
                f'You have ${balance} in your account.'
                'You can not withdraw more than your account balance'
            )
        return amount
    
class LoanRequestForm(TransactionForm):
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        return amount
    
class TransferForm(TransactionForm):
    class Meta:
        model = Transaction
        fields = ['receiver', 'amount', 'transaction_type']
    
    def clean_amount(self):
        account = self.account
        balance = account.balance

        min_transfer_amount = 100
        max_transfer_amount = 10000
        amount = self.cleaned_data.get('amount')

        if amount < min_transfer_amount:
            raise forms.ValidationError(f"Transfer amounts must be at least ${min_transfer_amount}")
        
        if amount > max_transfer_amount:
            raise forms.ValidationError(f"Transfer amounts must be at most ${max_transfer_amount}")

        if amount > balance:
            raise forms.ValidationError(
                f'You have ${balance} in your account.'
                'You can not transfer more than your account balance'
            )
        return amount
    