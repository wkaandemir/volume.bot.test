import base64
import datetime
import json
import random
import time
from cryptography.hazmat.primitives.asymmetric import ed25519
import requests
import config


API_KEY = config.api_key
API_SECERT = config.api_secret

MARKET_SYMBOL = 'SOL_USDC'
MAX_VOLUME = 1000000
EVERY_SWAP_AMOUNT = 0.4


def erişim_imzası(operate_method, argument, timetick, window_value):
    build_string = 'instruction=%s&' % (operate_method)
    sorted_keys = sorted(argument.keys())

    for key in sorted_keys:
        build_string += '%s=%s&' % (key, argument.get(key))

    build_string = build_string[:-1] + '&timestamp=%d&window=%d' % (timetick, window_value)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(API_SECERT)
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

def sembol_al():
    return json.loads(erişim_oluştur('get', '', 'api/v1/markets', {}))

def yeni_fiyat_al():
    fiyat_geçmişi = json.loads(erişim_oluştur('get', '', 'api/v1/klines', {'symbol': MARKET_SYMBOL, 'interval': '1m'}))
    fiyat = float(fiyat_geçmişi[-1]['close'])
    return fiyat

def geçmişi_al(sem):
    tüm_geçmiş = []
    index = 0

    while True:
        geçmiş_veri = json.loads(erişim_oluştur('get', 'orderHistoryQueryAll', 'wapi/v1/history/orders', {'symbol': sem, 'offset': index, 'limit': 1000}))
        index += 1000
        if geçmiş_veri:
            tüm_geçmiş += geçmiş_veri
        else:
            break

    return tüm_geçmiş

def toplam_hacmi_al(sem):
    tüm_geçmiş = geçmişi_al(sem)
    toplam_hacim = 0.0

    for geçmiş_bilgi in tüm_geçmiş:
        if not geçmiş_bilgi['status'] == 'Filled':
            continue
        
        toplam_hacim += round(float(geçmiş_bilgi['price']) * float(geçmiş_bilgi['quantity']), 3)

    return toplam_hacim

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


def usdcden_sol_hesapla(fiyat, usdc_miktarı):
    sol_miktarı = round((usdc_miktarı / fiyat) * 0.99, 2)  
    return sol_miktarı

def sol_bakiyesini_al():
    bakiye_listesi = varlık_al()
    sol_bilgi = bakiye_listesi.get('SOL', {})
    print(sol_bilgi)
    sol_bakiye = float(sol_bilgi.get('available', 0)) + float(sol_bilgi.get('locked', 0))

    return sol_bakiye

def usdc_bakiyesini_al():
    bakiye_listesi = varlık_al()
    usdc_bilgi = bakiye_listesi.get('USDC', {})
    usdc_bakiye = float(usdc_bilgi.get('available', 0))

    return usdc_bakiye

def toplam_sol_bakiyesini_al():
    bakiye_listesi = varlık_al()
    usdc_bilgi = bakiye_listesi.get('USDC', {})
    usdc_bakiye = float(usdc_bilgi.get('available', 0)) + float(usdc_bilgi.get('locked', 0))
    fiyat = yeni_fiyat_al()
    sol_bilgi = bakiye_listesi.get('SOL', {})
    sol_bakiye = float(sol_bilgi.get('available', 0)) + float(sol_bilgi.get('locked', 0)) + usdcden_sol_hesapla(fiyat, usdc_bakiye)
    
    return sol_bakiye

def tüm_sol_satın_al():
    usdc_bakiyesi = usdc_bakiyesini_al()

    if usdc_bakiyesi > 1:  # Çünkü sol kalmadı, tüm usdc'yi sol'a çevirmemiz gerekiyor
        fiyat = yeni_fiyat_al()
        sol_alma_miktarı = usdcden_sol_hesapla(fiyat, usdc_bakiyesi)
        print(emir_yürüt(MARKET_SYMBOL, fiyat, sol_alma_miktarı, True))

if __name__ == '__main__':
    toplam_bakiye = toplam_sol_bakiyesini_al()
    çıkış_gerekli = False
    
    while toplam_bakiye >= 0.1:   # Toplam varlık 0.1 sol'dan azsa işlem yapmayı durdur
        for index in range(10):
            try:  # Sol satıp usdc almayı dene
                fiyat = yeni_fiyat_al()
                print(datetime.datetime.now(), fiyat, 'Al')
                miktar = round(random.uniform(0.1, EVERY_SWAP_AMOUNT), 2)
                print(emir_yürüt(MARKET_SYMBOL, fiyat, miktar, False))
            except:  # Sol kalmadı
                print(datetime.datetime.now(), 'Emir İptal Edildi')
                emirleri_iptal_et(MARKET_SYMBOL)

                try:
                    print(datetime.datetime.now(), 'Sol Al')
                    tüm_sol_satın_al()


                    continue
                except:
                    pass
            try: 
                fiyat = yeni_fiyat_al()
                print(datetime.datetime.now(), fiyat, 'Sat')
                miktar = round(random.uniform(0.1, EVERY_SWAP_AMOUNT), 2)
                print(emir_yürüt(MARKET_SYMBOL, fiyat, miktar, True))
            except:
                pass
        if çıkış_gerekli:
            break


        toplam_bakiye = toplam_sol_bakiyesini_al()
        print(datetime.datetime.now(), 'Toplam Bakiye', toplam_bakiye, '(Sol)')

    if emirleri_al(MARKET_SYMBOL):
        emirleri_iptal_et(MARKET_SYMBOL)

    tüm_sol_satın_al()
