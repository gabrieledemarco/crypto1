# Create your models here.
from django.db import models
from django.contrib.auth.models import AbstractUser
from cryptography.fernet import Fernet
from django.db import models
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from django.core.exceptions import ValidationError

# Chiave segreta per Fernet (deve essere gestita in modo sicuro, non mettere la chiave nel codice)
# Genera una chiave segreta
KEY = Fernet.generate_key()  # Cambia questa con una chiave sicura
fernet = Fernet(KEY)


# portfolio_custmer
class CustomUser(AbstractUser):
    api_key = models.CharField(max_length=100)
    secret_key = models.CharField(max_length=100)


# crypto tables
class Crypto(models.Model):
    coin = models.CharField(max_length=10, null=False)
    name = models.CharField(max_length=50, null=False)
    binance_withdraw_enable = models.BooleanField(default=False)
    trading = models.BooleanField(default=False)
    withdraw_enable = models.BooleanField(default=False)
    x_effective_from = models.CharField(max_length=50, null=False)
    x_effective_to = models.CharField(max_length=50, null=False)

    class Meta:
        db_table = 'crypto'
        constraints = [
            models.UniqueConstraint(fields=['id'], name='crypto_pk')
        ]

    def __str__(self):
        return f"{self.name} ({self.coin})"


class Symbol(models.Model):
    symbol = models.CharField(max_length=20, null=False)
    base_asset = models.CharField(max_length=20, null=False)
    quote_asset = models.CharField(max_length=20, null=False)
    x_effective_from = models.CharField(max_length=50, null=False)
    x_effective_to = models.CharField(max_length=50, null=False)

    class Meta:
        db_table = 'symbols'  # Nome esatto della tabella nel database
        constraints = [
            models.UniqueConstraint(fields=['id'], name='symbols_pk')
        ]

    def __str__(self):
        return f"{self.symbol} ({self.base_asset}/{self.quote_asset})"
