from datetime import datetime

from .config_postgres_alchemy import postgres_sql
from sqlalchemy import PrimaryKeyConstraint
# from sqlalchemy_utils import database_exists, create_database
# from config_postgres_alchemy import postgres_sql as settings
from sqlalchemy import Table, Column, Integer, String, Float, TIMESTAMP, MetaData, Boolean, Identity, BigInteger
from sqlalchemy import create_engine

url = f"postgresql://{postgres_sql['user']}:{postgres_sql['password']}@{postgres_sql['host']}:{postgres_sql['port']}" \
      f"/{postgres_sql['db']}"

engine_fin = create_engine(url, pool_size=50, echo=False)

meta = MetaData()
start_time = datetime.now()

# -- Binance API's Tables
crypto = Table('crypto', meta,
               Column('id_crypto', Integer, Identity("always"), nullable=False, primary_key=True),
               Column('coin', String(10), nullable=False),
               Column('name', String(50), nullable=False),
               Column('binance_withdraw_enable', Boolean, nullable=False),
               Column('trading', Boolean, nullable=False),
               Column('withdraw_enable', Boolean, nullable=False),
               Column('x_effective_from', String(50), nullable=False),
               Column('x_effective_to', String(50), nullable=False),
               PrimaryKeyConstraint('id_crypto', name='crypto_pk'))

symbols = Table('symbols', meta,
                Column('id_symbol', Integer, Identity("always"), nullable=False, primary_key=True),
                Column('symbol', String(20), nullable=False),
                Column('base_asset', String(20), nullable=False),
                Column('quote_asset', String(20), nullable=False),
                Column('x_effective_from', String(50), nullable=False),
                Column('x_effective_to', String(50), nullable=False),
                PrimaryKeyConstraint('id_symbol', name='symbols_pk'))

networks = Table('networks', meta,
                 Column('id_network', Integer, Identity("always"), nullable=False, primary_key=True),
                 Column('network', String(20), nullable=False),
                 Column('coin', String(10), nullable=False),
                 Column('withdraw_integer_multiple', String(200), nullable=False),
                 Column('is_default', Boolean),
                 Column('deposit_enable', Boolean),
                 Column('withdraw_enable', Boolean, nullable=False),
                 Column('deposit_desc', String(200)),
                 Column('withdraw_desc', String(200), nullable=False),
                 Column('name', String(200), nullable=False),
                 Column('reset_address_status', Boolean, nullable=False),
                 Column('address_regex', String(200), nullable=False),
                 Column('memo_regex', String(200)),
                 Column('withdraw_fee', String(200), nullable=False),
                 Column('withdraw_min', String(200), nullable=False),
                 Column('withdraw_max', String(200), nullable=False),
                 Column('min_confirm', Integer, nullable=False),
                 Column('un_lock_confirm', Integer, nullable=False),
                 Column('same_address', Boolean, nullable=False),
                 Column('x_effective_from', String(50), nullable=False),
                 Column('x_effective_to', String(50), nullable=False),
                 PrimaryKeyConstraint('id_network', name='network_list_pk'))

# -- Users's Tables
user = Table('users', meta,
             Column('id_user', Integer, Identity("always"), nullable=False, primary_key=True),
             Column('api_key', String(100), nullable=False),
             Column('api_secret', String(100), nullable=False),
             Column('nickname', String(10), nullable=False),
             Column('password', String(10), nullable=False),
             Column('x_effective_from', String(50), nullable=False),
             Column('x_effective_to', String(50), nullable=False),
             PrimaryKeyConstraint('id_user', name='id_user_pk'))

