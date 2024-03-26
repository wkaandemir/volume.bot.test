import base64
import datetime
import json
import random
import time
from cryptography.hazmat.primitives.asymmetric import ed25519
import requests


API_KEY = "JoNTFQpe+KuTrT2GARWHEwgjpLHdNQK3B8tmnhB9+/c="
API_SECRET = "xp6eoV78koBNc5WdQMZ+neEp2bJLevVPwDGYSJ5DuMo="

API_KEY = input("API Key girin: ")
API_SECRET = input("API Secret girin: ")

MARKET_SYMBOL = 'WEN_USDC'


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


def yeni_fiyat_al():
    fiyat_geçmişi = json.loads(erişim_oluştur('get', '', 'api/v1/klines', {'symbol': MARKET_SYMBOL, 'interval': '1m'}))
    fiyat = float(fiyat_geçmişi[-1]['close'])
    return fiyat


def varlık_al():
    return json.loads(erişim_oluştur('get', 'balanceQuery', 'api/v1/capital', {}))

def depozit_adresi_al(blockchain):
    return erişim_oluştur('get', 'depositAddressQuery', 'wapi/v1/capital/deposit/address', {'blockchain': blockchain})

def emirleri_al(semboller):
    return json.loads(erişim_oluştur('get', 'orderQueryAll', 'api/v1/orders', {'symbol': semboller}))

def emirleri_iptal_et(sem):
    return erişim_oluştur('delete', 'orderCancelAll', 'api/v1/orders', {'symbol': sem})

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

    if resp == 'Yetersiz bakiye':
        raise
    return json.loads()


def usdcden_wen_hesapla(fiyat, usdc_miktarı):
    wen_miktarı = ((usdc_miktarı / fiyat) * 0.99)
    return wen_miktarı

def wen_bakiyesini_al():
    bakiye_listesi = varlık_al()
    wen_bilgi = bakiye_listesi.get('WEN', {})
    print(wen_bilgi)
    wen_bakiye = float(wen_bilgi.get('available', 0)) + float(wen_bilgi.get('locked', 0))

    return wen_bakiye

def usdc_bakiyesini_al():
    bakiye_listesi = varlık_al()
    usdc_bilgi = bakiye_listesi.get('USDC', {})
    usdc_bakiye = float(usdc_bilgi.get('available', 0))

    return usdc_bakiye

def toplam_wen_bakiyesini_al():
    bakiye_listesi = varlık_al()
    usdc_bilgi = bakiye_listesi.get('USDC', {})
    usdc_bakiye = float(usdc_bilgi.get('available', 0)) + float(usdc_bilgi.get('locked', 0))
    fiyat = yeni_fiyat_al()
    wen_bilgi = bakiye_listesi.get('WEN', {})
    wen_bakiye = float(wen_bilgi.get('available', 0)) + float(wen_bilgi.get('locked', 0)) + usdcden_wen_hesapla(fiyat, usdc_bakiye)

    return wen_bakiye

def tüm_wen_satın_al():
    usdc_bakiyesi = usdc_bakiyesini_al()

    if usdc_bakiyesi > 1:  # Çünkü wen kalmadı, tüm usdc'yi wen'a çevirmemiz gerekiyor
        fiyat = yeni_fiyat_al()
        wen_alma_miktarı = usdcden_wen_hesapla(fiyat, usdc_bakiyesi)
        print(emir_yürüt(MARKET_SYMBOL, fiyat, wen_alma_miktarı, True))

if __name__ == '__main__':
    toplam_bakiye = toplam_wen_bakiyesini_al()
    çıkış_gerekli = False

    while toplam_bakiye >= 0.1:   # Toplam varlık 0.1 wen'dan azsa işlem yapmayı durdur
        for index in range(10):
            try:  # wen satıp usdc almayı dene
                fiyat = yeni_fiyat_al()
                toplam_bakiye = toplam_wen_bakiyesini_al()
                min_miktar = toplam_bakiye * 0.25
                max_miktar = toplam_bakiye * 0.30
                miktar = round(random.uniform(min_miktar, max_miktar))
                print(emir_yürüt(MARKET_SYMBOL, fiyat, miktar, False))
            except:  # wen kalmadı
                emirleri_iptal_et(MARKET_SYMBOL)
                try:
                    print(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'Alındı')
                    tüm_wen_satın_al()
                    continue
                except:
                    pass
            try:
                fiyat = yeni_fiyat_al()
                print(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'Satıldı')
                miktar = round(random.uniform(min_miktar, max_miktar))
                print(emir_yürüt(MARKET_SYMBOL, fiyat, miktar, True))
            except:
                pass
        if çıkış_gerekli:
            break


    if emirleri_al(MARKET_SYMBOL):
        emirleri_iptal_et(MARKET_SYMBOL)

    tüm_wen_satın_al()
