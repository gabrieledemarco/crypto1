from . import DateFunction as dT


def get_tuple_crypto(coin) -> tuple:
    all_coin_info = (coin['coin'], coin['name'], coin['withdrawAllEnable'], coin['trading'],
                     coin['networkList'][0]['withdrawEnable'])

    return all_coin_info


def get_tuple__symbols(symbol) -> tuple:
    symbol_insert = (symbol['symbol'], symbol['baseAsset'], symbol['quoteAsset'])
    return symbol_insert


def get_tuple_dividends(id_user, dividend) -> tuple:
    print(dividend)
    all_dividends = (id_user,
                     str(dividend['id']),
                     str(dividend['tranId']),
                     dividend['asset'],
                     float(dividend['amount']),
                     dT.milliseconds_to_datetime(input_data=dividend['divTime']),
                     dividend['enInfo'])

    return all_dividends


def get_tuple_orders(id_user, order) -> tuple:
    order_symbol = (id_user, order['symbol'], order['orderId'], order['clientOrderId'], float(order['price']),
                    float(order['origQty']), float(order['executedQty']), float(order['cummulativeQuoteQty']),
                    order['status'], order['timeInForce'], order['type'], order['side'],
                    float(order['stopPrice']), float(order['icebergQty']),
                    dT.milliseconds_to_datetime(input_data=order['time']),
                    dT.milliseconds_to_datetime(input_data=order['updateTime']),
                    order['isWorking'], float(order['origQuoteOrderQty']))
    return order_symbol


def get_tuple_trades(id_user, trade) -> tuple:
    trade_symbol = (id_user, trade['symbol'], trade['id'], trade['orderId'], float(trade['price']),
                    float(trade['qty']),
                    float(trade['quoteQty']), float(trade['commission']), trade['commissionAsset'],
                    dT.milliseconds_to_datetime(input_data=trade['time']), trade['isBuyer'], trade['isMaker'],
                    trade['isBestMatch'])
    return trade_symbol


def get_tuple_withdraw_crypto(id_user, withdraw) -> tuple:
    withdraws = (id_user, withdraw["id"], float(withdraw["amount"]), withdraw['transactionFee'],
                 withdraw['coin'],
                 withdraw['status'], withdraw['address'], withdraw['txId'],
                 dT.string_to_datetime(input_data=withdraw["applyTime"], format_date='%Y-%m-%d %H:%M:%S'),
                 withdraw['network'], withdraw['transferType'], withdraw['info'], withdraw['confirmNo'],
                 withdraw['walletType'])
    return withdraws


def get_tuple_buy_sell_fiat(id_user, buy_sell, tran_type) -> tuple:
    fiats = (id_user, buy_sell['orderNo'], float(buy_sell['sourceAmount']), buy_sell['fiatCurrency'],
             float(buy_sell['obtainAmount']), buy_sell['cryptoCurrency'], float(buy_sell['totalFee']),
             float(buy_sell['price']), buy_sell['status'],
             dT.milliseconds_to_datetime(input_data=buy_sell['createTime']),
             dT.milliseconds_to_datetime(input_data=buy_sell['updateTime']), tran_type)

    return fiats


def get_tuple_deposit_crypto(id_user, dep) -> tuple:
    deposit = (id_user, float(dep['amount']), dep['coin'], dep['network'], dep['status'], dep['address'],
               dep['addressTag'], dep['txId'], dT.milliseconds_to_datetime(input_data=dep['insertTime']),
               dep['transferType'], dep['confirmTimes'], dep['unlockConfirm'],
               dep['walletType'])
    return deposit


def get_tuple_deposit_withdraw_fiat(id_user, dep, tran_type) -> tuple:
    deposits = (id_user, dep['orderNo'], dep['fiatCurrency'],
                float(dep['indicatedAmount']), float(dep['amount']), float(dep['totalFee']), dep['method'],
                dep['status'], dT.milliseconds_to_datetime(input_data=dep['createTime']),
                dT.milliseconds_to_datetime(input_data=dep['updateTime']), tran_type)

    return deposits
