import base64
import json
import time
from cryptography.hazmat.primitives.asymmetric import ed25519
import requests
import config
import time
import pandas as pd
import os
import sys
import logging
import sembol_list


API_KEY = config.api_key
API_SECRET = config.api_secret
son_kac_ortalama = 5
EVERY_SWAP_AMOUNT = 0.4

# DataFrame oluştur
data = {"Zaman Damgası": []}  # İlk sütun Zaman Damgası
for MARKET_SYMBOL in sembol_list.MARKET_SYMBOL_LIST:
    data[MARKET_SYMBOL] = []  # Diğer sütunlar için sembol adlarını kullanarak başlık ekle
df = pd.DataFrame(data)

def erişim_imzası(operate_method, argument, timetick, window_value):
    build_string = 'instruction=%s&' % (operate_method)
    sorted_keys = sorted(argument.keys())

    for key in sorted_keys:
        build_string += '%s=%s&' % (key, argument.get(key))

    build_string = build_string[:-1] + '&timestamp=%d&window=%d' % (timetick, window_value)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(API_SECRET)
        )
    signature = private_key.sign(build_string.encode())

    return base64.b64encode(signature).decode()

def erişim_oluştur(http_method, operate_method, path, argument):
    timetick = int(time.time() * 1000)
    window_value = 5000

    if operate_method:
        headers = {
            'X-Timestamp': str(timetick),
            'X-Window': str(window_value),
            'X-API-Key': API_KEY,
            'X-Signature': erişim_imzası(operate_method, argument, timetick, window_value),
        }
    else:
        headers = {}

    url = 'https://api.backpack.exchange/' + path
    http_method = http_method.lower()

    if http_method == 'get':
        if argument:
            sorted_keys = sorted(argument.keys())
            url += '?'
            for key in sorted_keys:
                url += '%s=%s&' % (key, argument.get(key))

            url = url[:-1]

        resp = requests.get(url, headers=headers, timeout=window_value)
        return resp.text
    elif http_method == 'post':
        resp = requests.post(url, headers=headers, timeout=window_value, json=argument)
        return resp.text
    elif http_method == 'delete':
        resp = requests.delete(url, headers=headers, timeout=window_value, json=argument)
        return resp.text

def emir_yürüt(sem, fiyat, miktar, al_sat):
    if al_sat:
        side_type = 'Bid'
    else:
        side_type = 'Ask'

    resp = erişim_oluştur('post', 'orderExecute', 'api/v1/order', {
            'orderType': 'Limit',
            'side': side_type,
            'price': fiyat,
            'symbol': sem,
            'quantity': str(miktar),
        })

    if resp == 'Insufficient funds':
        raise
    return json.loads()

def yeni_fiyat_al(MARKET_SYMBOL):
    fiyat_geçmişi = json.loads(erişim_oluştur('get', '', 'api/v1/klines', {'symbol': MARKET_SYMBOL, 'interval': '3m'}))
    fiyat = float(fiyat_geçmişi[-1]['close'])
    return fiyat

def varlık_al():
    return json.loads(erişim_oluştur('get', 'balanceQuery', 'api/v1/capital', {}))

def emir_bakiye_al():
    bakiye_listesi = varlık_al()
    usdc_bilgi = bakiye_listesi.get('USDC', {})
    emir_bakiye = float(usdc_bilgi.get('locked', 0))
    return emir_bakiye

def kullanılabilir_bakiye_al():
    bakiye_listesi = varlık_al()
    usdc_bilgi = bakiye_listesi.get('USDC', {})
    kullanılabir_bakiye = float(usdc_bilgi.get('available', 0))
    return kullanılabir_bakiye

def geri_sayım(saniye):
    while saniye:
        mins, saniye = divmod(saniye, 60)
        zaman_formatı = '{:02d}:{:02d}'.format(mins, saniye)
        print(zaman_formatı, end='\r')
        time.sleep(1)
        saniye -= 1

def excel_ekle(veri):
    global df
    df = df._append(veri, ignore_index=True)

