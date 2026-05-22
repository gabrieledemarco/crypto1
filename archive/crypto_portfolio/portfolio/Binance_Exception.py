from binance.exceptions import BinanceAPIException
import time


class BinanceException(Exception):
    def __init__(self, message, code=None):
        self.message = message
        self.code = code

    def __str__(self):
        if self.code:
            return f"BinanceException: {self.message} (code={self.code})"
        else:
            return f"BinanceException: {self.message}"


def safe_api_request(func, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code == -1003:  # Too many requests
                print("Too many requests. Waiting before retrying...")
                time.sleep(1)  # Wait for 1 second before retrying
            else:
                raise BinanceException(e.message, e.code) from e
