from datetime import datetime
from pandas import DataFrame
from .BinanceDAO import BinanceDAO
from .DbService import DbService
import time
import hashlib
import hmac
import requests
from .DateFunction import date_to_timestamp
import pytz


def get_top_10(changes: DataFrame, limit: int = 10) -> DataFrame:
    return changes.sort_values(by='priceChangePercent', ascending=False).head(limit).set_index('Symbol')


def get_worst_10(changes: DataFrame, limit: int = 10) -> DataFrame:
    return changes.set_index('Symbol').sort_values(by='priceChangePercent', ascending=True).head(limit)


class BinanceService:

    def __init__(self, DbService: DbService, api_key: str, api_secret: str):
        self.__dao = BinanceDAO(DbService=DbService, api_key=api_key, api_secret=api_secret)

    # Funzione per ottenere i dividendi
    def get_asset_dividend_history(self, asset, startTime, endTime, api_key, api_secret):
        base_url = 'https://api.binance.com'
        endpoint = '/sapi/v1/asset/assetDividend'

        # Parametri obbligatori
        params = {
            'asset': asset,  # asset come input
            'startTime': startTime,  # in millisecondi
            'endTime': endTime,  # in millisecondi
            'timestamp': int(time.time() * 1000),  # Timestamp in millisecondi
        }

        # Calcolare la firma
        query_string = '&'.join([f"{key}={value}" for key, value in params.items()])
        signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

        # Aggiungere la firma ai parametri
        params['signature'] = signature

        # Intestazioni per la richiesta
        headers = {
            'X-MBX-APIKEY': api_key
        }

        # Effettuare la richiesta GET con i parametri firmati
        try:
            response = requests.get(base_url + endpoint, headers=headers, params=params)
            # Se la risposta è positiva, restituire i dati
            if response.status_code == 200:
                return response.json()
            else:
                # In caso di errore, restituisce il messaggio di errore
                return response.json()
        except Exception as e:
            return {'error': str(e)}

    # Funzione per dividere l'intervallo in cicli più piccoli se la differenza tra le date è maggiore di 500
    def fetch_dividends_in_intervals(self, asset, startTime, endTime, api_key, api_secret):
        # print("fetch dividend for asset: ", asset)
        # Calcolare la differenza in giorni (millisecondi)
        difference = endTime - startTime

        # Se la differenza è maggiore di 500 ms, dividiamo l'intervallo in cicli
        if difference > 2592000000:
            cycle_interval = difference // 2592000000  # Numero di intervalli di 500 ms

            # Crea una lista di richieste che iterano tra i cicli
            results = []
            for i in range(int(cycle_interval)):
                # Calcolare il tempo di inizio e fine per ogni ciclo
                cycle_start = startTime + i * 2592000000
                cycle_end = cycle_start + 2592000000

                # Eseguire la chiamata per il ciclo
                result = self.get_asset_dividend_history(asset, cycle_start, cycle_end, api_key, api_secret)
                # print(result)
                if result['total'] > 0:
                    #   print(result)
                    results.append(result['total'])
                else:
                    timezone = pytz.timezone("Europe/Rome")
                #  print("No Div in", datetime.fromtimestamp(cycle_start/ 1000, tz=timezone),
                #        datetime.fromtimestamp(cycle_end/ 1000, tz=timezone))

            return results
        else:
            # Se la differenza è minore di 500 ms, effettua una sola chiamata
            return [self.get_asset_dividend_history(asset,
                                                    datetime.fromtimestamp(startTime),
                                                    datetime.fromtimestamp(endTime),
                                                    api_key,
                                                    api_secret)]

    def get_flexible_position(self, coin: str):
        return self.__dao.get_flexible_position(coin=coin)

    def get_coins(self):
        return self.__dao.get_coins()

    def get_symbols(self):
        return self.__dao.get_symbols()

    def get_account_snap(self):
        return self.__dao.get_account_snap()

    def get_df_symbol24H(self):
        symbol_24H = (self.__dao.get_all_symbol_24H())

        header = {'symbol': [],
                  'priceChangePercent': [],
                  'prevClosePrice': []}
        df_24H_symbol = DataFrame(data=header)
        for symbol in symbol_24H:
            df_24H_symbol.loc[len(df_24H_symbol)] = [symbol['symbol'],
                                                     symbol['priceChangePercent'],
                                                     symbol['prevClosePrice']]
        return df_24H_symbol

    def get_df_account_snap(self):
        hodl_asset = self.__dao.get_account_snap()
        data = {"asset": [],
                "free": [],
                "locked": [],
                "tot": []}
        df_asset = DataFrame(data=data)
        for asst in hodl_asset:
            if asst['free'] != asst['locked']:
                if asst['free'] != '0':
                    # print([asst['asset'], asst['free'], asst['locked']])
                    if asst['asset'][:2] == "LD":

                        df_asset.loc[len(df_asset)] = [asst['asset'][2:], asst['locked'], asst['free'],
                                                       float(asst['locked']) + float(asst['free'])]
                    else:
                        df_asset.loc[len(df_asset)] = [asst['asset'], asst['free'], asst['locked'],
                                                       float(asst['locked']) + float(asst['free'])]
        return df_asset

    def get_orders(self, symbol: str, start_time: int = None, end_time: int = None):
        return self.__dao.get_orders(symbol=symbol, start_time=start_time, end_time=end_time)

    def get_trades(self, symbol: str, start_time: int = None, end_time: int = None):
        return self.__dao.get_trades(symbol=symbol, start_time=start_time, end_time=end_time)

    def get_deposit_crypto(self, start_date: int, end_date: int):
        return self.__dao.get_deposit_crypto(start_date=start_date, end_date=end_date)

    def get_withdraw_crypto(self, start_date: int, end_date: int):
        return self.__dao.get_withdraw_crypto(start_date=start_date, end_date=end_date)

    def get_deposit_fiat(self, start_date: int, end_date: int):
        return self.__dao.get_deposit_fiat(start_date=start_date, end_date=end_date)

    def get_withdraw_fiat(self, start_date: int, end_date: int):
        return self.__dao.get_withdraw_fiat(start_date=start_date, end_date=end_date)

    def get_purchase_cx_fiat(self, start_date: int, end_date: int):
        return self.__dao.get_purchase_cx_fiat(start_date=start_date, end_date=end_date)

    def get_sell_cx_fiat(self, start_date: int, end_date: int):
        return self.__dao.get_sell_cx_fiat(start_date=start_date, end_date=end_date)

    def get_price_historical_kline(self, symbol: str, interval: str, start_date: datetime = None,
                                   end_date: datetime = None):
        return self.__dao.get_price_historical_kline(symbol=symbol, interval=interval, start_date=start_date,
                                                     end_date=end_date)

    def get_prev_close_price(self, symbol: str):
        return self.__dao.get_prev_close_price(symbol=symbol)

    def get_actual_price(self, symbol: str):
        return self.__dao.get_actual_price(symbol=symbol)

    def get_symbol_24H(self, symbol: str):
        return self.__dao.get_symbol_24H(symbol=symbol)

    def get_PriceChange24H(self, quote: str) -> DataFrame:
        return self.__dao.get_PriceChange24H(quote=quote)

    def get_coin_snapshot(self, coin: str):
        return self.__dao.get_coin_snapshot(coin=coin)

    def get_holding_asset(self):
        return self.__dao.get_holding_asset()

    def get_desc_asset_list(self):
        return self.__dao.get_desc_asset_list()

    def get_daily_div_history(self, asset: str = None, limit: int = None):
        return self.__dao.get_daily_div_history(asset=asset, limit=limit)

    def get_fiat_deposit_history(self):
        return self.__dao.get_fiat_deposit_history()

    def get_crypto_to_insert(self) -> list:
        return self.__dao.get_crypto_to_insert()

    def get_buy_sell_fiat_to_insert(self, transaction_type: int, start_time: int, end_time: int) -> list:
        return self.__dao.get_buy_sell_fiat_to_insert(transaction_type=transaction_type, start_time=start_time,
                                                      end_time=end_time)

    def get_deposit_crypto_to_insert(self, start_time: int, end_time: int):
        return self.__dao.get_deposit_crypto_to_insert(start_time=start_time, end_time=end_time)

    def get_deposit_withdraw_fiat_to_insert(self, transaction_type: int, start_time: int, end_time: int):
        return self.__dao.get_deposit_withdraw_fiat_to_insert(transaction_type=transaction_type,
                                                              start_time=start_time, end_time=end_time)

    def get_dividends_to_insert(self, asset: str = None, limit: int = None):
        return self.__dao.get_dividends_to_insert(asset=asset, limit=limit)

    def get_orders_to_insert(self, symbol: str) -> list:
        return self.__dao.get_orders_to_insert(symbol=symbol)

    def get_networks_to_insert(self):
        return self.__dao.get_networks_to_insert()

    def get_symbols_to_insert(self) -> list:
        return self.__dao.get_symbols_to_insert()

    def get_trades_to_insert(self, symbol: str) -> list:
        return self.__dao.get_trades_to_insert(symbol=symbol)

    def get_withdraw_crypto_to_insert(self, start_time: int, end_time: int) -> list:
        return self.__dao.get_withdraw_crypto_to_insert(start_time=start_time, end_time=end_time)

    def get_exchange_info(self):
        return self.__dao.get_exchange_info()

    def fetch_fiat_history_from_date(self, start_date):
        # Data di inizio (1 gennaio 2017) e data di fine (oggi)
        # start_date = "2017-01-01"
        end_date = datetime.today().strftime("%Y-%m-%d")

        # Converti le date in timestamp
        start_timestamp = date_to_timestamp(start_date)
        end_timestamp = date_to_timestamp(end_date)

        # Imposta la finestra di intervallo (500 giorni)
        max_days = 500
        current_start = start_timestamp
        current_end = min(current_start + max_days * 86400000, end_timestamp)  # 86400000 ms in un giorno

        # Ciclo per recuperare i dati in finestre di 500 giorni
        all_history = []
        while current_start < end_timestamp:
            # Chiama l'API con la finestra corrente
            response = self.get_deposit_fiat(start_date=current_start,
                                             end_date=current_end)
            # print(response)
            if response and 'data' in response:
                all_history.extend(response['data'])  # Aggiungi i dati alla lista
                # print(f"Recuperati {len(response['data'])} record tra {current_start} e {current_end}")

            # Aggiorna il periodo per la prossima richiesta
            current_start = current_end + 1
            current_end = min(current_start + max_days * 86400000, end_timestamp)  # Next window

        return all_history

    def fetch_fiat_history_from_origin(self):
        # Data di inizio (1 gennaio 2017) e data di fine (oggi)
        start_date = "2017-01-01"
        all_history = self.fetch_fiat_history_from_date(start_date="2017-01-01")

        return all_history