def excel_satir_sil():
    global df
    if len(df) > 20:
        df = df.iloc[5:]  # İlk 5 satırı sil
        df.reset_index(drop=True, inplace=True)

def sesli_uyarı():
    if sys.platform.startswith('darwin'):  # macOS
        os.system('afplay /System/Library/Sounds/Ping.aiff')
    elif sys.platform.startswith('win32'):  # Windows
        import winsound
        winsound.Beep(1000, 200)  # Windows'ta bir bip sesi çalar

# Log dosyasının adı ve formatı
logdosyasi = 'uygulama.log'
logging.basicConfig(filename=logdosyasi, level=logging.INFO, format='%(asctime)s - %(message)s')

if __name__ == '__main__':
    while True:
        emir_bakiye = emir_bakiye_al()
        kullanılabilir_bakiye = kullanılabilir_bakiye_al()
        excel_satir_sil()  
        geri_sayım(10)
        print("Yeni fiyatlar alınıyor...")
        print(f"Kullanılabilir USDC Bakiye :{round(kullanılabilir_bakiye,2)}")
        yeni_veri = {"Zaman Damgası": pd.Timestamp.now()} 
        for MARKET_SYMBOL in sembol_list.MARKET_SYMBOL_LIST:
            fiyat = yeni_fiyat_al(MARKET_SYMBOL)
            if fiyat is not None:
                yeni_veri[MARKET_SYMBOL] = fiyat
                ortalama_fiyat = df[MARKET_SYMBOL].tail(son_kac_ortalama).mean()  
                print(f"{MARKET_SYMBOL:<15}: {fiyat:<15} ortalaması ({son_kac_ortalama}): {ortalama_fiyat:.4f}")
                if fiyat < ortalama_fiyat * 0.995  and emir_bakiye < 1:
                    while True:
                        alış_fiyat = yeni_fiyat_al(MARKET_SYMBOL)
                        miktar = round((kullanılabilir_bakiye / alış_fiyat) * 0.90, 2)
                        for index in range(10):
                            try:
                                print(emir_yürüt(MARKET_SYMBOL, alış_fiyat, miktar, True))
                                continue
                            except:
                                pass
                        fiyat = yeni_fiyat_al(MARKET_SYMBOL)
                        print(f"Alış Emri Verildi...| Sembol: {MARKET_SYMBOL} | Güncel Fiyat: {fiyat:<5} | Alış Emir Fiyatı: {alış_fiyat:<5} | Miktar: {miktar} ")
                        emir_bakiye = emir_bakiye_al()
                        if emir_bakiye < 1:
                            sesli_uyarı()
                            break

                    while True:
                        fiyat = yeni_fiyat_al(MARKET_SYMBOL)
                        satış_fiyat = round(alış_fiyat * 1.001,2)
                        kullanılabilir_bakiye = kullanılabilir_bakiye_al()
                        if kullanılabilir_bakiye < 10:
                            for index in range(10):
                                try:
                                    print(emir_yürüt(MARKET_SYMBOL,satış_fiyat, miktar, False))
                                    continue
                                except:
                                    pass
                            print(f"Satış Emri Verildi...| Sembol: {MARKET_SYMBOL} | Güncel Fiyat: {fiyat:<5} | Alış Emir Fiyatı: {alış_fiyat:<5}  | Miktar: {miktar} |  Satış Emir Fiyatı: {satış_fiyat:<5}")
                        else:
                            kullanılabilir_bakiye = kullanılabilir_bakiye_al()
                            kar = round((satış_fiyat-alış_fiyat)*miktar,2)
                            logging.info(f"Sembol: {MARKET_SYMBOL:<5} | Kullanılabilir Bakiye: {kullanılabilir_bakiye:<5} | Kar: {kar:<5}")
                            sesli_uyarı()
                            break
            else:
                logging.warning(f"Could not retrieve price for {MARKET_SYMBOL}")
        excel_ekle(yeni_veri)
