from datetime import datetime

import pandas as pd
from tqdm import tqdm
import time
from . import DateFunction as dT
from .BinanceService import BinanceService
from .CreateTables import engine_fin
from .DbService import DbService
from .InsertValueInTable import InsertValueInTable

import sys


class CommonTable:  # Update_csn (Crypto, Symbols, Networks)

    def __init__(self, DbService: DbService):
        self.db = DbService
        self.df = pd.read_sql_table('portfolio_customuser', engine_fin, index_col='id').reset_index()
        engine_fin.dispose()
        self.df_symbols = pd.read_sql_table(table_name="symbols", con=engine_fin)
        engine_fin.dispose()
        self.api_key = self.df.loc[self.df['id'] == 4, 'api_key'].values[0]
        self.api_secret = self.df.loc[self.df['id'] == 4, 'secret_key'].values[0]
        self.ser_bin = BinanceService(api_key=self.api_key, api_secret=self.api_secret, DbService=DbService)
        self.ins_tab = InsertValueInTable(api_key=self.api_key, api_secret=self.api_secret, DbService=self.db)

    def first_insert_common_table(self):
        self.ins_tab.insert_Crypto()
        self.ins_tab.insert_symbols()
        self.ins_tab.insert_networks()

    def update_update_table(self, record):

        # if self.db.count_records(name_table="update_table") != 10:
        self.db.insert(name_table='update_table', list_record=record)

    # else:
    #     self.db.delete_where_condition(name_table='update_table', where_columns="name_table",
    #                                    values_column=name_table)
    #     self.db.insert(name_table='update_table', list_record=[name_table, end_date])

    def update_crypto(self):
        end_date = dT.now_date()
        crypto_db = self.db.get_all_value_in_column(name_column='coin', name_table='crypto')
        coins_list = self.ser_bin.get_coins()
        coins_bin = [coin['coin'] for coin in self.ser_bin.get_coins()]
        crypto_to_add = list(set(coins_bin) - set(crypto_db))
        crypto_to_del = list(set(crypto_db) - set(coins_bin))

        #print("crypto da aggiungere")
        #print(crypto_to_add)

        if crypto_to_del:
            for crypto in crypto_to_del:
                self.db.delete_where_condition(name_table='crypto', where_columns='coin', values_column=crypto)
        # print(self.ser_bin.get_coins())
        add_list = []
        if crypto_to_add:

            for coin in tqdm(coins_bin, desc="Crypto's table upsert"):
                for coin1 in coins_list:

                    # print("Coin1 è:",coin1)
                   # time.sleep(10)
                    # print(coin1['coin'])
                    if coin1['coin'] in crypto_to_add:
                        #print("coin1 è:", coin1['coin'])
                        row = (coin1['coin'],
                               coin1['name'],
                               coin1['withdrawAllEnable'],
                               coin1['trading'],
                               coin1['networkList'][0]['withdrawEnable'],
                               end_date,
                               '31129999'
                               )
                        #print(row)
                        add_list.append(row)
        #print(len(add_list))
        #print("procedi a inserimento massivo")
        if add_list:
            self.db.insert_bulk(name_table="crypto",
                                name_columns=self.db.name_columns("crypto"),
                                list_record=add_list)
        print("aggiornamento crypto completato")
        # for row in tqdm(add_list, desc="Crypto's table upsert"):
        #    self.db.insert(name_table="crypto", list_record=row)
        # self.db.massive_insert()
        # self.update_update_table(name_table="crypto", end_date=end_date)

    def update_symbols(self):
        end_date = dT.now_date()
        symbols_db = self.db.get_all_value_in_column(name_column='symbol', name_table='symbols')
        symbol_data = self.ser_bin.get_symbols()
        symbols_bin = [symbol['symbol'] for symbol in symbol_data]

        symbols_to_add = list(set(symbols_bin) - set(symbols_db))
        symbols_to_del = list(set(symbols_db) - set(symbols_bin))

        print("symboli da aggiungere")
        # print(symbols_to_add)
        if symbols_to_del:
            for symbol in symbols_to_del:
                self.db.delete_where_condition(name_table='symbols', where_columns='symbol', values_column=symbol)

        add_symbols = []
        if symbols_to_add:
            for i in range(len(symbols_bin)):
                if symbols_bin[i] in symbols_to_add:
                    add_symbols.append((symbol_data[i]['symbol'],
                                        symbol_data[i]['baseAsset'],
                                        symbol_data[i]['quoteAsset'],
                                        end_date,
                                        '31129999'))
        # print(type(add_symbols[0]))
        print("procedi a inserimento massivo")
        if add_symbols:
            # for symb in tqdm(add_symbols, desc="Symbol's table upsert"):
            self.db.insert_bulk(name_table='symbols',
                                name_columns=self.db.name_columns(name_table="symbols"),
                                list_record=add_symbols)
        print("aggiornamento symbols completato")

        # self.update_update_table(name_table="symbols", end_date=end_date)

    def get_valid_ticker(self, coin: str, quote: str) -> str:
        ticker = ""
        try:
            ticker = self.df_symbols.loc[(self.df_symbols['base_asset'] == coin) &
                                         (self.df_symbols['quote_asset'] == quote), 'symbol'].values[0]
        except IndexError as ex:
            try:
                ticker = self.df_symbols.loc[(self.df_symbols['base_asset'] == quote) &
                                             (self.df_symbols['quote_asset'] == coin), 'symbol'].values[0]
            except IndexError as ex:
                print(ex)
        return ticker