dividends = Table('dividends', meta,
                  Column('id_div', Integer, Identity("always"), nullable=False, primary_key=True),
                  Column('id_user', Integer, nullable=False),
                  Column('id', String(50), nullable=False),
                  Column('tran_id', String(50), nullable=False),
                  Column('asset', String(10), nullable=False),
                  Column('amount', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
                  Column('div_time', TIMESTAMP, nullable=False),
                  Column('en_info', String(50), nullable=False),
                  PrimaryKeyConstraint('id_div', name='dividendi_pk'))

orders = Table('orders', meta,
               Column('id_order', Integer, Identity("always"), nullable=False, primary_key=True),
               Column('id_user', Integer, nullable=False),
               Column('symbol', String(15), nullable=False),
               Column('id_order_bin', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('client_order_id', String(50), nullable=False),
               Column('price', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('orig_qty', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('executed_qty', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('cumulative_quote_qty', Float(precision=8), nullable=False),
               Column('status', String(50), nullable=False),
               Column('time_in_force', String(5), nullable=False),
               Column('type_order', String(30), nullable=False),
               Column('side', String(5), nullable=False),
               Column('stop_price', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('iceberg_qty', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('time', TIMESTAMP, nullable=False),
               Column('update_time', TIMESTAMP, nullable=False),
               Column('is_working', Boolean, nullable=False),
               Column('orig_quote_order_qty', Float(precision=8), nullable=False),
               PrimaryKeyConstraint('id_order', name='order_pk'))

trades = Table('trades', meta,
               Column('id_trade', BigInteger, Identity("always"), nullable=False, primary_key=True),
               Column('id_user', Integer, nullable=False),
               Column('symbol', String(15), nullable=False),
               Column('id', BigInteger, nullable=False),
               Column('id_order', BigInteger, nullable=False),
               Column('price', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('qty', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('quote_qty', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('commission', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('commission_asset', String(5), nullable=False),
               Column('time', TIMESTAMP, nullable=False),
               Column('is_buyer', Boolean, nullable=False),
               Column('is_maker', Boolean, nullable=False),
               Column('is_best_match', Boolean, nullable=False),
               PrimaryKeyConstraint('id_trade', name='trade_pk'))

buy_sell_fiat = Table('buy_sell_fiat', meta,
                      Column('id_transaction_f', BigInteger, Identity("always"), nullable=False, primary_key=True),
                      Column('id_user', Integer, nullable=False),
                      Column('orderno', String(40), nullable=False),
                      Column('sourceamount', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
                      Column('fiatcurrency', String(10), nullable=False),
                      Column('obtainamount', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
                      Column('cryptocurrency', String(20), nullable=False),
                      Column('totalfee', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
                      Column('price', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
                      Column('status', String(20), nullable=False),
                      Column('createtime', TIMESTAMP, nullable=False),
                      Column('updatetime', TIMESTAMP, nullable=False),
                      Column('buy_sell', String(1), nullable=False),
                      PrimaryKeyConstraint('id_transaction_f', name='buy_sell_pk'))

deposit_withdraw_fiat = Table('deposit_withdraw_fiat', meta,
                              Column('id_transaction', BigInteger, Identity("always"), nullable=False,
                                     primary_key=True),
                              Column('id_user', Integer, nullable=False),
                              Column('orderno', String(40), nullable=False),
                              Column('fiatcurrency', String(10), nullable=False),
                              Column('indicatedamount', Float(None, decimal_return_scale=7, asdecimal=True),
                                     nullable=False),
                              Column('amount', Float(None, decimal_return_scale=7, asdecimal=True)),
                              Column('totalfee', Float(None, decimal_return_scale=7, asdecimal=True),
                                     nullable=False),
                              Column('method', String(10), nullable=False),
                              Column('status', String(30), nullable=False),
                              Column('createtime', TIMESTAMP, nullable=False),
                              Column('updatetime', TIMESTAMP, nullable=False),
                              Column('deposit_withdraw', String(1), nullable=False),
                              PrimaryKeyConstraint('id_transaction', name='deposit_fiat_pk'))

deposits_crypto = Table('deposits_crypto', meta,
                        Column('id_deposit_c', BigInteger, Identity("always"), nullable=False,
                               primary_key=True),
                        Column('id_user', Integer, nullable=False),
                        Column('amount', Float(None, decimal_return_scale=7, asdecimal=True)),
                        Column('coin', String(20), nullable=False),
                        Column('network', String(20), nullable=False),
                        Column('status', Integer, nullable=False),
                        Column('address', String(100), nullable=False),
                        Column('addresstag', String(10), nullable=False),
                        Column('txid', String(100), nullable=False),
                        Column('inserttime', TIMESTAMP, nullable=False),
                        Column('transfertype', Integer, nullable=False),
                        Column('confirmtimes', String(6), nullable=False),
                        Column('unlockconfirm', Integer, nullable=False),
                        Column('wallettype', Integer, nullable=False),
                        PrimaryKeyConstraint('id_deposit_c', name='deposit_pk'))

withdraw_crypto = Table('withdraw_crypto', meta,
                        Column('id_withdraw_c', BigInteger, Identity("always"), nullable=False,
                               primary_key=True),
                        Column('id_user', Integer, nullable=False),
                        Column('id_bin', String(40), nullable=False),
                        Column('amount', Float(None, decimal_return_scale=7, asdecimal=True)),
                        Column('transactionfee', Float(None, decimal_return_scale=7, asdecimal=True)),
                        Column('coin', String(20), nullable=False),
                        Column('status', BigInteger, nullable=False),
                        Column('address', String(50), nullable=False),
                        Column('txid', String(100), nullable=False),
                        Column('applytime', TIMESTAMP, nullable=False),
                        Column('network', String(20), nullable=False),
                        Column('transfertype', BigInteger, nullable=False),
                        Column('info', String(200), nullable=False),
                        Column('confirmno', BigInteger, nullable=False),
                        Column('wallettype', BigInteger, nullable=False),
                        PrimaryKeyConstraint('id_withdraw_c', name='withdraw_pk'))

update_date = Table('update_table', meta,
                    Column('id_update', BigInteger, Identity("always"), nullable=False, primary_key=True),
                    Column('id_user', Integer, nullable=False),
                    Column('name_table', String(40), nullable=False),
                    Column('start_update_time', TIMESTAMP, nullable=False),
                    Column('end_update_time', TIMESTAMP, nullable=False),
                    PrimaryKeyConstraint('id_update', name='update_pk'))

meta.create_all(engine_fin)
"""
klines = Table('klines', meta,
               Column('id', Integer, Identity("always"), nullable=False, primary_key=True),
               Column('symbol', String(15), nullable=False),
               Column('open_time', TIMESTAMP, nullable=False),
               Column('open_price', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('high', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('low', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('close_price', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('volume', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('close_time', TIMESTAMP, nullable=False),
               Column('quote_asset_volume', Float(None, decimal_return_scale=7, asdecimal=True), nullable=False),
               Column('num_trade', Integer, nullable=False),
               Column('taker_buy_base_asset_volume', Float(None, decimal_return_scale=7, asdecimal=True),
                      nullable=False),
               Column('taker_buy_quote_asset_volume', Float(None, decimal_return_scale=7, asdecimal=True),
                      nullable=False),
               PrimaryKeyConstraint('id', name='kline_pk'))
     """
