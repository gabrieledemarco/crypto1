import psycopg2 as db

from . import config_postgres_alchemy as cfa


class Database:

    def __init__(self):
        self.__open_conn()

    def __open_conn(self):
        self._conn = db.connect(host=cfa.postgres_sql['host'], database=cfa.postgres_sql['db'],
                                user=cfa.postgres_sql['user'], password=cfa.postgres_sql['password'])
        self._curs = self._conn.cursor()

    def __is_connection_valid(self):
        try:
            return self._curs.closed == 0 and self._conn.closed == 0
        except:
            return False

    def execute(self, sql, list_value=None):
        if self.__is_connection_valid():
            self.close_conn()

        self.__open_conn()

        self._curs.execute(sql, list_value)

    def execute_and_commit(self, sql, list_value=None):
        self.execute(sql, list_value)
        self.commit()

    def fetchOne(self):
        return self._curs.fetchone()

    def fetchMany(self, fetch_size=cfa.postgres_sql['default_fetc_size']):
        return self._curs.fetchmany(fetch_size)

    def fetchAll(self):
        return self._curs.fetchall()

    def commit(self):
        if self.__is_connection_valid():
            self._conn.commit()

    def rollback(self):
        if self.__is_connection_valid():
            self._conn.rollback()

    def name_columns(self):
        return [desc[0] for desc in self._curs.description]

    def close_conn(self):
        try:
            self._curs.close()
            self._conn.close()
        except:
            pass
