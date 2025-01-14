class User:
    def __init__(self,
                 name: str = None,
                 nicknam: str = None,
                 email: str = None,
                 password: str = None):
        self.name = name
        self.nickname = nicknam
        self.password = password
        self.email = email
