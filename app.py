import os
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Charger les variables du fichier .env
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cle_secrete_bfs_2026')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'adminbfs2026')

# Connection Neon PostgreSQL
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modèle de la table dans Neon
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
    statut = db.Column(db.String(50), default="Nouveau")
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- ROUTES CLIENT ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    if request.method == 'POST':
        nouveau_ticket = Ticket(
            entreprise=request.form.get('entreprise'),
            nom_prenom=request.form.get('nom_prenom'),
            telephone=request.form.get('telephone'),
            email=request.form.get('email'),
            module=request.form.get('module'),
            urgence=request.form.get('urgence'),
            sujet=request.form.get('sujet'),
            description=request.form.get('description')
        )
        db.session.add(nouveau_ticket)
        db.session.commit()

        return render_template('success.html', ticket=nouveau_ticket)

# --- ROUTES ADMIN ---
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
    
    # Statistiques KPI
    total_tickets = len(tickets)
    nouveaux_tickets = sum(1 for t in tickets if t.statut == 'Nouveau')
    critiques_tickets = sum(1 for t in tickets if t.urgence == 'Critique')
    resolus_tickets = sum(1 for t in tickets if t.statut == 'Résolu')

    stats = {
        'total': total_tickets,
        'nouveaux': nouveaux_tickets,
        'critiques': critiques_tickets,
        'resolus': resolus_tickets
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

@app.route('/admin/delete/<int:ticket_id>', methods=['POST'])
def delete_ticket(ticket_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    ticket = Ticket.query.get_or_404(ticket_id)
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
        writer.writerow(['ID', 'Date Creation', 'Entreprise', 'Demandeur', 'Telephone', 'Email', 'Module', 'Urgence', 'Sujet', 'Description', 'Statut'])
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
                t.sujet,
                t.description,
                t.statut
            ])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=tickets_bfs_solutions.csv"})

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/robots.txt')
def robots():
    content = "User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: https://bfs-support-app.onrender.com/sitemap.xml"
    return content, 200, {'Content-Type': 'text/plain'}

@app.route('/sitemap.xml')
def sitemap():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://bfs-support-app.onrender.com/</loc>
    <priority>1.00</priority>
  </url>
</urlset>"""
    return content, 200, {'Content-Type': 'application/xml'}

if __name__ == '__main__':
    app.run(debug=True)
