import requests

def netgsm_sms(usercode,userpass,recipent_phone,otp):
    url = "https://api.netgsm.com.tr/sms/send/get/"
    data = {
        'usercode': usercode,
        'password': userpass,
        'gsmno': recipent_phone,
        'message': f"Kişisel Asistanınız ile sohbet edebilmek için girmeniz gereken tek kullanımlık şifre: {otp}",
        'msgheader': "Kişisel Asistanınız"
    }

    response = requests.post(url, data=data)
    print(response.text)