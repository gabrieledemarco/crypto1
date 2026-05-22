# services.py
from .models import CustomUser
from django.utils.timezone import now
from django.db import IntegrityError


class PortfolioCustomUserService:

    @staticmethod
    def create_user(username, password, email=None, api_key=None, secret_key=None):
        """Crea un nuovo utente con controllo degli errori."""
        try:
            user = CustomUser.objects.create_user(
                username=username,
                password=password,
                email=email,
                api_key=api_key,
                secret_key=secret_key
            )
            return user
        except IntegrityError as e:
            print(f"Errore di integrità: {e}")
            return None

    @staticmethod
    def get_user_by_username(username):
        """Recupera un utente dato lo username."""
        try:
            return CustomUser.objects.get(username=username)
        except PortfolioCustomUserService.DoesNotExist:
            return None

    @staticmethod
    def update_user_api_keys(username, new_api_key, new_secret_key):
        """Aggiorna le chiavi API di un utente."""
        user = PortfolioCustomUserService.get_user_by_username(username)
        if user:
            user.api_key = new_api_key
            user.secret_key = new_secret_key
            user.save()
            return user
        return None

    @staticmethod
    def delete_user(username):
        """Elimina un utente dal database."""
        user = PortfolioCustomUserService.get_user_by_username(username)
        if user:
            user.delete()
            return True
        return False

    @staticmethod
    def count_users():
        """Conta il numero totale di utenti."""
        return PortfolioCustomUserService.objects.count()

    @staticmethod
    def list_all_users():
        """Restituisce tutti gli utenti nel database."""
        return PortfolioCustomUserService.objects.all()
