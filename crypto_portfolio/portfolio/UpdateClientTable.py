import time

import pandas as pd
from . import DateFunction as dT
from . import TransfromDataBinance as tdb
from .BinanceService import BinanceService
from .CommonTable import CommonTable
from .CreateTables import engine_fin
from .DbService import DbService
from .UpdateTableService import UpdateTableService as Upd
from tqdm import tqdm
import pytz
from datetime import datetime


class UpdateClientTable:

    def __init__(self, user_id):

        self.db = DbService()
        self.df = pd.read_sql_table('portfolio_customuser', engine_fin)
        engine_fin.dispose()
        self.common = CommonTable(DbService=self.db)
        self.Upd = Upd()
        self.id_user = user_id

    def last_dividend_update_date(self):
        print("id utente:", self.id_user)
        return self.Upd.get_max_end_time_dividends(id_user=self.id_user)

    def update_user_dividends(self):
        """ Funzione per inserire tutti i dividendi dall'ultima data di aggiornamento"""

        # 1- Valorizza update_data data ultimo aggiornamneto

        # Recupera una data di aggiornamento dalla tabella public.update_table_date
        update_date = self.last_dividend_update_date()
        # Se non è avvenuto ancora un aggiornamento partiamo da 2017-01-01
        if update_date is None:
            # Definizione della data con fuso orario
            timezone = pytz.timezone("Europe/Rome")  # Specifica il fuso orario desiderato
            update_date = timezone.localize(datetime(2018, 1, 1))

        # Valorizza data di oggi
        end_date = dT.now_date()

        # 2- Raccogli i dividendi dalla data di ultimo aggiornamento
        row_user = self.df.query('id == @self.id_user')
        ser_bin = BinanceService(api_key=row_user['api_key'][0],
                                 api_secret=row_user['secret_key'][0],
                                 DbService=self.db)

        # 3 -Recuperiamo tutte le monete (asset) da analizzare
        asset_tot = self.db.get_all_value_in_column(name_column="coin", name_table="crypto")

        # Per ogni asset, otteniamo i dividendi
        all_div = []
        for asset in tqdm(asset_tot, desc="Searching Diviend for crypto"):
            # try:
            # Chiamata alla funzione per ottenere dividendi in intervalli di tempo
            dividends = ser_bin.fetch_dividends_in_intervals(asset=asset,
                                                             startTime=int(update_date.timestamp() * 1000),
                                                             # limit_div['start_timestamp'],
                                                             endTime=int(end_date.timestamp() * 1000),
                                                             # limit_div['end_timestamp'],
                                                             api_key=row_user['api_key'][0],
                                                             api_secret=row_user['secret_key'][0])

            # Se ci sono dividendi, li aggiungiamo alla lista
            if dividends:
                print("find dividend for: ", asset)
                for dividend in dividends:
                    tuple_div = tdb.get_tuple_dividends(id_user=self.id_user,
                                                        dividend=dividend)
                    # print(tuple_div)
                    all_div.append(tuple_div)
        # except Exception as ex:
        #   print(ex)
        if all_div:
            self.db.insert(name_table="dividends", list_record=all_div)

        self.Upd.insert_with_current_start_time(id_user=self.id_user,
                                                name_table="dividends")

    def update_dividends(self):

        update_date = self.last_update_date()
        timezone = pytz.timezone("UTC")
        update_date = timezone.localize(update_date)
        end_date = dT.now_date()

        all_div = []
        for index, row in self.df.iterrows():
            ser_bin = BinanceService(api_key=row['api_key'], api_secret=row['secret_key'],
                                     DbService=self.db)
            print("last login:", row['last_login'])
            print("update_date:", update_date)
            # limit_div = 0

            if row['last_login'] < update_date:
                limit_div = dT.limit(start_date=update_date, end_date=end_date)
                print(limit_div)
            else:
                limit_div = dT.limit(start_date=row['last_login'], end_date=end_date)
                print(limit_div)

            asset_tot = self.db.get_all_value_in_column(name_column="coin", name_table="crypto")
            for asset in asset_tot:
                try:
                    dividends = ser_bin.get_daily_div_history(asset=asset, limit=500)
                    if dividends:
                        for dividend in dividends:
                            tuple_div = tdb.get_tuple_dividends(id_user=row['id_user'],
                                                                dividend=dividend)
                            all_div.append(tuple_div)

                except Exception as ex:
                    if str(ex).startswith("APIError(code=-1121)"):
                        pass
                    elif str(ex).startswith("APIError(code=-1003)"):
                        time.sleep(60)
                        pass
                    else:
                        print(ex)
                        break

        if all_div:
            self.db.insert(name_table="dividends", list_record=all_div)

        self.Upd.insert_with_current_start_time(id_user=self.id_user,
                                                name_table="dividends")

    import pytz
    from datetime import datetime
    import time

    # Definizione della funzione aggiornata
    def update_dividends_RETR(self):

        update_date = self.last_update_date()  # Data dell'ultimo aggiornamento
        timezone = pytz.timezone("UTC")
        update_date = timezone.localize(update_date)  # Assicurati che la data sia consapevole del fuso orario UTC
        end_date = dT.now_date()  # Data finale (data corrente)

        all_div = []  # Lista per raccogliere i dividendi

        # Itera su ogni riga del DataFrame
        for index, row in self.df.iterrows():
            ser_bin = BinanceService(api_key=row['api_key'], api_secret=row['secret_key'],
                                     DbService=self.db)
            print("last login:", row['last_login'])
            print("update_date:", update_date)

            # Impostiamo i limiti di tempo per la ricerca dei dividendi
            if row['last_login'] > update_date:
                limit_div = dT.limit(start_date=update_date, end_date=end_date)
                print(limit_div)
            else:
                limit_div = dT.limit(start_date=row['last_login'], end_date=end_date)
                print(limit_div)

            # Recuperiamo tutte le monete (asset) da analizzare
            asset_tot = self.db.get_all_value_in_column(name_column="coin", name_table="crypto")

            # Per ogni asset, otteniamo i dividendi
            for asset in asset_tot:
                try:
                    # Chiamata alla funzione per ottenere dividendi in intervalli di tempo
                    dividends = ser_bin.fetch_dividends_in_intervals(asset=asset,
                                                                     startTime=int(update_date.timestamp() * 1000),
                                                                     # limit_div['start_timestamp'],
                                                                     endTime=int(end_date.timestamp() * 1000),
                                                                     # limit_div['end_timestamp'],
                                                                     api_key=row['api_key'],
                                                                     api_secret=row['secret_key'])

                    # Se ci sono dividendi, li aggiungiamo alla lista
                    if dividends:
                        for dividend in dividends:
                            tuple_div = tdb.get_tuple_dividends(id_user=row['id_user'], dividend=dividend)
                            print(tuple_div)
                            all_div.append(tuple_div)

                except Exception as ex:
                    # Gestione degli errori specifici
                    if str(ex).startswith("APIError(code=-1121)"):
                        pass
                    elif str(ex).startswith("APIError(code=-1003)"):
                        time.sleep(15)  # Attendere 60 secondi in caso di errore API -1003
                        pass
                    else:
                        print(ex)
                        break  # Se si verifica un altro errore, esci dal ciclo

        # Se ci sono dividendi da inserire nel database, li inseriamo
        if all_div:
            self.db.insert(name_table="dividends", list_record=all_div)

        # Aggiorniamo la tabella 'dividends' con il tempo di inizio dell'aggiornamento

    # self.Upd.insert_with_current_start_time(id_user=self.id_user, name_table="dividends")

    def update_orders(self):

        symbol_tot = self.db.get_all_value_in_column(name_column="symbol", name_table="symbols")
        update_date = self.last_update_date(name_table_update="orders")
        end_date = dT.now_date()

        all_orders = []
        for index, row in self.df.iterrows():
            ser_bin = BinanceService(api_key=row['api_key'], api_secret=row['api_secret'], DbService=self.db)
            if row['date_registration'] < update_date:
                start_date = update_date
            else:
                start_date = row['registration_date']

            start_date = dT.datetime_to_milliseconds_int(input_data=start_date)
            end_date = dT.datetime_to_milliseconds_int(input_data=end_date)

            for pair in symbol_tot:
                try:
                    orders = ser_bin.get_orders(symbol=pair, start_time=start_date, end_time=end_date)
                    if orders:
                        for order in orders:
                            tuple_orders = tdb.get_tuple_orders(id_user=row['id_user'], order=order)
                            all_orders.append(tuple_orders)

                except Exception as ex:
                    if str(ex).startswith("APIError(code=-1121)"):
                        pass
                    elif str(ex).startswith("APIError(code=-1003)"):
                        time.sleep(60)
                        pass
                    else:
                        print(ex)
                        break

        if all_orders:
            self.db.insert(name_table="orders", list_record=all_orders)
        self.common.update_update_table(name_table="orders", end_date=end_date)

    def update_trades(self):

        symbol_orders = self.db.get_all_value_in_column(name_column="symbol", name_table="orders")
        update_date = self.last_update_date(name_table_update="trades")
        end_date = dT.now_date()

        all_trade = []
        for index, row in self.df.iterrows():
            ser_bin = BinanceService(api_key=row['api_key'], api_secret=row['api_secret'], DbService=self.db)
            if row['date_registration'] < update_date:
                start_date = update_date
            else:
                start_date = row['registration_date']
            start_date = dT.datetime_to_milliseconds_int(input_data=start_date)
            end_date = dT.datetime_to_milliseconds_int(input_data=end_date)

            for pair in symbol_orders:
                try:
                    trades = ser_bin.get_trades(symbol=pair[0], start_time=start_date, end_time=end_date)
                    for trade in trades:
                        tuple_trade = tdb.get_tuple_trades(id_user=row['id_user'], trade=trade)
                        all_trade.append(tuple_trade)

                except Exception as ex:
                    if str(ex).startswith("APIError(code=-1121)"):
                        pass
                    elif str(ex).startswith("APIError(code=-1003)"):
                        time.sleep(60)
                        pass
                    else:
                        print(ex)
                        break
        if all_trade:
            self.db.insert(name_table="trades", list_record=all_trade)

        self.common.update_update_table(name_table="trades", end_date=end_date)

    def update_deposit_crypto(self):

        update_date = self.last_update_date(name_table_update="deposits_crypto")
        end_date = dT.now_date()

        all_deposit = []
        for index, row in self.df.iterrows():
            ser_bin = BinanceService(api_key=row['api_key'], api_secret=row['api_secret'], DbService=self.db)
            if row['date_registration'] < update_date:
                start_date = update_date
            else:
                start_date = row['registration_date']

            start_date = dT.datetime_to_milliseconds_int(input_data=start_date)
            end_date = dT.datetime_to_milliseconds_int(input_data=end_date)

            deposits = ser_bin.get_deposit_crypto(start_date=start_date, end_date=end_date)
            if deposits:
                for deposit in deposits:
                    tuple_deposit = tdb.get_tuple_deposit_crypto(id_user=row['id_user'], dep=deposit)
                    all_deposit.append(tuple_deposit)

        if all_deposit:
            self.db.insert(name_table="deposits_crypto", list_record=all_deposit)

        self.common.update_update_table(name_table="deposits_crypto", end_date=end_date)

    def update_withdraw_crypto(self):
        update_date = self.last_update_date(name_table_update="withdraw_crypto")
        end_date = dT.now_date()

        all_withdraw = []
        for index, row in self.df.iterrows():
            ser_bin = BinanceService(api_key=row['api_key'], api_secret=row['api_secret'], DbService=self.db)
            if row['date_registration'] < update_date:
                start_date = update_date
            else:
                start_date = row['registration_date']

            start_date = dT.datetime_to_milliseconds_int(input_data=start_date)
            end_date = dT.datetime_to_milliseconds_int(input_data=end_date)

            withdraw_crypto = ser_bin.get_withdraw_crypto(start_date=start_date, end_date=end_date)

            if withdraw_crypto:
                for withdraw in withdraw_crypto:
                    if 'confirmNo' in withdraw:
                        tuple_withdraw = tdb.get_tuple_withdraw_crypto(id_user=row['id_user'], withdraw=withdraw)
                        all_withdraw.append(tuple_withdraw)

        if all_withdraw:
            self.db.insert(name_table="withdraw_crypto", list_record=all_withdraw)

        self.common.update_update_table(name_table="withdraw_crypto", end_date=end_date)

    def update_deposit_withdraw_fiat(self, withdraws_deposits: str):

        # 1- Valorizza update_data data ultimo aggiornamneto

        # Recupera una data di aggiornamento dalla tabella public.update_table_date
        update_date = self.last_dividend_update_date()
        # Se non è avvenuto ancora un aggiornamento partiamo da 2017-01-01
        if update_date is None:
            # Definizione della data con fuso orario
            timezone = pytz.timezone("Europe/Rome")  # Specifica il fuso orario desiderato
            update_date = timezone.localize(datetime(2017, 1, 1))

        # Valorizza data di oggi
        end_date = dT.now_date()

        # 2- Raccogli i dividendi dalla data di ultimo aggiornamento
        row_user = self.df.query('id == @self.id_user')
        ser_bin = BinanceService(api_key=row_user['api_key'][0],
                                 api_secret=row_user['secret_key'][0],
                                 DbService=self.db)
        all_fiat = []


        """ 
        start_date = dT.datetime_to_milliseconds_int(input_data=update_date)
        end_date = dT.datetime_to_milliseconds_int(input_data=end_date)
        if withdraws_deposits == "deposit":
            dep_fiat = ser_bin.get_deposit_fiat(start_date=start_date, end_date=end_date)
            print(dep_fiat)
            if len(dep_fiat['data']) > 0:
                if 'data' in dep_fiat:
                    for deposit in dep_fiat['data']:
                        tuple_deposits = tdb.get_tuple_deposit_withdraw_fiat(id_user=self.id_user,
                                                                             dep=deposit,
                                                                             tran_type="D")
                        print(tuple_deposits)
                        all_fiat.append(tuple_deposits)

            else:
                withdraw_fiat = ser_bin.get_withdraw_fiat(start_date=start_date, end_date=end_date)
                if len(withdraw_fiat['data']) > 0:
                    if 'data' in withdraw_fiat:
                        for withdraw in withdraw_fiat['data']:
                            tuple_withdraws = tdb.get_tuple_deposit_withdraw_fiat(id_user=self.id_user,
                                                                                  dep=withdraw,
                                                                                  tran_type="W")
                            all_fiat.append(tuple_withdraws)
        """
        if all_fiat:
            self.db.insert(name_table="deposit_withdraw_fiat", list_record=all_fiat)

        # self.common.update_update_table(name_table="deposit_withdraw_fiat", end_date=end_date)

    def update_buy_sell_fiat(self, buy_sell: str):
        # 1- Valorizza update_data data ultimo aggiornamneto

        # Recupera una data di aggiornamento dalla tabella public.update_table_date
        update_date = self.last_dividend_update_date()
        # Se non è avvenuto ancora un aggiornamento partiamo da 2017-01-01
        if update_date is None:
            # Definizione della data con fuso orario
            timezone = pytz.timezone("Europe/Rome")  # Specifica il fuso orario desiderato
            update_date = timezone.localize(datetime(2017, 1, 1))

        # Valorizza data di oggi
        end_date = dT.now_date()

        # 2- Raccogli i dividendi dalla data di ultimo aggiornamento
        row_user = self.df.query('id == @self.id_user')
        ser_bin = BinanceService(api_key=row_user['api_key'][0],
                                 api_secret=row_user['secret_key'][0],
                                 DbService=self.db)

        all_transaction = []
        start_date = dT.datetime_to_milliseconds_int(input_data=update_date)
        end_date = dT.datetime_to_milliseconds_int(input_data=end_date)

        if buy_sell == "buy":
            purchase_cx_fiat = ser_bin.get_purchase_cx_fiat(start_date=start_date, end_date=end_date)

            if 'data' in purchase_cx_fiat:
                if len(purchase_cx_fiat['data']) > 0:
                    for purchase in purchase_cx_fiat['data']:
                        tuple_transaction = tdb.get_tuple_buy_sell_fiat(id_user=self.id_user,
                                                                        buy_sell=purchase,
                                                                        tran_type="B")
                        all_transaction.append(tuple_transaction)

        else:
            sell_cx_fiat = ser_bin.get_sell_cx_fiat(start_date=start_date, end_date=end_date)
            if 'data' in sell_cx_fiat:
                if len(sell_cx_fiat['data']) > 0:
                    for sell in sell_cx_fiat['data']:
                        tuple_sell = tdb.get_tuple_buy_sell_fiat(id_user=self.id_user,
                                                                 buy_sell=sell,
                                                                 tran_type="S")
                        all_transaction.append(tuple_sell)

        if all_transaction:
            print(all_transaction)
            self.db.insert(name_table="buy_sell_fiat", list_record=all_transaction)

            # self.common.update_update_table(name_table="buy_sell_fiat", end_date=end_date)

    def update_buy_fiat(self):
        # 1- Valorizza update_data data ultimo aggiornamneto

        # Recupera una data di aggiornamento dalla tabella public.update_table_date
        update_date = self.last_dividend_update_date()
        # Se non è avvenuto ancora un aggiornamento partiamo da 2017-01-01
        if update_date is None:
            # Definizione della data con fuso orario
            timezone = pytz.timezone("Europe/Rome")  # Specifica il fuso orario desiderato
            update_date = timezone.localize(datetime(2017, 1, 1))

        # Valorizza data di oggi
        end_date = dT.now_date()

        # 2- Raccogli i dividendi dalla data di ultimo aggiornamento
        row_user = self.df.query('id == @self.id_user')
        ser_bin = BinanceService(api_key=row_user['api_key'][0],
                                 api_secret=row_user['secret_key'][0],
                                 DbService=self.db)

        all_transaction = []
        start_date = dT.datetime_to_milliseconds_int(input_data=update_date)
        end_date = dT.datetime_to_milliseconds_int(input_data=end_date)

        history = ser_bin.fetch_fiat_history_from_origin()
        return history


    def update_all_table(self):
        # self.common.update_crypto()
        # self.common.update_symbols()
        # self.update_dividends_RETR()
        history = self.update_buy_fiat()
        print(history)
        #self.update_deposit_withdraw_fiat(withdraws_deposits="deposit")
        # self.update_user_dividends()
        # self.update_dividends()
        # self.update_orders()
        # self.update_trades()
        #self.update_deposit_crypto()
        # self.update_deposit_withdraw_fiat(withdraws_deposits="deposit")
        # self.update_deposit_withdraw_fiat(withdraws_deposits="withdraw")
        # self.update_withdraw_crypto()
        # self.update_buy_sell_fiat(buy_sell="buy")
        # self.update_buy_sell_fiat(buy_sell="sell")
