from binance.client import Client
import time
from datetime import datetime, timedelta


# from BinanceDAO import BinanceDAO


# Funzione per ottenere la cronologia dei pagamenti fiat
def get_fiat_payments_history(client, begin_time, end_time):
    return client.get_fiat_payments_history(transactionType='0', beginTime=begin_time, endTime=end_time)


def get_fiat_deposit_history(client, begin_time, end_time):
    return client.get_fiat_deposit_withdraw_history(transactionType='0', beginTime=begin_time, endTime=end_time)


# Funzione per convertire la data in timestamp (millisecondi)
def date_to_timestamp(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(time.mktime(dt.timetuple()) * 1000)


# Funzione principale per richiedere la cronologia da 2017-01-01 a oggi in finestre di 500 giorni
def fetch_fiat_history_in_batches(client):
    # Data di inizio (1 gennaio 2017) e data di fine (oggi)
    start_date = "2017-01-01"
    end_date = datetime.today().strftime("%Y-%m-%d")

    # Converti le date in timestamp
    start_timestamp = date_to_timestamp(start_date)
    end_timestamp = date_to_timestamp(end_date)

    # Imposta la finestra di intervallo (500 giorni)
    max_days = 500
    current_start = start_timestamp
    current_end = min(current_start + max_days * 86400000, end_timestamp)  # 86400000 ms in un giorno

    # Ciclo per recuperare i dati in finestre di 500 giorni
    all_history = []
    while current_start < end_timestamp:
        # Chiama l'API con la finestra corrente
        response = get_fiat_payments_history(client, current_start, current_end)
        # print(response)
        if response and 'data' in response:
            all_history.extend(response['data'])  # Aggiungi i dati alla lista
            # print(f"Recuperati {len(response['data'])} record tra {current_start} e {current_end}")

        # Aggiorna il periodo per la prossima richiesta
        current_start = current_end + 1
        current_end = min(current_start + max_days * 86400000, end_timestamp)  # Next window

    return all_history


def fetch_fiat_deposit_batches(client):
    # Data di inizio (1 gennaio 2017) e data di fine (oggi)
    start_date = "2017-01-01"
    end_date = datetime.today().strftime("%Y-%m-%d")

    # Converti le date in timestamp
    start_timestamp = date_to_timestamp(start_date)
    end_timestamp = date_to_timestamp(end_date)

    # Imposta la finestra di intervallo (500 giorni)
    max_days = 500
    current_start = start_timestamp
    current_end = min(current_start + max_days * 86400000, end_timestamp)  # 86400000 ms in un giorno
    time.sleep(10)
    # Ciclo per recuperare i dati in finestre di 500 giorni
    all_history = []
    while current_start < end_timestamp:
        # Chiama l'API con la finestra corrente
        response = get_fiat_deposit_history(client, current_start, current_end)
        print(response)
        time.sleep(60)
        if response and 'data' in response:
            all_history.extend(response['data'])  # Aggiungi i dati alla lista
            # print(f"Recuperati {len(response['data'])} record tra {current_start} e {current_end}")

        # Aggiorna il periodo per la prossima richiesta
        current_start = current_end + 1
        current_end = min(current_start + max_days * 86400000, end_timestamp)  # Next window

    return all_history


# Esempio di utilizzo
api_key = "x9KAJ0OLKL5CtGWccR7a2xnFeJcRzrHLDo0xYlt5fETPLc4D40lgLeOW03srpHrU"
secret_key = "4eFv0el5mR3Qc6FpdqXZr3OtxpX9NXWLmN0N8GOEoQxBJyjK6dTYkMsOqYIt2KlX"

# Inizializza il servizio
# Inizializza il servizio
client = Client(api_key, secret_key)

# Esegui la funzione (assicurati che `client` sia definito)
fiat_history = fetch_fiat_history_in_batches(client)

# Stampa i risultati
# print(f"Totale record recuperati: {len(fiat_history)}")
# print(fiat_history)


fiat_dep_hist = fetch_fiat_deposit_batches(client)

print(fiat_dep_hist)
