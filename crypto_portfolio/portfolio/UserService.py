from UsersDAO import UsersDAO
from DbService import DbService


class UsrService:
    def __init__(self,
                 api_key: str = None,
                 api_secret: str = None,
                 nick_name: str = None,
                 pass_word: str = None):
        self.dbs = DbService()
        self.nickname = nick_name
        self.password = pass_word
        self.api_key = api_key
        self.api_secret = api_secret
        self.__user_dao = UsersDAO(DbServ=self.dbs,
                                   api_key=self.api_key,
                                   api_secret=self.api_secret,
                                   nick_name=self.nickname,
                                   pass_word=self.password)

    def get_user_id(self):
        return self.dbs.get_select_with_where(name_table="users",
                                              select_columns="id_user",
                                              where_columns="nickname",
                                              values_column=self.nickname)[0]

    def get_Api_of_usr(self):
        return self.__user_dao.get_Api_of_usr()

    def is_user_registered(self) -> bool:
        return self.__user_dao.is_user_registered()

    def insert_user(self):
        return self.__user_dao.insert_user()

    def insert_new_user_and_data(self):
        return self.__user_dao.insert_new_user_and_data()

    def get_all_users(self):
        return self.dbs.get_all_value_in_column(name_column="nickname",
                                                name_table="users")

    def get_password_of_user(self):
        id_user = self.dbs.get_select_with_where(name_table="users",
                                                 select_columns="id_user",
                                                 where_columns="nickname",
                                                 values_column=self.nickname)[0]

        passw = self.dbs.get_select_with_where(name_table="users",
                                               select_columns="password",
                                               where_columns="id_user",
                                               values_column=id_user)[0]

        return id_user, passw
