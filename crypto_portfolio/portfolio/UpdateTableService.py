from .UpdateDateDao import UpdateTableDAO
from datetime import datetime


class UpdateTableService:
    def __init__(self):
        """Inizializza il service con un'istanza del DAO."""
        self.dao = UpdateTableDAO()

    def insert_with_current_time(self, id_user, name_table):
        """Inserisce una nuova riga usando il timestamp corrente per entrambi gli orari."""
        current_time = datetime.now()
        self.dao.insert_row(id_user, name_table, current_time, current_time)

    def insert_with_current_start_time(self, id_user, name_table):
        """Inserisce una nuova riga con start_update_time al tempo corrente e end_update_time come NULL."""
        current_time = datetime.now()
        self.dao.insert_row(id_user, name_table, current_time, current_time)

    def update_end_time(self, id_update):
        """Aggiorna solo l'end_update_time al tempo corrente."""
        current_time = datetime.now()
        self.dao.update_end_time(id_update, current_time)

    def update_start_time(self, id_update):
        """Aggiorna solo lo start_update_time al tempo corrente."""
        current_time = datetime.now()
        query = "UPDATE update_table SET start_update_time = %s WHERE id_update = %s"
        self.dao.db.execute_and_commit(query, [current_time, id_update])

    def count_rows_by_user(self, id_user):
        """Conta le righe per un determinato utente."""
        return self.dao.count_rows_by_user(id_user)

    def count_rows_by_user_and_table(self, id_user, name_table):
        """Conta le righe per un utente specifico e una tabella."""
        return self.dao.count_rows_by_user_and_table(id_user, name_table)

    def get_all_records(self):
        """Restituisce tutte le righe dalla tabella."""
        return self.dao.select_all()

    def get_records_by_user(self, id_user):
        """Restituisce tutte le righe di un determinato utente."""
        return self.dao.select_by_user(id_user)

    def delete_record_by_id(self, id_update):
        """Elimina un record dalla tabella usando l'id."""
        self.dao.delete_by_id(id_update)

    def close_service(self):
        """Chiude la connessione al database."""
        self.dao.close()

    def get_max_end_time_dividends(self, id_user):
        """Recupera il massimo end_update_time dalla tabella 'dividends' per un determinato id_user."""
        return self.dao.get_max_end_time(id_user, 'dividends')

    def get_max_end_time_orders(self, id_user):
        """Recupera il massimo end_update_time dalla tabella 'orders' per un determinato id_user."""
        return self.dao.get_max_end_time(id_user, 'orders')

    def get_max_end_time_trades(self, id_user):
        """Recupera il massimo end_update_time dalla tabella 'trades' per un determinato id_user."""
        return self.dao.get_max_end_time(id_user, 'trades')

    def get_max_end_time_deposit_withdraw_fiat(self, id_user):
        """Recupera il massimo end_update_time dalla tabella 'deposit_withdraw_fiat' per un determinato id_user."""
        return self.dao.get_max_end_time(id_user, 'deposit_withdraw_fiat')

    def get_max_end_time_deposits_crypto(self, id_user):
        """Recupera il massimo end_update_time dalla tabella 'deposits_crypto' per un determinato id_user."""
        return self.dao.get_max_end_time(id_user, 'deposits_crypto')

    def get_max_end_time_withdraw_crypto(self, id_user):
        """Recupera il massimo end_update_time dalla tabella 'withdraw_crypto' per un determinato id_user."""
        return self.dao.get_max_end_time(id_user, 'withdraw_crypto')


# Esempio di utilizzo
if __name__ == "__main__":
    service = UpdateTableService()

    # Inserimento con orario corrente
    service.insert_with_current_time(1, 'crypto_portfolio')
    service.insert_with_current_start_time(2, 'crypto_portfolio')

    # Aggiorna end time
    service.update_end_time(1)

    # Conta righe per utente
    print("Righe per utente 1:", service.count_rows_by_user(1))

    # Chiudi connessione
    service.close_service()
