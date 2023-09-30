from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_sqlalchemy import SQLAlchemy
import pytz
import smtplib
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string
import secrets
import sqlite3
import os
import winrm
from subprocess import run
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from flask_session import Session
from waitress import serve

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'RandomString2020@'                       # Set your secret key (random string)
db = SQLAlchemy(app)
app.config['SESSION_TYPE'] = 'filesystem'                   
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True


app.config['MAIL_SERVER'] = 'smtp.gmail.com'                # Set your SMTP server URL
app.config['MAIL_PORT'] = 587                               # Set your SMTP port
app.config['MAIL_USE_TLS'] = True                           # Use SSL 
app.config['MAIL_USERNAME'] = 'hello@aulabook.com'          # Set your smtp username
app.config['MAIL_PASSWORD'] = 'xbmiglnyzzfsrjfm'            # Set your smtp password
app.config['MAIL_DEFAULT_SENDER'] = 'hello@aulabook.com'

Session(app)

admin_token='ChangeMe'                                      # The token for accessing /visualizza page

host = '10.237.11.200'                                      # Active directory server IP
domain = 'LaboratorioSP'                                    # Domain (without tld)
user = 'Administrator'                                      # User with admin privilege
password = 'Aul4b00k@d3m001'                                # Password
ou = 'Laboratorio'                                          # OU where you want to create users
dc='laboratoriosp'                                          # Domain (without tld)
dc2='local'                                                 # TLD
cn='UtentiLaboratorio'                                      # Group where you want to add users
cdc='laboratoriosp.local'                                   # Complete domain name 

nomelab = "Aula VirtualSet - Sede Centrale"                 # Laboratory/room name
istituto = "I.I.S. Leonardo"                                # School name
indirizzo_responsabile = "mail@paganosimone.com"            # Lab/room manager e-mail
indirizzo_viceresponsabile = "email@paganosimone.com"       # Second manager e-mail
responsabile = "Simone Pagano"                              # Manager name
url = "demo.aulabook.com"                                   # URL of aulabook instance

winsession = winrm.Session(host, auth=('{}@{}'.format(user,domain), password), transport='ntlm')

mail = Mail(app)

with app.app_context():
    db.create_all()

def generate_random_code():
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(6))

