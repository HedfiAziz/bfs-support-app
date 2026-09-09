import os
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cle_secrete_bfs_2026')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'adminbfs2026')

# Dossier d'enregistrement des pièces jointes
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Connexion Neon PostgreSQL
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Options du moteur SQLAlchemy contre la déconnexion SSL inattendue
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    entreprise = db.Column(db.String(150), nullable=False)
    nom_prenom = db.Column(db.String(150), nullable=False)
    telephone = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    module = db.Column(db.String(100), nullable=False)
    urgence = db.Column(db.String(50), nullable=False)
    sujet = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    fichier_joint = db.Column(db.String(255), nullable=True)
    temps_estime = db.Column(db.Float, default=0.0)
    statut = db.Column(db.String(50), default="Nouveau")
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

# Migration automatique PostgreSQL au démarrage
with app.app_context():
    db.create_all()
    try:
        db.session.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS fichier_joint VARCHAR(255);"))
        db.session.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS temps_estime FLOAT DEFAULT 0.0;"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    if request.method == 'POST':
        filename = None
        if 'fichier_joint' in request.files:
            file = request.files['fichier_joint']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        nouveau_ticket = Ticket(
            entreprise=request.form.get('entreprise', '').strip(),
            nom_prenom=request.form.get('nom_prenom', '').strip(),
            telephone=request.form.get('telephone', '').strip(),
            email=request.form.get('email', '').strip(),
            module=request.form.get('module', '').strip(),
            urgence=request.form.get('urgence', '').strip(),
            sujet=request.form.get('sujet', '').strip(),
            description=request.form.get('description', '').strip(),
            fichier_joint=filename
        )
        db.session.add(nouveau_ticket)
        db.session.commit()

        return render_template('success.html', ticket=nouveau_ticket)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Mot de passe incorrect."
    return render_template('admin_login.html', error=error)

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    tickets = Ticket.query.order_by(Ticket.date_creation.desc()).all()
    
    stats = {
        'total': len(tickets),
        'nouveaux': sum(1 for t in tickets if t.statut == 'Nouveau'),
        'en_cours': sum(1 for t in tickets if t.statut in ['En cours', 'En Cours']),
        'critiques': sum(1 for t in tickets if t.urgence == 'Critique'),
        'resolus': sum(1 for t in tickets if t.statut in ['Résolu', 'Clôturé', 'Cloture', 'Resolue'])
    }

    return render_template('admin.html', tickets=tickets, stats=stats)

@app.route('/admin/update_status/<int:ticket_id>', methods=['POST'])
def update_status(ticket_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    ticket = Ticket.query.get_or_404(ticket_id)
    nouveau_statut = request.form.get('statut')
    if nouveau_statut:
        ticket.statut = nouveau_statut
        db.session.commit()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_temps/<int:ticket_id>', methods=['POST'])
def update_temps(ticket_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    ticket = Ticket.query.get_or_404(ticket_id)
    temps_val = request.form.get('temps_estime')
    if temps_val is not None:
        try:
            ticket.temps_estime = float(temps_val)
            db.session.commit()
        except ValueError:
            pass
            
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:ticket_id>', methods=['POST'])
def delete_ticket(ticket_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if ticket.fichier_joint:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], ticket.fichier_joint)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

    db.session.delete(ticket)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export_csv')
def export_csv():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    tickets = Ticket.query.order_by(Ticket.date_creation.desc()).all()
    
    def generate():
        data = StringIO()
        writer = csv.writer(data)
        yield '\ufeff'
        writer.writerow(['ID', 'Date Creation', 'Entreprise', 'Demandeur', 'Telephone', 'Email', 'Module', 'Urgence', 'Temps Passe (h)', 'Sujet', 'Description', 'Fichier Joint', 'Statut'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        
        for t in tickets:
            writer.writerow([
                t.id, 
                t.date_creation.strftime('%d/%m/%Y %H:%M') if t.date_creation else '',
                t.entreprise,
                t.nom_prenom,
                t.telephone,
                t.email,
                t.module,
                t.urgence,
                t.temps_estime or 0,
                t.sujet,
                t.description,
                t.fichier_joint or '',
                t.statut
            ])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    return Response(
        generate(), 
        mimetype='text/csv; charset=utf-8', 
        headers={"Content-Disposition": "attachment;filename=tickets_bfs_solutions.csv"}
    )

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(debug=True)