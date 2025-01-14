import pandas as pd
from DbService import DbService
from binance.client import  Client
from BinanceService import BinanceService
from BinanceDAO import BinanceDAO
from UserService import UsrService
from User import User

utente = 'gab1'
psw = UsrService(nick_name=utente).get_password_of_user()

usr = User(nicknam=utente,
           password=psw[1])

Api = UsrService(nick_name=utente).get_Api_of_usr()
id_user = UsrService(nick_name=utente).get_user_id()

client = Client(api_key=Api[0][0],
                    api_secret=Api[0][1])
print(client.get_all_coins_info())
symbols_df = pd.DataFrame(client.get_all_coins_info())
print(symbols_df)
""" 

resp = client.get_all_tickers()
symbol_list = []
for symb in resp:
    symbol_list.append(resp[''])



Bindao = BinanceDAO(DbService=DbService(),
                    api_key=Api[0][0],
                    api_secret=Api[0][1])

Binsrv = BinanceService(DbService=DbService(),
                        api_key=Api[0][0],
                        api_secret=Api[0][1])

#SELEZIONE CONTROVALUTA
counter_value = "USDT"
#CALCOLO AMOUNT IN PORTF
df_account_asst = Binsrv.get_df_account_snap()
#CREAZIONE SYMBOL CON CONTROVALUTA
df_account_asst["symbol"] = df_account_asst["asset"] + counter_value



#DOWNLOAD PRICE
df_24H_symbol = Binsrv.get_df_symbol24H()


df_portf = pd.merge(df_account_asst, df_24H_symbol, on='symbol', how='left').dropna()

df_portf['mktValue'] = df_portf['tot'].astype(float) * df_portf['prevClosePrice'].astype(float)

mkt_value = df_portf['mktValue'].sum()
print(df_portf)
print(mkt_value, " in USDT")"""