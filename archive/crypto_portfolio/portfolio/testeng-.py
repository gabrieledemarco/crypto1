from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

# Genera una chiave segreta (deve essere lunga 16, 24 o 32 byte per AES)
key = get_random_bytes(32)

# Cifra il dato
def encrypt_data(data, key):
    cipher = AES.new(key, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(data.encode(), AES.block_size))
    return cipher.iv + ct_bytes  # Restituisce IV + testo cifrato

# Decifra il dato
def decrypt_data(encrypted_data, key):
    iv = encrypted_data[:16]  # IV è la prima parte del dato cifrato
    ct = encrypted_data[16:]  # Il testo cifrato è la parte restante
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted_data = unpad(cipher.decrypt(ct), AES.block_size)
    return decrypted_data.decode()

# Esempio
data = "my_secret_api_key"
encrypted = encrypt_data(data, key)
print("Encrypted:", encrypted)

decrypted = decrypt_data(encrypted, key)
print("Decrypted:", decrypted)