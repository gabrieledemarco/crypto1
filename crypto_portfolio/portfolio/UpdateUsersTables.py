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



    def update_client(self):
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