import time
import hashlib
import hmac
import requests

# API Key e Secret
api_key = 'x9KAJ0OLKL5CtGWccR7a2xnFeJcRzrHLDo0xYlt5fETPLc4D40lgLeOW03srpHrU'
api_secret = '4eFv0el5mR3Qc6FpdqXZr3OtxpX9NXWLmN0N8GOEoQxBJyjK6dTYkMsOqYIt2KlX'

# Parametri della richiesta
base_url = 'https://api.binance.com'
endpoint = '/sapi/v1/asset/assetDividend'

# Parametri obbligatori
params = {
    'timestamp': int(time.time() * 1000),  # Timestamp in millisecondi
}

# Calcolo della firma
query_string = '&'.join([f"{key}={value}" for key, value in params.items()])
signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

# Aggiungi la firma ai parametri
params['signature'] = signature

# Header con la chiave API
headers = {
    'X-MBX-APIKEY': api_key
}

# Invia la richiesta GET con i parametri firmati
response = requests.get(base_url + endpoint, headers=headers, params=params)

# Stampa la risposta
print(response.json())


