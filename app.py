from flask import *
from flask_cors import CORS
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from flask_session import Session
from flask_admin import Admin
# from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# from flask_wtf.csrf import CSRFProtect

import openai
import google.generativeai as genai

import mysql.connector
import psycopg2
import requests
from datetime import datetime, timedelta
import base64
from io import BytesIO
from youtube_transcript_api import YouTubeTranscriptApi
import secrets
from striprtf.striprtf import rtf_to_text
import docx2txt
import socket


from gtts import gTTS

# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload
# import google.oauth2.credentials

from send_email import send_email
from ddg_search import search_web_ddg

import os

def is_local_machine():
    hostname = socket.gethostname()
    print(hostname)
    return "DESKTOP-" in hostname

#####################################
#Global değişkenler

API_KEYS = []
with open('apikeys.txt', 'r') as f:
    for line in f:
        API_KEYS.append(line.split('=')[1].strip())

USER = {'id':-1,'username':'','email':'','tokens_left':0,'points_left':0}

SERVICE_ACCOUNT_FILE_PATH = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# credentials = service_account.Credentials.from_service_account_file(
#     SERVICE_ACCOUNT_FILE_PATH, scopes=SCOPES)

# drive_service = build('drive', 'v3', credentials=credentials)
#####################################


#####################################
#MySQL ve veritabanı işlemleri
# connection = mysql.connector.connect(
#     host=API_KEYS[2],
#     port=int(API_KEYS[3]),
#     user=API_KEYS[4],
#     password=API_KEYS[5],
#     database=API_KEYS[6]
#     ##Deploy için bunları kullanabilirsiniz
#     #host=os.getenv("DB_HOST"),
#     #user=os.getenv("DB_USER"),
#     #password=os.getenv("DB_PASSWORD"),
#     #database=os.getenv("DB_NAME")
# )
if is_local_machine():
    conn_string = f"postgresql://{API_KEYS[4]}:{API_KEYS[5]}@{API_KEYS[2]}:5432/{API_KEYS[6]}"
else:
    db_port = os.getenv('DB_PORT', '5432')  # default to 5432 if not set
    conn_string = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{db_port}/{os.getenv('DB_NAME')}"
print(conn_string)
connection = psycopg2.connect(conn_string)

def get_password_from_db(user_email):
    cursor = connection.cursor()
    cursor.execute("SELECT user_password FROM users WHERE email = %s", (user_email,))
    result = cursor.fetchone()
    cursor.close()
    if result:
        return result['user_password']
    else:
        return None

def load_user_mysql(user_id=None,user_name=None):
    global USER
    cursor = connection.cursor()
    if user_id != None:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    if user_name != None:
        cursor.execute("SELECT * FROM users WHERE username = %s", (user_name,))
    user = cursor.fetchone()
    if user:
        USER['id'] = user[0]
        USER['username'] = user[1]
        USER['email'] = user[2]
        USER['tokens_left'] = user[4]
        USER['points_left'] = user[5]
    cursor.close()
    return None

def update_user_tokens(user_id, tokens_used):
    user = User.query.get(user_id)
    if user:
        # Aylık token sıfırlama kontrolü
        if datetime.now() - user.last_token_reset > timedelta(days=30):
            user.tokens_left = 1000  # Aylık token miktarını sıfırla
            user.last_token_reset = datetime.now()

        if user.tokens_left >= tokens_used:
            user.tokens_left -= tokens_used
            cursor = connection.cursor()
            cursor.execute("UPDATE users SET tokens_left = %s WHERE id = %s", (user.tokens_left, user_id))
            connection.commit()
            cursor.close()
            return True
        else:
            return False
    return False

#####################################

#####################################
#Flask tanımlamaları
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_COOKIE_NAME'] = 'google-login-session'
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = secrets.token_urlsafe(16)
admin = Admin(app, name='My Admin', template_mode='bootstrap3')
# limiter = Limiter(get_remote_address,app=app,default_limits=['100 per day'],storage_uri='memory://')
# csrf = CSRFProtect(app) #login/signup'u engelliyor o yüzden devredışı bırakıldı
CORS(app)

