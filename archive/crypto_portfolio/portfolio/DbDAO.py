from .Database import Database
from psycopg2.extras import execute_values

import sys


class DbDao:
    def __init__(self):
        self.__db = Database()

    def name_columns(self, name_table: str):
        sel = f"select * from public.{name_table} limit 0"
        self.__db.execute(sel)
        name = self.__db.name_columns()
        return name

    def insert(self, name_table: str, name_columns: list, list_record: list):
        # print(name_columns)
        records_list_template = ",".join(["%s"] * len(list_record))
        # print(records_list_template)
        n_col = ','.join(name_columns[1:])
        ins = f"insert into public.{name_table} ({n_col}) values ({records_list_template})"
        print(ins)
        self.__db.execute_and_commit(ins, list_record)

    def insert_bulk(self, name_table: str, name_columns: list, list_record: list):
        """Inserimento massivo di record in una tabella PostgreSQL."""
        # Costruzione della query SQL sicura
        n_col = ','.join(name_columns[1:])

        with open('output.txt', 'w') as f:
            sys.stdout = f
            # Creazione di un template di valori per l'inserimento
            records_list_template = "(" + ",".join(["%s"] * len(name_columns[1:])) + ")"

            # Query di inserimento
            ins = f"INSERT INTO public.{name_table} ({n_col}) VALUES {','.join([records_list_template] * len(list_record))}"
            print(ins)
            flat_values = [value for record in list_record for value in record]
            print(flat_values)
            # Esecuzione batch utilizzando executemany per inserimenti massivi
            self.__db.execute_and_commit(ins, flat_values)
            print("Inserimento massivo completato con successo!")
            f.close()

        # Ripristino dell'output alla console
        sys.stdout = sys.__stdout__


    def is_not_empty(self, name_table: str) -> bool:
        sel = f"select count(*) from public.{name_table}"
        self.__db.execute(sel)
        row = self.__db.fetchOne()
        return row[0] > 0

    def count_records(self, name_table: str) -> int:
        sel = f"select count(*) from public.{name_table}"
        self.__db.execute(sel)
        row = self.__db.fetchOne()
        return row[0]

    def get_all_value_in_column(self, name_column, name_table) -> list:
        sel = f"select {name_column} from public.{name_table}"
        self.__db.execute(sel)
        rows = self.__db.fetchAll()
        if name_column == "*":
            all_value = [row for row in rows]
        else:
            all_value = [row[0] for row in rows]
        return all_value

    def get_select_with_where(self, select_columns, name_table: str, where_columns, values_column):

        if type(where_columns) == list:
            list_val = [[where_columns[i], f"{values_column[i]}"] if type(values_column[i]) == int
                        else [where_columns[i], f"'{values_column[i]}'"] for i in range(len(values_column))]
            a = " where " + " and ".join([" = ".join(x) for x in list_val])

        else:
            if type(values_column) == int or type(values_column) == bool:
                a = f" where {where_columns} = {values_column}"
            else:
                a = f" where {where_columns} = '{values_column}'"

        if type(select_columns) == list:
            sel_fin = f"select " + ", ".join(select_columns) + f" from public.{name_table}" + a
        else:
            sel_fin = f"select {select_columns} from public.{name_table}" + a

        # print(sel_fin)
        self.__db.execute(sel_fin)
        rows = self.__db.fetchAll()
        if type(select_columns) == list:
            all_value = [row for row in rows]
        else:
            all_value = [row[0] for row in rows]
        return all_value

    def delete_where_condition(self, name_table: str, where_columns, values_column):
        if type(where_columns) == list:
            list_val = [[where_columns[i], f"{values_column[i]}"] if type(values_column[i]) == int
                        else [where_columns[i], f"'{values_column[i]}'"] for i in range(len(values_column))]
            a = " where " + " and ".join([" = ".join(x) for x in list_val])

        else:
            if type(values_column) == int or type(values_column) == bool:
                a = f" where {where_columns} = {values_column}"
            else:
                a = f" where {where_columns} = '{values_column}'"

        del_str = f"delete from public.{name_table}" + a
        self.__db.execute_and_commit(del_str)

    def delete(self, name_table: str):
        del_str = f"delete from public.{name_table}"
        self.__db.execute_and_commit(del_str)

    def check_connections(self):
        sel = "select *  from pg_stat_activity"
        self.__db.execute(sel)
        rows = self.__db.fetchAll()
        return [row[0] for row in rows]

    def delete_DB(self):
        sel = "DROP database jshmvqsc"
        self.__db.execute_and_commit(sel)

    def show_tables_list(self):
        sel = "SELECT table_name FROM " \
              "information_schema.tables WHERE " \
              "table_schema='public' AND table_type='BASE TABLE';"
        self.__db.execute_and_commit(sel)
