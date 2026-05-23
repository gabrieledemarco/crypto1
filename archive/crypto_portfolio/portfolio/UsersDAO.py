from datetime import datetime

from DbService import DbService
from InsertValueInTable import InsertValueInTable


class UsersDAO:

    def __init__(self,
                 DbServ: DbService,
                 api_key: str = None,
                 api_secret: str = None,
                 nick_name: str = None,
                 pass_word: str = None,
                 x_effective_from=None,
                 x_effective_to=str('31-12-9999')):

        self.db_ser = DbServ
        self.api_key = api_key
        self.api_secret = api_secret
        self.nick_name = nick_name
        self.pass_word = pass_word
        self.effective_f = x_effective_from
        self.effective_t = x_effective_to

    def get_Api_of_usr(self):
        Api = self.db_ser.get_select_with_where(select_columns=['api_key', 'api_secret'],
                                                where_columns='nickname',
                                                values_column=self.nick_name,
                                                name_table='users')
        print(Api[0])
        if len(Api) > 0:
            if self.api_key is None or self.api_secret is None:
                self.api_secret = Api[0][1]
                self.api_key = Api[0][0]

        return Api

    def is_user_registered(self) -> bool:
        user = self.db_ser.get_select_with_where(select_columns='nickname',
                                                 name_table='users',
                                                 where_columns='nickname',
                                                 values_column=self.nick_name)
        value = 0
        if len(user) == 0:
            value = False
        elif len(user) > 0:
            value = True
        else:
            print("something goes wrong")

        return value

    def insert_user(self):
        return self.db_ser.insert(name_table='users', list_record=[self.api_key,
                                                                   self.api_secret,
                                                                   self.nick_name,
                                                                   self.pass_word,
                                                                   self.effective_f,
                                                                   self.effective_t])

    def insert_new_user_and_data(self):
        self.insert_user()
        insert_value = InsertValueInTable(api_key=self.api_key, api_secret=self.api_secret)
        insert_value.insert_dividends()
        insert_value.insert_orders()
        insert_value.insert_trades()
        insert_value.insert_deposit_withdraw()
