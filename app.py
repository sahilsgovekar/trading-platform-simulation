from flask import Flask, jsonify, request, render_template, redirect, url_for
import requests
import sqlite3
import xmltodict
import yfinance as yf
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trading.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    funds = db.Column(db.Float, nullable=False, default=10000)

class StockTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_symbol = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(4), nullable=False) # 'BUY' or 'SELL'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@app.before_first_request
def create_tables():
    db.create_all()
    if not User.query.first():
        user = User(funds=10000)
        db.session.add(user)
        db.session.commit()

# Home route
@app.route('/')
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
def index():
    return render_template('trade.html', symbols=STOCK_SYMBOLS)

@app.route('/get_stock_price', methods=['POST'])
def get_stock_price():
    stock_symbol = request.form['symbol']
    stock = yf.Ticker(stock_symbol)
    stock_info = stock.info
    stock_price = stock_info.get('regularMarketPrice')
    if stock_price is None:
        stock_price = stock.history(period="1d")['Close'].iloc[-1]
    
    user = User.query.first()
    transactions = StockTransaction.query.filter_by(stock_symbol=stock_symbol, user_id=user.id).all()
    total_quantity = sum(t.quantity for t in transactions if t.transaction_type == 'BUY') - sum(t.quantity for t in transactions if t.transaction_type == 'SELL')

    return render_template('result.html', symbol=stock_symbol, price=stock_price, funds=user.funds, quantity=total_quantity)

@app.route('/buy_stock', methods=['POST'])
def buy_stock():
    stock_symbol = request.form['symbol']
    price = float(request.form['price'])
    quantity = int(request.form['quantity'])
    
    user = User.query.first()
    total_cost = price * quantity
    
    if user.funds >= total_cost:
        user.funds -= total_cost
        transaction = StockTransaction(stock_symbol=stock_symbol, quantity=quantity, price=price, transaction_type='BUY', user_id=user.id)
        db.session.add(transaction)
        db.session.commit()

    return redirect(url_for('get_stock_price'), code=307)

@app.route('/sell_stock', methods=['POST'])
def sell_stock():
    stock_symbol = request.form['symbol']
    price = float(request.form['price'])
    quantity = int(request.form['quantity'])
    
    user = User.query.first()
    transactions = StockTransaction.query.filter_by(stock_symbol=stock_symbol, user_id=user.id).all()
    total_quantity = sum(t.quantity for t in transactions if t.transaction_type == 'BUY') - sum(t.quantity for t in transactions if t.transaction_type == 'SELL')

    if total_quantity >= quantity:
        user.funds += price * quantity
        transaction = StockTransaction(stock_symbol=stock_symbol, quantity=quantity, price=price, transaction_type='SELL', user_id=user.id)
        db.session.add(transaction)
        db.session.commit()

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


if __name__ == '__main__':
    app.run(debug=True)