####################################


####################################
#Google OAuth Bilgileri ve sınıfları
oauth = OAuth(app)
google_oauth = oauth.register(
    name='google',
    client_id='457680679934-ksrdt3eihj6m03j3vh1prsr91dk6dm7d.apps.googleusercontent.com',
    client_secret='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',
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    jwks_uri='https://www.googleapis.com/oauth2/v3/certs',
    client_kwargs={'scope': 'openid profile email'},
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
)

login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

####################################

@login_manager.user_loader
def load_user(user_id):
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if user:
        return User(id=user['id'], name=user['name'], email=user['email'])
    return None

openai.api_key = ""
genai.configure(api_key="AIzaSyAbkz38WTZLYTjxC97ZEpAH92z_uf72zm0")

@app.route('/oauth2callback')
# @limiter.limit("10 per day")
def oauth2callback():
    print(session)
    print(session.get('state'))
    if 'state' not in session or request.args.get('state') != session['state']:
        return 'State does not match!', 400
    
    token = google_oauth.authorize_access_token()
    resp = google_oauth.get('https://openidconnect.googleapis.com/v1/userinfo')
    user_info = resp.json()
    
    user = User(id=user_info['sub'], name=user_info['name'], email=user_info['email'])
    
    cursor = connection.cursor()
    cursor.execute("INSERT INTO users (username, email, user_password, phone_number) VALUES (%s, %s, '', '') ON CONFLICT (username) DO UPDATE SET username=%s, email=%s",
                (user.name, user.email, user.name, user.email))
    connection.commit()
    load_user_mysql(user_name=user.name)
    cursor.close()
    
    login_user(user)
    
    return redirect('/chat')

############################################
#AI Model etkileşimleri
def openai_response(message):
    try:
        if update_user_tokens(USER['id'], 1):
            response = openai.Completion.create(
                    engine="text-davinci-002",
                    prompt=message,
                    max_tokens=150,
                    temperature=0.5
                )
        else:
            response = "I'm sorry, you don't have enough tokens. Please top up your tokens."
    except Exception as e:
        response = e
    return response

def gemini_response(message):
    print(message)
    prompt = f"Şu mesaja en fazla 100 kelime kullanarak anlamlı ve tamamlanmış bir yanıt ver: {message}"
    model = genai.GenerativeModel('gemini-pro')
    config = genai.GenerationConfig()
    response = model.generate_content(prompt, generation_config=config)
    print(response)
    print(response._result.candidates[0].content.parts[0].text)
    response_text = response._result.candidates[0].content.parts[0].text
    return response_text

############################################


############################################

@app.route('/upload-file',methods=['POST'])
def upload_file():
    # print(request.form)
    file_content = request.form['file_content']
    model_index = int(request.form['model_index'])
    print(file_content)
    match model_index:
        case 0: response = gemini_response(file_content)
        case 1: response = openai_response(file_content)
    if isinstance(response, Exception):
        response_data = {'result': 'error', 'message': str(response)}
    else:
        response_data = {'result': 'success', 'response': response}
    return jsonify(response_data)

@app.route('/transcript-tube',methods=['POST'])
def transcript_tube():
    print(request.form)
    message = request.form.get('video_id')
    print(message)
    yt_api = YouTubeTranscriptApi()
    response = yt_api.get_transcript(message)
    print(response)
    response_data = {'result': 'success', 'message': response}
    return jsonify(response_data)

@app.route('/take-voice',methods=['POST'])
def take_voice():
    response = ''
    print(request.form)
    model_index = int(request.form.get('model_index'))
    message = request.form.get('message')
    print(message)
    match model_index:
        case 0: response = gemini_response(message)
        case 1: response = openai_response(message)
    if isinstance(response, Exception):
        response_data = {'result': 'error', 'message': str(response)}
    else:
        response_text = response
        tts = gTTS(text=response_text, lang='tr')
        audio_fp = BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        response_audio = base64.b64encode(audio_fp.read()).decode('utf-8')

        response_data = {'result': 'success', 'audio': response_audio}
    return jsonify(response_data)

