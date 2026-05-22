import pandas as pd

from .DbDAO import DbDao


class DbService:

    def __init__(self):
        self.__dao = DbDao()

    def name_columns(self, name_table: str):
        return self.__dao.name_columns(name_table=name_table)

    def insert(self, name_table: str, list_record: list):
        name_columns = self.__dao.name_columns(name_table=name_table)
         #print(name_columns)
        #print(list_record[0])
        return self.__dao.insert(name_table=name_table, name_columns=name_columns, list_record=list_record)

    def insert_bulk(self, name_table: str, name_columns: list, list_record: list):
        return self.__dao.insert_bulk(name_table=name_table, name_columns=name_columns, list_record=list_record)

    def is_not_empty(self, name_table: str) -> bool:
        return self.__dao.is_not_empty(name_table=name_table)

    def count_records(self, name_table: str) -> int:
        return self.__dao.count_records(name_table=name_table)

    def get_all_value_in_column(self, name_column, name_table) -> list:
        return self.__dao.get_all_value_in_column(name_column=name_column, name_table=name_table)

    def get_select_with_where(self, select_columns, name_table: str, where_columns, values_column):
        return self.__dao.get_select_with_where(select_columns=select_columns, name_table=name_table,
                                                where_columns=where_columns, values_column=values_column)

    def get_df_select_with_where(self, select_columns, name_table: str, where_columns, values_column):
        select = self.__dao.get_select_with_where(select_columns=select_columns, name_table=name_table,
                                                  where_columns=where_columns, values_column=values_column)

        return pd.DataFrame(data=select, columns=select_columns)

    def delete_where_condition(self, name_table: str, where_columns, values_column):
        self.__dao.delete_where_condition(name_table=name_table, where_columns=where_columns,
                                          values_column=values_column)

    def delete(self, name_table: str):
        self.__dao.delete(name_table=name_table)

    def check_connections(self):
        self.__dao.check_connections()

    def delete_DB(self):
        self.__dao.delete_DB()

    def show_tables_list(self):
        self.__dao.show_tables_list()