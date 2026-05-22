from datetime import timedelta

import numpy as np
import pandas as pd
from pandas import DataFrame
import DateFunction as dT
from BinanceService import BinanceService
from CommonTable import CommonTable
from CreateTables import engine_fin

pd.set_option('display.max_columns', None)


def get_df_date(start_date):
    index_date = pd.date_range(start=start_date, end=dT.datetime_to_date(dT.now_date()), freq="D")
    return pd.DataFrame(data=[1] * len(index_date), index=index_date, columns=["Val"])


def min_date(df_list: list):
    return min([min(df.index) for df in df_list if not df.empty])


def wags(price, weight):
    return sum(price * weight) / sum(weight)


def get_weights(qty, price, tot):
    return (qty * price) / tot


def get_remapped_rename_trx(df_buy_sell, coin):
    df_buy_sell = df_buy_sell.rename(columns={"updatetime": "time", "fiatcurrency": "symbol",
                                              "buy_sell": "side", "obtainamount": "qty"})
    df_buy_sell["side"] = df_buy_sell["side"].map({"B": "BUY", "S": "SELL"})
    df_buy_sell["symbol"] = coin + df_buy_sell["symbol"]
    return df_buy_sell


class StatisticsCoin:

    def __init__(self, id_user: int, api_key: str, api_secret: str):

        self.comm = CommonTable()
        self.df_trade = pd.read_sql(sql=f"select * from trades where id_user={id_user}", con=engine_fin)
        engine_fin.dispose()
        self.df_dep = pd.read_sql(sql=f"select * from deposits_crypto where id_user={id_user}",
                                  con=engine_fin)
        engine_fin.dispose()
        self.df_order = pd.read_sql(sql=f"select * from orders where id_user={id_user}",
                                    con=engine_fin)
        engine_fin.dispose()
        self.df_with = pd.read_sql(sql=f"select * from withdraw_crypto where id_user={id_user}",
                                   con=engine_fin)
        engine_fin.dispose()
        self.df_div = pd.read_sql(sql=f"select * from dividends where id_user={id_user}",
                                  con=engine_fin)
        engine_fin.dispose()
        self.df_buy_sell = pd.read_sql(sql=f"select * from buy_sell_fiat where id_user={id_user}",
                                       con=engine_fin)
        engine_fin.dispose()

        self.df_symbol = pd.read_sql_table(table_name="symbols", con=engine_fin)
        engine_fin.dispose()

        self.df_crypto = pd.read_sql_table(table_name="crypto", con=engine_fin)
        engine_fin.dispose()

        self.bin_ser = BinanceService(api_key=api_key, api_secret=api_secret)

    def get_coin_name(self, coin: str):
        return self.df_crypto.loc[self.df_crypto['coin'] == coin, 'name'].values[0]

    def get_symbol_x_coin(self, coin: str):
        return list(self.df_symbol.loc[self.df_symbol['base_asset'] == coin, 'symbol'].values)

    def get_historical_amount(self, coin: str):
        """ Desc: Return df of Historic Amount invested in a given coin
                Input:
                    coin:str
                Ouput
                    df : ['Dividend']['Trade']['Deposit']['Withdraw']['Sold']['Purchase'][Amount]
                    """

        self.df_trade['time'] = pd.to_datetime(self.df_trade['time']).dt.date
        self.df_trade = self.df_trade.loc[self.df_trade['symbol'].str.startswith(coin),
        ['time', 'qty']].set_index('time') \
            .sort_index().rename(index={'time': 'date'})

        self.df_dep['inserttime'] = pd.to_datetime(self.df_dep['inserttime']).dt.date
        self.df_dep = self.df_dep.loc[self.df_dep['coin'] == coin, ['inserttime', 'amount']].set_index('inserttime') \
            .sort_index().rename(columns={'amount': 'amount_dep'}, index={'inserttime': 'date'})

        self.df_with['applytime'] = pd.to_datetime(self.df_with['applytime']).dt.date
        self.df_with = self.df_with.loc[self.df_with['coin'] == coin, ['applytime', 'amount']].set_index('applytime') \
            .sort_index().rename(columns={'amount': 'amount_with'}, index={'applytime': 'date'})

        self.df_div['div_time'] = pd.to_datetime(self.df_div['div_time']).dt.date
        self.df_div = self.df_div.loc[self.df_div['asset'] == coin, ['div_time', 'amount']].set_index('div_time') \
            .sort_index().rename(columns={'amount': 'amount_div'}, index={'div_time': 'date'})

        self.df_buy_sell['updatetime'] = pd.to_datetime(self.df_buy_sell['updatetime']).dt.date
        self.df_buy_sell['obtainamount'] = np.where(self.df_buy_sell['buy_sell'] == "B",
                                                    self.df_buy_sell['obtainamount'],
                                                    - self.df_buy_sell['obtainamount'])
        self.df_buy_sell = self.df_buy_sell.loc[(self.df_buy_sell['cryptocurrency'] == coin) &
                                                (self.df_buy_sell['status'] == "Completed"),
        ['updatetime', 'obtainamount']].set_index('updatetime').sort_index() \
            .rename(index={'updatetime': 'date'})

        if self.df_trade.empty and self.df_dep.empty and self.df_with.empty and self.df_div.empty and \
                self.df_buy_sell.empty:
            return print("There are no operations for this coin")
        else:
            mini_date = min_date([self.df_trade, self.df_dep, self.df_with, self.df_div, self.df_buy_sell])
            df_date = get_df_date(start_date=mini_date)
            result = df_date.join(self.df_div).join(self.df_trade).join(self.df_dep).join(self.df_with). \
                join(self.df_buy_sell).fillna(0)

            del result['Val']
            result['Amount'] = (result['amount_div'] + result['qty'] +
                                result['amount_dep'] + result['amount_with'] +
                                result['obtainamount']).cumsum()

            return result

    def get_PL_x_traded_symbols(self, coin: str):

        df_tot = pd.merge(self.df_trade.loc[self.df_trade['symbol'].str.startswith(coin),
        ['symbol', 'id_order', 'price', 'time', 'commission_asset', 'qty']],
                          self.df_order.loc[self.df_order['symbol'].str.startswith(coin),
                          ['side', 'symbol', 'id_order_bin']], how="inner",
                          left_on=['symbol', 'id_order'], right_on=['symbol', 'id_order_bin'])

        if not df_tot.empty:
            tot = df_tot.groupby(['symbol', 'side']).agg({'qty': np.sum, 'price': np.mean}).reset_index()
            tot['change'] = tot.groupby('symbol')['price'].pct_change().fillna(0)

            tot['deposit'] = tot['qty'] * tot['price']
            # tot['sold_dv'] = tot['price'] * (1 + tot['change']) * tot['qty']
            tot['tot_PL'] = tot['change'] * tot['qty'] * tot['price']
            tot['tot_Pl_perc'] = tot['tot_PL'] / tot['deposit']
            tot['source'] = 'trd'
            tot.set_index('symbol', inplace=True)

            return tot

    def get_PL_x_trx_symbols(self, coin: str):
        df = self.df_buy_sell.loc[(self.df_buy_sell['cryptocurrency'] == coin) &
                                  (self.df_buy_sell['status'] == 'Completed'),
        ['fiatcurrency', 'buy_sell', 'obtainamount', 'price']]

        if not df.empty:
            tot = df.groupby(['fiatcurrency', 'buy_sell']).agg({'obtainamount': np.sum, 'price': np.mean}).reset_index()
            tot['change'] = tot.groupby('fiatcurrency')['price'].pct_change().fillna(0)

            tot['deposit'] = tot['obtainamount'] * tot['price']
            tot['tot_PL'] = tot['change'] * tot['obtainamount'] * tot['price']
            tot['tot_Pl_perc'] = tot['tot_PL'] / tot['deposit']
            tot = tot.rename(columns={"fiatcurrency": "symbol", "buy_sell": "side",
                                      "obtainamount": "qty"})
            tot['symbol'] = coin + tot['symbol']
            tot["side"] = tot["side"].map({"B": "BUY", "S": "SELL"})
            tot['source'] = 'trx'
            tot.set_index('symbol', inplace=True)

            return tot

    def get_Realized_PL_symbol_grouped(self, coin: str):

        pl_trade = self.get_PL_x_traded_symbols(coin=coin)
        pl_trx = self.get_PL_x_trx_symbols(coin=coin)

        if pl_trade.empty and pl_trx.empty:
            return print("There aren't trades and transaction")
        else:
            return pd.concat([pl_trade, pl_trx])

    def get_df_Weights_from_trade(self, coin: str, quote: str):  # rivedere
        df_tot = pd.merge(self.df_trade.loc[self.df_trade['symbol'].str.startswith(coin),
        ['symbol', 'id_order', 'price', 'time', 'commission_asset', 'qty']],
                          self.df_order.loc[self.df_order['symbol'].str.startswith(coin),
                          ['side', 'symbol', 'id_order_bin']], how="inner",
                          left_on=['symbol', 'id_order'], right_on=['symbol', 'id_order_bin'])

        df_tot['coin'] = coin
        df_tot['quote'] = df_tot['symbol'].str.split(coin).str[-1]
        df_tot['symbol_price'] = np.where((df_tot['quote'] != "USDT") & ((df_tot['symbol'].str.startswith('EUR')) |
                                                                         (df_tot['symbol'].str.startswith('USDT'))),
                                          df_tot['quote'] + df_tot['coin'], df_tot['symbol'])

        df_tot['conv_price'] = df_tot.apply(lambda x: self.bin_ser.get_price_historical_kline(
            symbol=x['symbol_price'], interval="1d", start_date=x['time'] - timedelta(days=1), end_date=x['time']))

        df_tot['new_qty'] = np.where((df_tot['quote'] != "USDT") & ((df_tot['symbol'].str.startswith('EUR')) |
                                                                    (df_tot['symbol'].str.startswith('USDT'))),
                                     df_tot['qty'] / df_tot['conv_price'], df_tot['qty'] * df_tot['conv_price'])
        print(df_tot[['symbol_price', 'conv_price', 'qty', 'new_qty']])
        df_sum_g = df_tot[['symbol_price', 'new_qty']].groupby('symbol_price').sum()
        print(df_sum_g)

    def get_valid_conversion_Price(self, p_coin_in_quote_0: float, quote_0: str, quote_1: str, time=None) -> float:
        ticker = self.comm.get_valid_ticker(coin=quote_0, quote=quote_1)

        if time is None:
            p_ticker = self.bin_ser.get_actual_price(symbol=ticker)
        else:
            end_date = time + timedelta(days=1)
            p_ticker = self.bin_ser.get_price_historical_kline(symbol=ticker, interval="1d", start_date=time,
                                                               end_date=end_date)

        l_quote_0 = len(quote_0)
        price_in_quote_1 = 0.0

        if ticker[-l_quote_0:] == quote_0:
            price_in_quote_1 = p_coin_in_quote_0 / p_ticker
        elif ticker[0:l_quote_0] == quote_0:
            price_in_quote_1 = p_coin_in_quote_0 * p_ticker
        else:
            print("we")

        return price_in_quote_1

    def get_concat_trd_trx(self, coin: str):
        df_trade_tot = pd.merge(self.df_trade.loc[self.df_trade['symbol'].str.startswith(coin),
        ['symbol', 'id_order', 'price', 'time', 'commission_asset', 'qty']],
                                self.df_order.loc[self.df_order['symbol'].str.startswith(coin),
                                ['side', 'symbol', 'id_order_bin']], how="inner",
                                left_on=['symbol', 'id_order'], right_on=['symbol', 'id_order_bin'])

        df_trx = self.df_buy_sell.loc[(self.df_buy_sell['cryptocurrency'] == coin) &
                                      (self.df_buy_sell['status'] == 'Completed'), ['updatetime', 'fiatcurrency',
                                                                                    'buy_sell', 'obtainamount',
                                                                                    'price']]
        df_trade_tot['source'] = 'trd'
        df_trade_tot['qty'] = np.where(df_trade_tot['side'] == "BUY", df_trade_tot['qty'], -df_trade_tot['qty'])
        df_trx['obtainamount'] = np.where(df_trx['buy_sell'] == "B", df_trx['obtainamount'], - df_trx['obtainamount'])

        df_trx = df_trx.rename(columns={"updatetime": "time", "fiatcurrency": "symbol", "buy_sell": "side",
                                        "obtainamount": "qty"})
        df_trx["side"] = df_trx["side"].map({"B": "BUY", "S": "SELL"})
        df_trx['symbol'] = coin + df_trx['symbol']
        df_trx['source'] = 'trx'
        result = pd.concat([df_trx, df_trade_tot[['time', 'symbol', 'side', 'qty', 'price', 'source']]]) \
            .reset_index().drop(["index"], axis=1).sort_values('time')

        return result

    def get_converted_df(self, coin: str, quote: str, result: DataFrame):
        result['conversion_price'] = np.where(result.symbol.str.replace(coin, "") != quote, result.apply(
            lambda x: self.get_valid_conversion_Price(p_coin_in_quote_0=x['price'],
                                                      quote_0=x['symbol'].replace(coin, ""),
                                                      quote_1=quote, time=x['time']), axis=1), result['price'])
        return result

    def get_conversion_df_trd_trx(self, coin: str, quote: str):
        result = self.get_concat_trd_trx(coin=coin)
        result_fin = self.get_converted_df(coin=coin, quote=quote, result=result)

        return result_fin

    def get_df_weights_from_trx(self, coin: str, quote: str):

        df_trx = self.df_buy_sell.loc[(self.df_buy_sell['cryptocurrency'] == coin) &
                                      (self.df_buy_sell['status'] == 'Completed'), ['updatetime', 'fiatcurrency',
                                                                                    'buy_sell', 'obtainamount',
                                                                                    'price']]
        print(df_trx)
        if not df_trx.empty:
            df_trx = get_remapped_rename_trx(df_buy_sell=df_trx, coin=coin)
            df_conv = self.get_converted_df(coin=coin, quote=quote, result=df_trx)
            df_conv['qty'] = df_conv['qty'].abs()
            df_conv['weight'] = df_conv.apply(lambda x: get_weights(qty=x['qty'], price=x['conversion_price'],
                                                                    tot=(df_conv['qty']
                                                                         * df_conv['conversion_price']).sum()), axis=1)

            return df_conv[['symbol', 'side', 'qty', 'conversion_price', 'weight']]
        else:
            return DataFrame(columns=['symbol', 'side', 'qty', 'conversion_price', 'weight'])

    def get_df_weights_from_trd(self, coin: str, quote: str):
        df_trade_tot = pd.merge(self.df_trade.loc[self.df_trade['symbol'].str.startswith(coin),
        ['symbol', 'id_order', 'price', 'time', 'commission_asset', 'qty']],
                                self.df_order.loc[self.df_order['symbol'].str.startswith(coin),
                                ['side', 'symbol', 'id_order_bin']], how="inner",
                                left_on=['symbol', 'id_order'], right_on=['symbol', 'id_order_bin'])

        if not df_trade_tot.empty:
            df_conv = self.get_converted_df(coin=coin, quote=quote, result=df_trade_tot)
            df_conv['qty'] = df_conv['qty'].abs()
            df_conv['weight'] = df_conv.apply(lambda x: get_weights(qty=x['qty'], price=x['conversion_price'],
                                                                    tot=(df_conv['qty']
                                                                         * df_conv['conversion_price']).sum()), axis=1)

            return df_conv[['symbol', 'side', 'qty', 'conversion_price', 'weight']]
        else:
            return DataFrame(columns=['symbol', 'side', 'qty', 'conversion_price', 'weight'])

    def get_df_weights_from_trd_trx(self, coin: str, quote: str):
        df_conv = self.get_conversion_df_trd_trx(coin=coin, quote=quote)
        df_conv['qty'] = df_conv['qty'].abs()
        df_conv['weight'] = df_conv.apply(lambda x: get_weights(qty=x['qty'], price=x['conversion_price'],
                                                                tot=(df_conv['qty']
                                                                     * df_conv['conversion_price']).sum()), axis=1)
        return df_conv[['symbol', 'side', 'qty', 'conversion_price', 'weight']]

    def get_1day_EquityV_Change(self, coin: str, quote: str):

        symbol = coin + quote
        last_two_days = self.get_historical_amount(coin=coin)['Amount'].reset_index().tail(2)
        last_two_days['price'] = [self.bin_ser.get_prev_close_price(symbol=symbol),
                                  self.bin_ser.get_actual_price(symbol=symbol)]

        last_two_days['mkt_val'] = last_two_days['Amount'] * last_two_days['price']
        last_two_days['change'] = last_two_days['mkt_val'].diff()
        last_two_days['change_p'] = last_two_days['change'] / last_two_days['mkt_val'].shift(1) * 100

        return last_two_days[['change', 'change_p']].tail(1).to_dict(orient="records")

    def get_FixedStaking_Amount(self, coin: str) -> float:
        tot_amount = self.get_historical_amount(coin=coin)['Amount'].iloc[-1]

        acc_snap = self.bin_ser.get_coin_snapshot(coin=coin)
        flex = self.bin_ser.get_flexible_position(coin=coin)

        return float(tot_amount - acc_snap - flex)

    def get_df_trd_trx_x_coin(self, coin: str):
        df_trade_tot = pd.merge(self.df_trade.loc[self.df_trade['symbol'].str.startswith(coin),
        ['symbol', 'id_order', 'price', 'time', 'commission_asset', 'qty']],
                                self.df_order.loc[self.df_order['symbol'].str.startswith(coin),
                                ['side', 'symbol', 'id_order_bin']], how="inner",
                                left_on=['symbol', 'id_order'], right_on=['symbol', 'id_order_bin'])

        df_trx = self.df_buy_sell.loc[(self.df_buy_sell['cryptocurrency'] == coin) &
                                      (self.df_buy_sell['status'] == 'Completed'), ['updatetime', 'fiatcurrency',
                                                                                    'buy_sell', 'obtainamount',
                                                                                    'price']]
        df_trade_tot['source'] = 'trd'
        df_trade_tot['qty'] = np.where(df_trade_tot['side'] == "BUY", df_trade_tot['qty'], -df_trade_tot['qty'])
        df_trx['obtainamount'] = np.where(df_trx['buy_sell'] == "B", df_trx['obtainamount'], - df_trx['obtainamount'])

        df_trx = df_trx.rename(columns={"updatetime": "time", "fiatcurrency": "symbol", "buy_sell": "side",
                                        "obtainamount": "qty"})
        df_trx["side"] = df_trx["side"].map({"B": "BUY", "S": "SELL"})
        df_trx['symbol'] = coin + df_trx['symbol']
        df_trx['source'] = 'trx'
        result = pd.concat([df_trx, df_trade_tot[['time', 'symbol', 'side', 'qty', 'price', 'source']]]).reset_index(). \
            drop(["index"], axis=1).sort_values('time')

        df_trx_trd = result[['symbol', 'side', 'qty']]

        symbols = list(set(df_trx_trd['Symbol']))
        data_list = list()
        for i in symbols:
            for j in ["BUY", "SELL"]:
                data = [i, j, 0]
                data_list.append(data)

        df_a = pd.DataFrame(data=data_list, columns=['Symbol', 'side', 'Qty'])

        new_frame = [df_trx_trd, df_a]
        res = pd.concat(new_frame).reset_index().drop("index", axis=1)
        return res

    def get_coin_meanP_amount_trade(self, coin: str, quote: str) -> dict:  # vedere super_init
        df_trade_tot = self.get_df_weights_from_trd(coin=coin, quote=quote)

        if not df_trade_tot.empty:
            df_trade_tot['cumsum_qty'] = df_trade_tot['qty'].cumsum()
            mean_price = (df_trade_tot['conversion_price'] * df_trade_tot['weight']).sum()
            return {'Symbol': coin + quote, 'WAvg': mean_price, 'Amount': df_trade_tot['cumsum_qty'].iloc[-1]}
        else:
            return {'Symbol': coin + quote, 'WAvg': 0, 'Amount': 0}

    def get_coin_meanP_amount_trx(self, coin: str, quote: str) -> dict:  # vedere super_init
        df_trade_tot = self.get_df_weights_from_trx(coin=coin, quote=quote)

        if not df_trade_tot.empty:
            df_trade_tot['cumsum_qty'] = df_trade_tot['qty'].cumsum()
            mean_price = (df_trade_tot['conversion_price'] * df_trade_tot['weight']).sum()
            return {'Symbol': coin + quote, 'WAvg': mean_price, 'Amount': df_trade_tot['cumsum_qty'].iloc[-1]}
        else:
            return {'Symbol': coin + quote, 'WAvg': 0, 'Amount': 0}

    def get_coin_meanP_amount_trd_trx(self, coin: str, quote: str) -> dict:
        df_trade_tot = self.get_df_weights_from_trd_trx(coin=coin, quote=quote)

        if not df_trade_tot.empty:
            df_trade_tot['cumsum_qty'] = df_trade_tot['qty'].cumsum()
            mean_price = (df_trade_tot['conversion_price'] * df_trade_tot['weight']).sum()
            return {'Symbol': coin + quote, 'WAvg': mean_price, 'Amount': df_trade_tot['cumsum_qty'].iloc[-1]}
        else:
            return {'Symbol': coin + quote, 'WAvg': 0, 'Amount': 0}

    def get_Mkt_Attribute(self, coin: str, quote: str):

        df_trade_tot = self.get_df_weights_from_trd_trx(coin=coin, quote=quote)
        df_trade_tot['qty'] = np.where(df_trade_tot['side'] == 'BUY', df_trade_tot['qty'],
                                       - df_trade_tot['qty'])
        df_trade_tot['weight'] = np.where(df_trade_tot['side'] == 'BUY', df_trade_tot['weight'],
                                          - df_trade_tot['weight'])
        actual_price = self.bin_ser.get_actual_price(symbol=coin + quote)

        df_trade_tot['cumsum_qty'] = df_trade_tot['qty'].cumsum()
        Y = (actual_price * df_trade_tot['cumsum_qty'].iloc[-1])  # Float Actual MKT V

        sum_qty = df_trade_tot['cumsum_qty'].iloc[-1]
        mean_price = (df_trade_tot['conversion_price'] * df_trade_tot['weight']).sum()
        y_0 = (df_trade_tot['qty'] * df_trade_tot['conversion_price']).sum()
        PNL = Y - y_0  # Mkt Profit And Loss
        PNL_perc = PNL / y_0  # Mkt Profit And Loss Perc

        dict_return = {'Symbol': coin + quote, 'Quote': y_0,
                       'Amount': sum_qty, 'WAvg': mean_price,
                       'MktP': actual_price, 'Mkt Value': Y,
                       'PNL': PNL, 'PNL_perc': PNL_perc}
        return dict_return
