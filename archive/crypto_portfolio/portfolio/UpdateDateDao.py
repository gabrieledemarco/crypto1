from .Database import Database
from psycopg2.extras import execute_values

import sys


class UpdateTableDAO:
    def __init__(self):
        """Inizializza il DAO utilizzando la classe Database."""
        self.db = Database()

    def insert_row(self, id_user, name_table, start_update_time, end_update_time):
        """Inserisce una nuova riga nella tabella update_table."""
        query = """
        INSERT INTO update_table (id_user, name_table, start_update_time, end_update_time)
        VALUES (%s, %s, %s, %s)
        """
        self.db.execute_and_commit(query, [id_user, name_table, start_update_time, end_update_time])

    def count_rows_by_user(self, id_user):
        """Conta il numero di righe per un dato utente."""
        query = "SELECT COUNT(*) FROM update_table WHERE id_user = %s"
        self.db.execute(query, [id_user])
        return self.db.fetchOne()[0]

    def count_rows_by_user_and_table(self, id_user, name_table):
        """Conta il numero di righe per utente e tabella."""
        query = "SELECT COUNT(*) FROM update_table WHERE id_user = %s AND name_table = %s"
        self.db.execute(query, [id_user, name_table])
        return self.db.fetchOne()[0]

    def select_all(self):
        """Restituisce tutte le righe dalla tabella update_table."""
        query = "SELECT * FROM update_table"
        self.db.execute(query)
        return self.db.fetchAll()

    def select_by_user(self, id_user):
        """Restituisce tutte le righe per un determinato utente."""
        query = "SELECT * FROM update_table WHERE id_user = %s"
        self.db.execute(query, [id_user])
        return self.db.fetchAll()

    def delete_by_id(self, id_update):
        """Elimina una riga dalla tabella per id_update."""
        query = "DELETE FROM update_table WHERE id_update = %s"
        self.db.execute_and_commit(query, [id_update])

    def update_end_time(self, id_update, new_end_time):
        """Aggiorna l'end_update_time per una determinata riga."""
        query = "UPDATE update_table SET end_update_time = %s WHERE id_update = %s"
        self.db.execute_and_commit(query, [new_end_time, id_update])

    def close(self):
        """Chiude esplicitamente la connessione al database."""
        self.db.close_conn()

    def get_max_end_time(self, id_user, name_table):
        """Recupera il massimo valore di end_update_time per id_user e name_table."""
        query = """
            SELECT MAX(end_update_time) 
            FROM update_table 
            WHERE id_user = %s AND name_table = %s
        """
        self.db.execute(query, [id_user, name_table])
        result = self.db.fetchOne()
        return result[0] if result else None