@app.route('/search-input',methods=['POST'])
def search_web():
    print(request.form)
    query = request.form.get('query')
    return search_web_ddg(query)

@app.route('/take-input',methods=['POST'])
# @limiter.limit("1000 per day")
def take_input():
    response = ''
    print(request.form)
    model_index = int(request.form.get('model_index'))
    message = request.form.get('message')
    print(message)
    match model_index:
        case 0: response = gemini_response(message)
        case 1: response = openai_response(message)
    if isinstance(response, Exception):
        response_data = {'result': 'error', 'message': str(response)}
    else:
        response_data = {'result': 'success', 'response': response}
    return jsonify(response_data)

@app.route('/offers')
# @limiter.limit("100 per day")
def offers():
    if USER.get('id') == -1:
        return redirect(url_for("index"))
    else:
        return render_template("offers.html",user=USER)

@app.route('/dashboard')
# @limiter.limit("100 per day")
def dashboard():
    if USER.get('id') == -1:
        return redirect(url_for("index"))
    else:
        return render_template("dashboard.html",user=USER)

@app.route('/chat',methods=['GET'])
# @limiter.limit("100 per day")
def chat_screen():
    if USER.get('id') == -1:
        return redirect(url_for("index"))
    else:
        return render_template("chat.html",user=USER)

@app.route('/signup-google',methods=['POST'])
# @limiter.limit("10 per day")
def signup_action_google():
    state = os.urandom(24).hex()
    session['state'] = state
    redirect_uri = "http://localhost:5000/oauth2callback"
    return jsonify({'redirect_url': google_oauth.authorize_redirect(redirect_uri, state=state).headers['Location']})

@app.route('/logout',methods=['GET'])
# @limiter.limit("100 per day")
def logout():
    global USER
    USER['id'] = -1
    USER['username'] = ''
    USER['email'] = ''
    USER['tokens_left'] = 0
    return redirect(url_for("index"))

@app.route('/signup',methods=['POST'])
# @limiter.limit("100 per day")
def signup_action():
    print("helo")
    form_data = request.get_json()
    print(form_data)
    username = form_data['username']
    email = form_data['email']
    password = form_data['password']
    phone = form_data['phone']

    cursor = connection.cursor()
    cursor.execute("INSERT INTO users (username, email, user_password, phone_number) VALUES (%s, %s, %s, %s)", (username, email, password,phone))
    connection.commit()
    cursor.close()
    load_user_mysql(user_name=username)
    return redirect(url_for('chat_screen'))

@app.route('/remind-password',methods=['POST'])
# @limiter.limit("5 per day")
def remind():
    form_data = request.get_json()
    print(form_data)
    user_email = form_data['email']
    smtp_email = API_KEYS[7]
    smtp_key = API_KEYS[8]
    try:
        send_email(smtp_email,smtp_key,user_email,0,get_password_from_db(user_email))
        return jsonify({'ok':True}), 200
    except Exception as e:
        print(e)

@app.route('/login',methods=['GET','POST'])
# @limiter.limit("100 per day")
def signup():
    if request.method == 'GET':
        return render_template('login.html')
    elif request.method == 'POST':
        form_data = request.get_json()
        print(form_data)
        email = form_data['email']
        password = form_data['password']

        cursor = connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s AND user_password = %s", (email, password))
        user = cursor.fetchone()
        if user:
            USER['id'] = user[0]
            USER['username'] = user[1]
            USER['email'] = user[2]
            USER['tokens_left'] = user[4]
            return redirect('/chat')
        else:
            return render_template('login.html',error="Hatalı kullanıcı adı ya da sifre girdiniz")

@app.route('/index',methods=['GET','POST'])
# @limiter.limit("100 per day")
def index():
    if USER.get('id') == -1:
        return render_template('index.html',userLogged=False)
    else:
        return render_template('index.html',userLogged=True)

@app.route('/',methods=['GET','POST'])
# @limiter.limit("100 per day")
def index_first():
    if USER.get('id') == -1:
        return render_template('index.html',userLogged=False)
    else:
        return render_template('index.html',userLogged=True)

if __name__ == '__main__':
    app.run(debug=True)