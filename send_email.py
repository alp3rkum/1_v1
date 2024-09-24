# import os
import smtplib
from email.message import EmailMessage

# current_directory = os.path.dirname(os.path.abspath(__name__))
# html_file_path = [
#     os.path.join(current_directory,'templates','email','remindPassword.html')
# ]
subjects = [
    "Şifre Hatırlatma"
]

def send_email(smtp_email,smtp_key,recipent_email,mode,password):

    msg = EmailMessage()
    match mode:
        case 0: msg.set_content(f"Şifreniz {password}")
    msg['Subject'] = subjects[mode]
    msg['From'] = 'Kişisel Asistanınız'
    msg['To'] = recipent_email

    try:
        smtp = smtplib.SMTP_SSL('smtp.gmail.com',465)
        smtp.login(smtp_email,smtp_key)
        smtp.send_message(msg)
    except Exception as e:
        print(e)