import time
from datetime import datetime
from datetime import timedelta

from tqdm import tqdm

from . import DateFunction as dT
from .BinanceService import BinanceService
from .DbService import DbService


class InsertValueInTable:

    def __init__(self,
                 DbService: DbService,
                 api_key: str,
                 api_secret: str):

        self.ser_db = DbService
        self.ser_bin = BinanceService(DbService=DbService, api_key=api_key, api_secret=api_secret)

    def insert_deposit_withdraw(self):
        start_date = datetime(2017, 1, 1)
        end_date = datetime.today()
        delta = timedelta(days=30)
        all_deposit_crypto = []
        all_withdraw_crypto = []
        all_dep_with_fiat = []
        buy_sell_fiat = []
        count_chiamate = 0
        print(count_chiamate)
        while start_date <= end_date:
            if count_chiamate >= 8:
                time.sleep(50/1000)
                count_chiamate = 0
                end_data = start_date + delta
                start_date_ins = dT.datetime_to_milliseconds_int(start_date)
                end_date_ins = dT.datetime_to_milliseconds_int(end_data)

                deposit_crypto = self.ser_bin.get_deposit_crypto_to_insert(start_time=start_date_ins,
                                                                           end_time=end_date_ins)
                count_chiamate +=1
                print(count_chiamate)
                if deposit_crypto is not None:
                    all_deposit_crypto.append(deposit_crypto)

                withdraw_crypto = self.ser_bin.get_withdraw_crypto_to_insert(start_time=start_date_ins,
                                                                             end_time=end_date_ins)
                count_chiamate +=1
                print(count_chiamate)
                if withdraw_crypto is not None:
                    all_withdraw_crypto.append(withdraw_crypto)

                deposit_fiat = self.ser_bin.get_deposit_withdraw_fiat_to_insert(transaction_type=0,
                                                                                start_time=start_date_ins,
                                                                                end_time=end_date_ins)
                count_chiamate +=1
                print(count_chiamate)
                if deposit_fiat is not None:
                    all_dep_with_fiat.append(deposit_fiat)

                withdraw_fiat = self.ser_bin.get_deposit_withdraw_fiat_to_insert(transaction_type=1,
                                                                                 start_time=start_date_ins,
                                                                                 end_time=end_date_ins)
                count_chiamate +=1
                print(count_chiamate)
                if withdraw_fiat is not None:
                    all_dep_with_fiat.append(withdraw_fiat)

                purchase_cx_fiat = self.ser_bin.get_buy_sell_fiat_to_insert(transaction_type=0, start_time=start_date_ins,
                                                                            end_time=end_date_ins)
                count_chiamate +=1
                print(count_chiamate)
                if purchase_cx_fiat is not None:
                    buy_sell_fiat.append(purchase_cx_fiat)

                sell_cx_fiat = self.ser_bin.get_buy_sell_fiat_to_insert(transaction_type=1, start_time=start_date_ins,
                                                                        end_time=end_date_ins)
                count_chiamate +=1
                print(count_chiamate)
                if sell_cx_fiat is not None:
                    buy_sell_fiat.append(sell_cx_fiat)

                start_date += delta + timedelta(days=1)

        all_deposit_crypto = sum(all_deposit_crypto, [])
        all_withdraw_crypto = sum(all_withdraw_crypto, [])
        all_dep_with_fiat = sum(all_dep_with_fiat, [])
        buy_sell_fiat = sum(buy_sell_fiat, [])

        for deposit in all_deposit_crypto:
            self.ser_db.insert(name_table="deposits_crypto", list_record=deposit)
        for withraw in all_withdraw_crypto:
            self.ser_db.insert(name_table="withdraw_crypto", list_record=withraw)
        for dep_fiat in all_dep_with_fiat:
            self.ser_db.insert(name_table="deposit_withdraw_fiat", list_record=dep_fiat)
        for fiat in buy_sell_fiat:
            self.ser_db.insert(name_table="buy_sell_fiat", list_record=fiat)

    def insert_dividends(self):
        asset_tot = self.ser_db.get_all_value_in_column(name_column="coin", name_table="crypto")

        dividends = self.ser_bin.get_dividends_to_insert(limit=500)
        if len(dividends) < 500:
            self.ser_db.insert(name_table="dividends", list_record=dividends)
        else:
            all_dividends = []
            for asset in tqdm(asset_tot):
                try:
                    dividends = self.ser_bin.get_dividends_to_insert(asset=asset, limit=500)
                    if dividends is not None:
                        all_dividends.append(dividends)
                except Exception as ex:
                    if str(ex).startswith("APIError(code=-1121)"):
                        pass
                    elif str(ex).startswith("APIError(code=-1003)"):
                        time.sleep(60)
                        pass
                    else:
                        print(ex)
                        break
            all_dividends = sum(all_dividends, [])
            for dividend in all_dividends:
                self.ser_db.insert(name_table="dividends", list_record=dividend)

    def insert_orders(self):
        symbols = self.ser_db.get_all_value_in_column(name_column="symbol", name_table="symbols")


        all_order = []
        for symbol in tqdm(symbols):
            try:
                orders = self.ser_bin.get_orders_to_insert(symbol=symbol)
                if orders is not None:
                    all_order.append(orders)
                   # print(orders)
            except Exception as ex:
                if str(ex).startswith("APIError(code=-1121)"):
                    pass
                elif str(ex).startswith("APIError(code=-1003)"):
                    time.sleep(60)
                    pass
                else:
                    print(ex)
                    break

        all_order = sum(all_order, [])
        for order in all_order:
            self.ser_db.insert(name_table="orders", list_record=order)

    def insert_Crypto(self):
        if not self.ser_db.is_not_empty(name_table="crypto"):
            coins = self.ser_bin.get_crypto_to_insert()
            for coin in coins:
                self.ser_db.insert(name_table="crypto", list_record=coin)
            return coins

    def insert_symbols(self):
        if not self.ser_db.is_not_empty(name_table="symbols"):
            symbols = self.ser_bin.get_symbols_to_insert()
            for symbol in symbols:
                self.ser_db.insert(name_table="symbols", list_record=symbol)
            return symbols

    def insert_networks(self):
        if not self.ser_db.is_not_empty(name_table="networks"):
            networks = self.ser_bin.get_networks_to_insert()

            for network in networks:
                #network = [network, str(datetime.today()), '3112999']
                self.ser_db.insert(name_table="networks", list_record=network)
            return networks

    def insert_trades(self):
        symbols = self.ser_db.get_all_value_in_column(name_column=" distinct symbol", name_table="orders")

        all_trades = []
        for symbol in tqdm(symbols):
            try:
                trades = self.ser_bin.get_trades_to_insert(symbol=symbol)
                if trades is not None:
                    all_trades.append(trades)

            except Exception as ex:
                if str(ex).startswith("APIError(code=-1121)"):
                    pass
                elif str(ex).startswith("APIError(code=-1003)"):
                    time.sleep(60)
                    pass
                else:
                    print(ex)
                    break

        all_trades = sum(all_trades, [])
        for trades in all_trades:
            self.ser_db.insert(name_table="trades", list_record=trades)