class Prenotazione(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    classe = db.Column(db.String(100), nullable=False)
    ora_inizio = db.Column(db.String(10), nullable=False)
    ora_fine = db.Column(db.String(10), nullable=False)
    giorno = db.Column(db.String(10), nullable=False)
    descrizione = db.Column(db.String(500), nullable=False)
    codice_identificativo = db.Column(db.String(6), nullable=False)
    docente_accompagnatore = db.Column(db.String(100), nullable=False)
    segnalazione = db.Column(db.String(1000), nullable=True)
    timestamp = db.Column(db.String(19), default=datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

@app.route('/', methods=['GET', 'POST'])
def index():

    return render_template('index.html', nomelab=nomelab, istituto=istituto, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile)


@app.route('/aggiungi_prenotazione', methods=['GET', 'POST'])
def aggiungi_prenotazione():
    if request.method == 'POST':

        giorno = request.form['giorno']
        ora_inizio = request.form['ora_inizio']
        ora_fine = request.form['ora_fine']

        if verifica_sovrapposizione_orari(giorno, ora_inizio, ora_fine):
            return redirect(url_for('prenotazione_esistente'))
        
        nome = request.form['nome']
        cognome = request.form['cognome']
        email = request.form['email']
        classe = request.form['classe']
        descrizione = request.form['descrizione']
        codice_identificativo = generate_random_code()
        docente_accompagnatore = request.form['docente_accompagnatore']

        prenotazione = Prenotazione(nome=nome, cognome=cognome, email=email, classe=classe, ora_inizio=ora_inizio,
                                    ora_fine=ora_fine, giorno=giorno, descrizione=descrizione,
                                    codice_identificativo=codice_identificativo,
                                    docente_accompagnatore=docente_accompagnatore)
        db.session.add(prenotazione)
        db.session.commit()

        ora_inizio_dt = datetime.strptime(ora_inizio, '%H:%M')
        ora_fine_dt = datetime.strptime(ora_fine, '%H:%M')

        if ora_fine_dt <= ora_inizio_dt:
            flash('The end time must be after the start time.', 'error') #ENGTEXT
            return render_template('aggiungi_prenotazione.html')

        durata_prenotazione = ora_fine_dt - ora_inizio_dt

        ora_fine_effettiva = ora_inizio_dt + durata_prenotazione
        
        username = "lab"+codice_identificativo
        password = "S3cur3pass@"

        message = Message("Reservation confirmed", sender="hello@aulabook.com", recipients=[email]) #ENGTEXT

        message.html = render_template('email_conferma.html', nome=nome, cognome=cognome, nomelab=nomelab,
                               codice_identificativo=codice_identificativo, giorno=giorno, classe=classe, docente_accompagnatore=docente_accompagnatore, descrizione=descrizione, username=username, password=password,
                               ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile)
        
        mail.send(message)
               
        data_eliminazione = request.form['giorno']
        ora_eliminazione = request.form['ora_fine']
        
        data_eliminazione_format = datetime.strptime(data_eliminazione, '%Y-%m-%d').strftime('%d/%m/%Y')

        command = """dsadd user "cn={},ou={},dc={},dc={}" -disabled no -upn {}@{} -pwd S3cur3pass@ -mustchpwd no -memberof cn={},ou={},dc={},dc={} -acctexpires never""".format(username,ou,dc,dc2,username,cdc,cn,ou,dc,dc2)
        
        schedule = f'schtasks /create /sc once /st {ora_eliminazione} /sd {data_eliminazione_format} /tn DisabilitaUtente{username} /tr "net user {username} /active:no"'  
        
        print(schedule)
          
        r = winsession.run_cmd(command)
        r2 = winsession.run_cmd(schedule)
        
        print(r.status_code)
        print(r.std_out)
        print(r.std_err)
        
        r_status=r.status_code
        r_stdout=r.std_out
        r_stderr=r.std_err
        
        print(r2.status_code)
        print(r2.std_out)
        print(r2.std_err)
        
        r2_status=r2.status_code
        r2_stdout=r2.std_out
        r2_stderr=r2.std_err
        
        messageresponsabile = Message("New reservation", sender="hello@aulabook.com", recipients=[indirizzo_responsabile, indirizzo_viceresponsabile]) #ENGTEXT
        messageresponsabile.html = render_template('email_conferma_responsabile.html', nome=nome, cognome=cognome, nomelab=nomelab,
                               codice_identificativo=codice_identificativo, giorno=giorno, classe=classe, docente_accompagnatore=docente_accompagnatore, descrizione=descrizione, username=username, password=password,
                               ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile, r_status=r_status, r2_status=r2_status, r_stdout=r_stdout, r2_stdout=r2_stdout, r_stderr=r_stderr, r2_stderr=r2_stderr)

        mail.send(messageresponsabile)
   
        flash('Reservation added successfully.', 'success') #ENGTEXT
        return redirect(url_for('prenotazione_confermata'))

    return render_template('aggiungi_prenotazione.html')

def verifica_sovrapposizione_orari(giorno, ora_inizio, ora_fine):
    ora_inizio_obj = datetime.strptime(ora_inizio, '%H:%M').time()

    ora_fine_obj = datetime.strptime(ora_fine, '%H:%M').time()

    prenotazioni = Prenotazione.query.filter(
        (Prenotazione.giorno == giorno)
    ).all()

    for prenotazione in prenotazioni:
        pren_ora_inizio_obj = datetime.strptime(prenotazione.ora_inizio, '%H:%M').time()
        pren_ora_fine_obj = datetime.strptime(prenotazione.ora_fine, '%H:%M').time()

        if (ora_inizio_obj >= pren_ora_inizio_obj and ora_inizio_obj < pren_ora_fine_obj) or \
           (ora_fine_obj > pren_ora_inizio_obj and ora_fine_obj <= pren_ora_fine_obj):
            return True

    return False

@app.route('/prenotazione_esistente', methods=['GET'])
def prenotazione_esistente():
    prenotazioni = Prenotazione.query.order_by(Prenotazione.timestamp).all()
    return render_template('prenotazione_esistente.html', prenotazioni=prenotazioni, nomelab=nomelab)

@app.route('/verifica_password', methods=['GET', 'POST'])
def verifica_password():
    if request.method == 'POST':
        password_inserita = request.form['password']

        if password_inserita == admin_token:

            session['accesso_consentito'] = True
            message = Message("New login detected", sender="hello@aulabook.com", recipients=[indirizzo_responsabile]) #ENGTEXT

            message.html = render_template('email_login.html', nomelab=nomelab, responsabile=responsabile, url=url)
            
            mail.send(message)
            return redirect('/visualizza')
        else:
            flash('Wrong admin token', 'danger') #ENGTEXT
    return render_template('password.html')

@app.route('/logout')
def logout():
    session.pop('accesso_consentito', None)
    return redirect('/')

@app.route('/visualizza', methods=['GET'])
def visualizza_prenotazioni():
    if 'accesso_consentito' in session and session['accesso_consentito']:
        
        prenotazioni = Prenotazione.query.order_by(Prenotazione.giorno).all()
        return render_template('visualizza.html', prenotazioni=prenotazioni)
    else:

        return redirect('/verifica_password')

@app.route('/registro_pubblico', methods=['GET'])
def registro_pubblico_prenotazioni():
    prenotazioni = Prenotazione.query.order_by(Prenotazione.timestamp).all()
    return render_template('registro_pubblico.html', prenotazioni=prenotazioni)

@app.route('/recupera_prenotazione', methods=['GET', 'POST'])
def recupera_prenotazione():
    if request.method == 'POST':
        codice_identificativo = request.form['codice_identificativo']

        prenotazione = Prenotazione.query.filter_by(codice_identificativo=codice_identificativo).first()

        return render_template('recupera_prenotazione.html', prenotazione=prenotazione)

    return render_template('recupera_prenotazione.html')

@app.route('/elimina_prenotazione', methods=['POST'])
def elimina_prenotazione():
    if request.method == 'POST':
        id_prenotazione = request.form.get('id_prenotazione')
        prenotazione = Prenotazione.query.filter_by(id=id_prenotazione).first()

        if prenotazione:

            codice_identificativo=prenotazione.codice_identificativo
            nome=prenotazione.nome
            cognome=prenotazione.cognome
            email=prenotazione.email
            classe=prenotazione.classe
            ora_inizio=prenotazione.ora_inizio
            ora_fine=prenotazione.ora_fine
            giorno=prenotazione.giorno
            descrizione=prenotazione.descrizione
            codice_identificativo=prenotazione.codice_identificativo
            docente_accompagnatore=prenotazione.docente_accompagnatore
            
            message = Message("Reservation cancelled", sender="hello@aulabook.com", recipients=[email]) #ENGTEXT
            message.html = render_template('email_annullata.html', nome=nome, cognome=cognome, nomelab=nomelab,
                                giorno=giorno, classe=classe, docente_accompagnatore=docente_accompagnatore, descrizione=descrizione,
                                ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile)
            
            mail.send(message)
        

            username = "lab"+prenotazione.codice_identificativo

            command = """dsrm "cn={},ou={},dc={},dc={}" -noprompt""".format(username, ou, dc, dc2)
            unschedule = f'schtasks /delete /tn DisabilitaUtente{username} /f'  
            
            r = winsession.run_cmd(command)
            r2 = winsession.run_cmd(unschedule)

            print(r.status_code)
            print(r.std_out)
            print(r.std_err)
            
            r_status = r.status_code
            r_stdout = r.std_out
            r_stderr = r.std_err

            print(r2.status_code)
            print(r2.std_out)
            print(r2.std_err)
            
            r2_status = r2.status_code
            r2_stdout = r2.std_out
            r2_stderr = r2.std_err
            
            messageresponsabile = Message("Reservation cancelled", sender="hello@aulabook.com", recipients=[indirizzo_responsabile, indirizzo_viceresponsabile]) #ENGTEXT
            messageresponsabile.html = render_template('email_annullata_responsabile.html', nome=nome, cognome=cognome, nomelab=nomelab,
                               giorno=giorno, classe=classe, docente_accompagnatore=docente_accompagnatore, descrizione=descrizione,
                               ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile, r_status=r_status, r_stdout=r_stdout, r_stderr=r_stderr, r2_status=r2_status, r2_stdout=r2_stdout, r2_stderr=r2_stderr)

            mail.send(messageresponsabile)
            
            db.session.delete(prenotazione)
            db.session.commit()
            return redirect(url_for('prenotazione_cancellata'))
        else:
            flash('La prenotazione non esiste.', 'danger')

    return redirect('/recupera_prenotazione')

@app.route('/prenotazione_confermata')
def prenotazione_confermata():
    return render_template('prenotazione_confermata.html', indirizzo_responsabile=indirizzo_responsabile)

@app.route('/regolamento')
def regolamento():
    return render_template('regolamento.html')

@app.route('/prenotazione_cancellata')
def prenotazione_cancellata():
    return render_template('prenotazione_cancellata.html', indirizzo_responsabile=indirizzo_responsabile)

@app.route('/segnalazione', methods=['GET', 'POST'])
def segnalazione():
    if request.method == 'POST':
        codice_identificativo = request.form['codice_identificativo']
        segnalazione_testo = request.form['segnalazione']

        prenotazione = Prenotazione.query.filter_by(codice_identificativo=codice_identificativo).first()

        if prenotazione:
            prenotazione.segnalazione = segnalazione_testo
            db.session.commit()
            flash('Segnalazione aggiunta con successo.', 'success')

            codice_identificativo=prenotazione.codice_identificativo
            nome=prenotazione.nome
            cognome=prenotazione.cognome
            email=prenotazione.email
            classe=prenotazione.classe
            ora_inizio=prenotazione.ora_inizio
            ora_fine=prenotazione.ora_fine
            giorno=prenotazione.giorno
            descrizione=prenotazione.descrizione
            codice_identificativo=prenotazione.codice_identificativo
            docente_accompagnatore=prenotazione.docente_accompagnatore
            segnalazione=prenotazione.segnalazione
            
            message = Message("You sent a report", sender="hello@aulabook.com", recipients=[email]) #ENGTEXT
            message.html = render_template('email_segnalazione.html', nome=nome, cognome=cognome, nomelab=nomelab,
                                giorno=giorno, classe=classe, docente_accompagnatore=docente_accompagnatore, descrizione=descrizione,
                                ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile, segnalazione=segnalazione)
            
            mail.send(message)
            
            
            messageresponsabile = Message("New report received", sender="hello@aulabook.com", recipients=[indirizzo_responsabile, indirizzo_viceresponsabile]) #ENGTEXT
            messageresponsabile.html = render_template('email_segnalazione_responsabile.html', nome=nome, cognome=cognome, nomelab=nomelab,
                                giorno=giorno, classe=classe, docente_accompagnatore=docente_accompagnatore, descrizione=descrizione,
                                ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile, segnalazione=segnalazione)
            
            mail.send(messageresponsabile)
            

        else:
            flash('La prenotazione con il codice identificativo specificato non esiste.', 'danger')

    return render_template('segnalazione.html')

@app.route('/carica_prenotazione', methods=['GET'])
def carica_prenotazione():
    codice_identificativo = request.args.get('codice_identificativo')

    prenotazione = Prenotazione.query.filter_by(codice_identificativo=codice_identificativo).first()

    if prenotazione:
        prenotazione_data = {
            'nome': prenotazione.nome,
            'cognome': prenotazione.cognome,
            'email': prenotazione.email,
            'classe': prenotazione.classe,
            'segnalazione': prenotazione.segnalazione,
        }
        return jsonify(prenotazione_data)
    else:
        return jsonify({'error': 'Prenotazione non trovata'}), 404

if __name__ == '__main__':
    serve(app, host='0.0.0.0')
