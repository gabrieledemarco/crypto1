from datetime import datetime
from datetime import timedelta

import pandas as pd
from binance.client import Client
from pandas import DataFrame
from tqdm import tqdm

from .Binance_Exception import BinanceException
from .DbService import DbService


class BinanceDAO:

    def __init__(self, DbService: DbService, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = Client(api_key=self.api_key, api_secret=self.api_secret)
        self.db = DbService
        self.id_user = self.db.get_select_with_where(select_columns='id',
                                                     name_table='portfolio_customuser',
                                                     where_columns='api_key',
                                                     values_column=api_key)[0]

    def get_account_snap(self):
        """
              Desc: Return Amount detected from in SPOT Account
              Input:
                  coin:str
              Output:
                  Amount = Amount('free') + Amount('locked')


                #-- Amount('locked') are amounts of coin locked in an OPEN TRADE
              """

        account_asset_list = self.client.get_account_snapshot(type="SPOT")['snapshotVos'][0]['data']['balances']
        return account_asset_list

    def get_coins(self):
        return self.client.get_all_coins_info()

    def get_symbols(self):
        return self.client.get_exchange_info()['symbols']

    def get_orders(self, symbol: str, start_time: int = None, end_time: int = None):
        return self.client.get_all_orders(symbol=symbol, startTime=start_time, endTime=end_time)

    def get_trades(self, symbol: str, start_time: int = None, end_time: int = None):
        return self.client.get_my_trades(symbol=symbol, startTime=start_time, endTime=end_time)

    def get_deposit_crypto(self, start_date: int, end_date: int):
        return self.client.get_deposit_history(startTime=start_date, endTime=end_date, limit=500)

    def get_withdraw_crypto(self, start_date: int, end_date: int):
        return self.client.get_withdraw_history(startTime=start_date, endTime=end_date, limit=500)

    def get_deposit_fiat(self, start_date: int, end_date: int):
        return self.client.get_fiat_deposit_withdraw_history(transactionType=0, startTime=start_date, endTime=end_date,
                                                             rows=500)

    def get_withdraw_fiat(self, start_date: int, end_date: int):
        return self.client.get_fiat_deposit_withdraw_history(transactionType=1, startTime=start_date, endTime=end_date,
                                                             rows=500)

    def get_purchase_cx_fiat(self, start_date: int, end_date: int):
        return self.client.get_fiat_payments_history(transactionType=0, startTime=start_date, endTime=end_date)

    def get_sell_cx_fiat(self, start_date: int, end_date: int):
        return self.client.get_fiat_payments_history(transactionType=1, startTime=start_date, endTime=end_date)

    # function of price
    def get_price_historical_kline(self, symbol: str, interval: str, start_date: datetime = None,
                                   end_date: datetime = None):
        if start_date and end_date:
            start_date = start_date.date()
            end_date = end_date.date()

            if end_date - start_date == timedelta(days=1):

                p_ticker = float(self.client.get_historical_klines(symbol=symbol, interval=interval,
                                                                   start_str=str(start_date),
                                                                   end_str=str(end_date))[0][4])
            else:
                p_ticker = [float(price[4]) for price in
                            self.client.get_historical_klines(symbol=symbol, interval=interval,
                                                              start_str=str(start_date), end_str=str(end_date))]

        elif start_date and not end_date:
            p_ticker = [float(price[4]) for price in self.client.get_historical_klines(symbol=symbol, interval=interval,
                                                                                       start_str=str(start_date))]
        elif not start_date and end_date:
            raise Exception("You can't just enter the end date")
        else:
            p_ticker = float(self.client.get_ticker(symbol=symbol)['lastPrice'])

        return p_ticker

    def get_prev_close_price(self, symbol: str):
        """
        Desc: Return Last Price of a given symbol
        Input:
            symbol:str
        Output:
            ticker.lastPrice
        """
        prev_close_price = self.client.get_ticker(symbol=symbol)['prevClosePrice']

        return float(prev_close_price)

    def get_actual_price(self, symbol: str) -> float:
        """
        Desc: Return Last Price of a given symbol
        Input:
            symbol:str
        Output:
            ticker.lastPrice
        """
        last_price = self.client.get_ticker(symbol=symbol)['lastPrice']
        return float(last_price)

    def get_symbol_24H(self, symbol: str = None) -> list:
        """
                Desc: Return a list of float type number and str
                 Input:
                                       symbol:str
                  Output:
                                       list of symbol and the 24 price percentage change

                 """
        return self.client.get_ticker(symbol=symbol)

    def get_all_symbol_24H(self):
        return self.client.get_ticker()

    def get_PriceChange24H(self, quote: str) -> DataFrame:
        Symbol = [(x['symbol'], x['priceChangePercent']) for x in self.get_symbol_24H()]
        df_change = DataFrame(data=Symbol, columns=['Symbol', 'priceChangePercent'])
        dist_c = df_change.where(df_change['Symbol'].str.endswith(quote.upper()))
        return dist_c

    def download_close_p(self, symbol: str, start_d) -> DataFrame:
        """
                Desc: Return df 'Data', 'Close P' for a given symbol from a starting date
                Input:
                    symbol: str,
                    start_d: starting date of investment -- self.get_starting_date_of_investment(coin=coin)

                :return  df_price:
                """
        # --Download Close Prices
        end_data = int(datetime.now().timestamp() * 1000)
        start_data = int(start_d.timestamp() * 1000)
        prices = self.client.get_historical_klines(start_str=start_data,
                                                   end_str=end_data,
                                                   symbol=symbol,
                                                   interval="1d")

        close_p = [(price[6], price[4]) for price in prices]

        df_price = DataFrame(data=close_p, columns=['Data', 'Close_P'])
        df_price['Data'] = pd.to_datetime(df_price['Data'], unit="ms")
        df_price.set_index('Data', inplace=True)

        return df_price

    # amount and coin holding
    def get_coin_snapshot(self, coin: str) -> float:
        """
              Desc: Return Amount detected from in SPOT Account
              Input:
                  coin:str
              Output:
                  Amount = Amount('free') + Amount('locked')


                #-- Amount('locked') are amounts of coin locked in an OPEN TRADE
              """
        coin_snapshot = 0
        account_asset_list = self.client.get_account_snapshot(type="SPOT")['snapshotVos'][0]['data']['balances']

        for asset in account_asset_list:
            if asset['asset'] == coin:
                coin_snapshot = float(asset['free']) + float(asset['locked'])

        return coin_snapshot

    def get_holding_asset(self) -> list:
        """
        Desc: Return list of Spot Holding Asset
        :return:
        """
        crypto = self.client.get_account_snapshot(type='SPOT')

        asset_tot = []
        for asset in crypto['snapshotVos'][0]['data']['balances']:
            if asset['free'] == '0' and asset['locked'] == '0':
                pass
            else:
                asset_tot.append(asset['asset'])

        return asset_tot

    def get_flexible_position(self, coin):
        floating_positions = self.client.get_lending_position()

        list_pos = [(lend['asset'], lend['dailyInterestRate'], lend['totalAmount'], lend['totalInterest'])
                    for lend in floating_positions if lend['asset'] == coin]
        df_flexible_st = DataFrame(data=list_pos, columns=('asset', 'dailyInterestRate', 'totalAmount',
                                                           'totalInterest'))
        if not df_flexible_st.empty:
            result = df_flexible_st[df_flexible_st['asset'] == coin]['totalAmount'].to_frame().iloc[-1].values
            tot_interest = df_flexible_st[df_flexible_st['asset'] == coin]['totalInterest'].to_frame().iloc[-1].values
        else:
            result = 0
            tot_interest = 0

        flexible = float(result) - float(tot_interest)
        return flexible

    # asset description
    def get_desc_asset_list(self):
        """
                Desc: Return list of Asset Description
                :return:
                """
        des_list = []
        res = self.client.get_all_coins_info()
        asset_list = self.get_holding_asset()
        for rest in res:
            for crypt in asset_list:
                if crypt == rest['coin']:
                    des_list = rest
        return des_list

    # get data from binance for tables
    def get_daily_div_history(self, asset=None, limit=None) -> list:
        """ Desc: Return a list of last LIMIT = limit dividend received of a given asset
           Input:
               asset=None : str , limit=None : str
           Ouput
               list: dividend
               """
        rows = self.client.get_asset_dividend_history(asset=asset, limit=limit)['rows']
        dividend_list = [stake for stake in rows]
        return dividend_list

    def get_fiat_deposit_history(self) -> list:
        """
                Desc: Return list of Fiat Deposit
                :return:
                """
        try:
            deposit_history = []
            deposit_list = self.client.get_fiat_deposit_withdraw_history(transactionType=0)
            if deposit_list and ['data'] in deposit_list:
                deposit_history = [deposit['data'] for deposit in deposit_list]

            return deposit_history

        except BinanceException as ex:
            print('Error:' + str(ex))

    def get_buy_sell_fiat_to_insert(self, transaction_type: int, start_time: int, end_time: int):

        if transaction_type == 0:
            tran_type = "B"
        else:
            tran_type = "S"

        buy_sell_fiat = self.client.get_fiat_payments_history(transactionType=transaction_type, startTime=start_time,
                                                              endTime=end_time)

        if buy_sell_fiat and "data" in buy_sell_fiat:
            fiats = [(self.id_user, buy_sell['orderNo'], float(buy_sell['sourceAmount']), buy_sell['fiatCurrency'],
                      float(buy_sell['obtainAmount']), buy_sell['cryptoCurrency'], float(buy_sell['totalFee']),
                      float(buy_sell['price']), buy_sell['status'],
                      datetime.fromtimestamp(buy_sell['createTime'] / 1000),
                      datetime.fromtimestamp(buy_sell['updateTime'] / 1000), tran_type)
                     for buy_sell in buy_sell_fiat['data']]

            return fiats

    def get_deposit_crypto_to_insert(self, start_time: int, end_time: int) -> list:
        deposit_crypto = self.client.get_deposit_history(startTime=start_time, endTime=end_time, limit=500)
        if deposit_crypto:
            deposit = [(self.id_user, float(dep['amount']), dep['coin'], dep['network'], dep['status'], dep['address'],
                        dep['addressTag'], dep['txId'], datetime.fromtimestamp(dep['insertTime'] / 1000),
                        dep['transferType'], dep['confirmTimes'], dep['unlockConfirm'],
                        dep['walletType']) for dep in deposit_crypto]
            return deposit

    def get_deposit_withdraw_fiat_to_insert(self, transaction_type: int, start_time: int, end_time: int):

        if transaction_type == 0:
            tran_type = "D"
        else:
            tran_type = "W"

        deposit_fiat = self.client.get_fiat_deposit_withdraw_history(transactionType=transaction_type,
                                                                     startTime=start_time,
                                                                     endTime=end_time, rows=500)

        if "data" in deposit_fiat and deposit_fiat['data']:
            deposits = [(self.id_user, dep['orderNo'], dep['fiatCurrency'],
                         float(dep['indicatedAmount']), float(dep['amount']), float(dep['totalFee']), dep['method'],
                         dep['status'], datetime.fromtimestamp(dep['createTime'] / 1000),
                         datetime.fromtimestamp(dep['updateTime'] / 1000), tran_type)
                        for dep in deposit_fiat['data']]

            return deposits

    def get_dividends_to_insert(self, asset: str = None, limit: int = None):
        dividends = self.client.get_asset_dividend_history(asset=asset, limit=limit)['rows']
        if dividends:
            all_dividends = [(self.id_user, str(dividend['id']), str(dividend['tranId']), dividend['asset'],
                              float(dividend['amount']), datetime.fromtimestamp(dividend['divTime'] / 1000),
                              dividend['enInfo']) for dividend in dividends]

            return all_dividends

    def get_orders_to_insert(self, symbol: str) -> list:
        orders = self.client.get_all_orders(symbol=symbol)
        if orders:
            order_symbol = [
                (self.id_user, order['symbol'], order['orderId'], order['clientOrderId'], float(order['price']),
                 float(order['origQty']), float(order['executedQty']), float(order['cummulativeQuoteQty']),
                 order['status'], order['timeInForce'], order['type'], order['side'],
                 float(order['stopPrice']), float(order['icebergQty']),
                 datetime.fromtimestamp(order['time'] / 1000),
                 datetime.fromtimestamp(order['updateTime'] / 1000),
                 order['isWorking'], float(order['origQuoteOrderQty'])) for order in orders]
            return order_symbol

    def get_crypto_to_insert(self) -> list:
        coins = self.client.get_all_coins_info()
        all_coin_info = []
        for coin in tqdm(coins):
            if len(coin['networkList']) > 0:
                all_coin_info.append((coin['coin'], coin['name'], coin['withdrawAllEnable'], coin['trading'],
                                      coin['networkList'][0]['withdrawEnable'], str(datetime.now()), '31129999'))

        #  all_coin_info = [(coin['coin'], coin['name'], coin['withdrawAllEnable'], coin['trading'],
        #                   coin['networkList'][0]['withdrawEnable']) for coin in tqdm(coins)]

        return all_coin_info

    def get_symbols_to_insert(self) -> list:
        symbols = self.client.get_exchange_info()['symbols']
        symbol_insert = []
        for symbol in tqdm(symbols):
            if len(symbol['symbol']) > 0:
                symbol_insert.append((symbol['symbol'], symbol['baseAsset'], symbol['quoteAsset'],
                                      str(datetime.now()), '31129999'))

        return symbol_insert

    def get_networks_to_insert(self):
        coins = self.client.get_all_coins_info()
        list_networks = []
        for coin in tqdm(coins, desc="Networks's table upsert"):
            dictionary = coin['networkList']
            for dic in range(len(dictionary)):
                for the_key, the_value in dictionary[dic].items():
                    if type(the_value) == str and the_value == "":
                        dictionary[dic][the_key] = the_value.replace("", "NULL")
                ins_net = (dictionary[dic]['network'], dictionary[dic]['coin'],
                           dictionary[dic]['withdrawIntegerMultiple'], dictionary[dic]['isDefault'],
                           dictionary[dic]['depositEnable'], dictionary[dic]['withdrawEnable'],
                           dictionary[dic]['depositDesc'], dictionary[dic]['withdrawDesc'], dictionary[dic]['name'],
                           dictionary[dic]['resetAddressStatus'], dictionary[dic]['addressRegex'],
                           dictionary[dic]['memoRegex'], dictionary[dic]['withdrawFee'], dictionary[dic]['withdrawMin'],
                           dictionary[dic]['withdrawMax'], dictionary[dic]['minConfirm'],
                           dictionary[dic]['unLockConfirm'], dictionary[dic]['sameAddress'],
                           str(datetime.today()),
                           '31129999')

                list_networks.append(ins_net)
        return list_networks

    def get_trades_to_insert(self, symbol: str) -> list:
        trades = self.client.get_my_trades(symbol=symbol)
        trade_symbol = [(self.id_user, trade['symbol'], trade['id'], trade['orderId'], float(trade['price']),
                         float(trade['qty']),
                         float(trade['quoteQty']), float(trade['commission']), trade['commissionAsset'],
                         datetime.fromtimestamp(trade['time'] / 1000), trade['isBuyer'], trade['isMaker'],
                         trade['isBestMatch']) for trade in trades]
        return trade_symbol

    def get_withdraw_crypto_to_insert(self, start_time: int, end_time: int) -> list:
        withdraw_crypto = self.client.get_withdraw_history(startTime=start_time, endTime=end_time, limit=500)
        if withdraw_crypto:
            withdraws = [(self.id_user, withdraw["id"], float(withdraw["amount"]), withdraw['transactionFee'],
                          withdraw['coin'],
                          withdraw['status'], withdraw['address'], withdraw['txId'],
                          datetime.strptime(withdraw["applyTime"], '%Y-%m-%d %H:%M:%S'), withdraw['network'],
                          withdraw['transferType'], withdraw['info'], withdraw['confirmNo'], withdraw['walletType'])
                         for withdraw in withdraw_crypto]
            return withdraws

    def get_exchange_info(self):
        return self.client.get_exchange_info()



