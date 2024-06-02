from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import requests
import sqlite3
import xmltodict
import yfinance as yf

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trading.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'ohyesabhi'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
bcrypt = Bcrypt(app)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    funds = db.Column(db.Float, nullable=False, default=10000)

class StockTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_symbol = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(4), nullable=False) # 'BUY' or 'SELL'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_first_request
def create_tables():
    db.create_all()

@app.route("/")
def landing_route():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! Login please', 'success')
        return redirect(url_for('trade'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('trade'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# Home route
@app.route('/home')
def home():
    return render_template('home.html')

# News route
@app.route('/news')
def news():
    news_data = fetch_latest_news()
    return render_template('news.html', news_data=news_data)

# Predefined list of stock symbols for the dropdown
STOCK_SYMBOLS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'FB', 'TSLA', 'BRK-A', 'JNJ', 'V', 'WMT', 
    'JPM', 'MA', 'PG', 'UNH', 'NVDA', 'HD', 'DIS', 'PYPL', 'VZ', 'ADBE'
]

@app.route('/trade')
def trade():
    return render_template('trade.html', symbols=STOCK_SYMBOLS)

@app.route('/get_stock_price', methods=['POST'])
@login_required
def get_stock_price():
    stock_symbol = request.form['symbol']
    stock = yf.Ticker(stock_symbol)
    stock_info = stock.info
    stock_price = stock_info.get('regularMarketPrice')
    if stock_price is None:
        stock_price = stock.history(period="1d")['Close'].iloc[-1]
    
    transactions = StockTransaction.query.filter_by(stock_symbol=stock_symbol, user_id=current_user.id).all()
    total_quantity = sum(t.quantity for t in transactions if t.transaction_type == 'BUY') - sum(t.quantity for t in transactions if t.transaction_type == 'SELL')

    return render_template('result.html', symbol=stock_symbol, price=stock_price, funds=current_user.funds, quantity=total_quantity)

@app.route('/buy_stock', methods=['POST'])
@login_required
def buy_stock():
    stock_symbol = request.form['symbol']
    price = float(request.form['price'])
    quantity = int(request.form['quantity'])
    
    total_cost = price * quantity
    
    if current_user.funds >= total_cost:
        current_user.funds -= total_cost
        transaction = StockTransaction(stock_symbol=stock_symbol, quantity=quantity, price=price, transaction_type='BUY', user_id=current_user.id)
        db.session.add(transaction)
        db.session.commit()
        flash('Stock bought successfully!', 'success')
    else:
        flash('Insufficient funds.', 'danger')

    return redirect(url_for('get_stock_price'), code=307)

@app.route('/sell_stock', methods=['POST'])
@login_required
def sell_stock():
    stock_symbol = request.form['symbol']
    price = float(request.form['price'])
    quantity = int(request.form['quantity'])
    
    transactions = StockTransaction.query.filter_by(stock_symbol=stock_symbol, user_id=current_user.id).all()
    total_quantity = sum(t.quantity for t in transactions if t.transaction_type == 'BUY') - sum(t.quantity for t in transactions if t.transaction_type == 'SELL')

    if total_quantity >= quantity:
        current_user.funds += price * quantity
        transaction = StockTransaction(stock_symbol=stock_symbol, quantity=quantity, price=price, transaction_type='SELL', user_id=current_user.id)
        db.session.add(transaction)
        db.session.commit()
        flash('Stock sold successfully!', 'success')
    else:
        flash('Insufficient stock quantity.', 'danger')

    return redirect(url_for('get_stock_price'), code=307)

def fetch_latest_news():
    url = "https://finance.yahoo.com/rss/topstories"  # Example URL; replace with actual Yahoo Finance API endpoint
    response = requests.get(url)
    if response.status_code == 200:
        try:
            # Parse the RSS feed
            news_data = xmltodict.parse(response.content)
            return news_data['rss']['channel']['item']  # Extract relevant news items
        except Exception as e:
            return [{"title": "Error", "description": str(e), "link": ""}]
    else:
        return [{"title": "Error", "description": "Failed to fetch news", "link": ""}]

@app.route("/about")
def about():
    return render_template("about.html")

@app.route('/portfolio')
@login_required
def portfolio():
    transactions = StockTransaction.query.filter_by(user_id=current_user.id).all()
    portfolio = {}
    
    for transaction in transactions:
        if transaction.stock_symbol not in portfolio:
            portfolio[transaction.stock_symbol] = {'quantity': 0, 'total_value': 0}
        
        if transaction.transaction_type == 'BUY':
            portfolio[transaction.stock_symbol]['quantity'] += transaction.quantity
            portfolio[transaction.stock_symbol]['total_value'] += transaction.price * transaction.quantity
        elif transaction.transaction_type == 'SELL':
            portfolio[transaction.stock_symbol]['quantity'] -= transaction.quantity
            portfolio[transaction.stock_symbol]['total_value'] -= transaction.price * transaction.quantity

    total_portfolio_value = sum(stock['total_value'] for stock in portfolio.values())
    return render_template('portfolio.html', portfolio=portfolio, total_portfolio_value=total_portfolio_value)


if __name__ == '__main__':
    app.run(debug=True)
