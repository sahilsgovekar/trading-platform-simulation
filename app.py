from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify  
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from flask_bcrypt import Bcrypt
import requests
import sqlite3
import xmltodict
import yfinance as yf
from yahoo_fin import stock_info as si
import plotly.graph_objs as go
import plotly.io as pio
import datetime
import re
import time

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trading.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "ohyesabhi"
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
    transaction_type = db.Column(db.String(4), nullable=False)  # 'BUY' or 'SELL'
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# @app.before_first_request
# def create_tables():
#     db.create_all()

def validate_password(password):
    # Password must be at least 8 characters long and contain at least:
    # one uppercase letter, one lowercase letter, one number, and one special character
    if (len(password) < 8 or
        not re.search(r"[A-Z]", password) or
        not re.search(r"[a-z]", password) or
        not re.search(r"\d", password) or
        not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)):
        return False
    return True


@app.route("/")
def landing_route():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Basic username validation
        if len(username) < 4:
            flash("Username must be at least 4 characters long.", "danger")
            return redirect(url_for("signup"))

        # Password validation
        if not validate_password(password):
            flash("Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, one number, and one special character.", "danger")
            return redirect(url_for("signup"))

        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists. Please choose a different one.", "danger")
            return redirect(url_for("signup"))

        # If validations pass, hash the password and create the user
        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("trade"))
        else:
            flash("Please check username and password", "Login Unsuccessful")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# Home route
@app.route("/home")
def home():
    return render_template("home.html")


# News route
@app.route("/news")
def news():
    news_data = fetch_latest_news()
    return render_template("news.html", news_data=news_data)


# Predefined list of stock symbols for the dropdown
STOCK_SYMBOLS = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "FB",
    "TSLA",
    "BRK-A",
    "JNJ",
    "V",
    "WMT",
    "JPM",
    "MA",
    "PG",
    "UNH",
    "NVDA",
    "HD",
    "DIS",
    "PYPL",
    "VZ",
    "ADBE",
]


@app.route("/trade")
def trade():
    return render_template("trade.html", symbols=STOCK_SYMBOLS)


@app.route("/get_stock_price", methods=["POST"])
@login_required
def get_stock_price():
    stock_symbol = request.form["symbol"]
    stock = yf.Ticker(stock_symbol)
    stock_info = stock.info
    stock_price = stock_info.get("regularMarketPrice")
    if stock_price is None:
        stock_price = stock.history(period="1d")["Close"].iloc[-1]

    # Fetch intraday data for the stock
    now = datetime.datetime.now()
    start = now - datetime.timedelta(hours=6)
    intraday_data = stock.history(start=start, end=now, interval="5m")

    graph_html = ""
    if not intraday_data.empty:
        # Determine color based on price movement
        try:
            price_change = intraday_data["Close"].iloc[-1] - intraday_data["Open"].iloc[0]
            line_color = "green" if price_change > 0 else "red"

            # Create plotly graph
            # Create plotly graph
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=intraday_data.index, y=intraday_data["Close"], mode='lines', line=dict(color=line_color)))
            fig.update_layout(
                title=f"{stock_symbol} Performance (Last 6 Hours)",
                xaxis_title="Time",
                yaxis_title="Price",
                template="plotly_dark",
                paper_bgcolor="rgba(0, 0, 0, 0)",
                plot_bgcolor="#111",
                font=dict(color="#fff"),
                xaxis=dict(
                    gridcolor="#444",
                    linecolor="#444"
                ),
                yaxis=dict(
                    gridcolor="#444",
                    linecolor="#444"
                )
            )

            graph_html = pio.to_html(fig, full_html=False)
        except IndexError:
            flash("Error fetching intraday data for the stock. Displaying fallback data.")
    else:
        # Fetch historical data as a fallback
        fallback_data = stock.history(period="5d", interval="1h")
        if not fallback_data.empty:
            try:
                price_change = fallback_data["Close"].iloc[-1] - fallback_data["Open"].iloc[0]
                line_color = "green" if price_change > 0 else "red"

                # Create plotly graph with fallback data
                # Create plotly graph with fallback data
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=fallback_data.index, y=fallback_data["Close"], mode='lines', line=dict(color=line_color)))
                fig.update_layout(
                    title=f"{stock_symbol} Performance (Last 5 Days)",
                    xaxis_title="Time",
                    yaxis_title="Price",
                    template="plotly_dark",
                    paper_bgcolor="rgba(0, 0, 0, 0)",
                    plot_bgcolor="#111",
                    font=dict(color="#fff"),
                    xaxis=dict(
                        gridcolor="#444",
                        linecolor="#444"
                    ),
                    yaxis=dict(
                        gridcolor="#444",
                        linecolor="#444"
                    )
                )
                graph_html = pio.to_html(fig, full_html=False)
            except IndexError:
                flash("Error fetching fallback data for the stock. Please try again later.")
        else:
            flash("No historical data available for the selected stock.")

    transactions = StockTransaction.query.filter_by(
        stock_symbol=stock_symbol, user_id=current_user.id
    ).all()
    total_quantity = sum(
        t.quantity for t in transactions if t.transaction_type == "BUY"
    ) - sum(t.quantity for t in transactions if t.transaction_type == "SELL")

    return render_template(
        "result.html",
        symbol=stock_symbol,
        price=stock_price,
        funds=current_user.funds,
        quantity=total_quantity,
        graph_html=graph_html
    )




@app.route("/buy_stock", methods=["POST"])
@login_required
def buy_stock():
    stock_symbol = request.form["symbol"]
    price = float(request.form["price"])
    quantity = int(request.form["quantity"])

    total_cost = price * quantity

    if current_user.funds >= total_cost:
        current_user.funds -= total_cost
        transaction = StockTransaction(
            stock_symbol=stock_symbol,
            quantity=quantity,
            price=price,
            transaction_type="BUY",
            user_id=current_user.id,
        )
        db.session.add(transaction)
        db.session.commit()
        flash("Stock bought successfully!", "success")
    else:
        flash("Insufficient funds.", "danger")

    return redirect(url_for("get_stock_price"), code=307)


@app.route("/sell_stock", methods=["POST"])
@login_required
def sell_stock():
    stock_symbol = request.form["symbol"]
    price = float(request.form["price"])
    quantity = int(request.form["quantity"])

    transactions = StockTransaction.query.filter_by(
        stock_symbol=stock_symbol, user_id=current_user.id
    ).all()
    total_quantity = sum(
        t.quantity for t in transactions if t.transaction_type == "BUY"
    ) - sum(t.quantity for t in transactions if t.transaction_type == "SELL")

    if total_quantity >= quantity:
        current_user.funds += price * quantity
        transaction = StockTransaction(
            stock_symbol=stock_symbol,
            quantity=quantity,
            price=price,
            transaction_type="SELL",
            user_id=current_user.id,
        )
        db.session.add(transaction)
        db.session.commit()
        flash("Stock sold successfully!", "success")
    else:
        flash("Insufficient stock quantity.", "danger")

    return redirect(url_for("get_stock_price"), code=307)


def fetch_latest_news():
    url = "https://finance.yahoo.com/rss/topstories"  # Example URL; replace with actual Yahoo Finance API endpoint
    response = requests.get(url)
    if response.status_code == 200:
        try:
            # Parse the RSS feed
            news_data = xmltodict.parse(response.content)
            return news_data["rss"]["channel"]["item"]  # Extract relevant news items
        except Exception as e:
            return [{"title": "Error", "description": str(e), "link": ""}]
    else:
        return [{"title": "Error", "description": "Failed to fetch news", "link": ""}]


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/portfolio")
@login_required
def portfolio():
    transactions = StockTransaction.query.filter_by(user_id=current_user.id).all()
    portfolio = {}

    for transaction in transactions:
        if transaction.stock_symbol not in portfolio:
            portfolio[transaction.stock_symbol] = {"quantity": 0, "total_value": 0}

        if transaction.transaction_type == "BUY":
            portfolio[transaction.stock_symbol]["quantity"] += transaction.quantity
            portfolio[transaction.stock_symbol]["total_value"] += (
                transaction.price * transaction.quantity
            )
        elif transaction.transaction_type == "SELL":
            portfolio[transaction.stock_symbol]["quantity"] -= transaction.quantity
            portfolio[transaction.stock_symbol]["total_value"] -= (
                transaction.price * transaction.quantity
            )

    total_portfolio_value = sum(stock["total_value"] for stock in portfolio.values())
    return render_template(
        "portfolio.html",
        portfolio=portfolio,
        total_portfolio_value=total_portfolio_value,
    )


def get_market_data():
    gainers = si.get_day_gainers()
    losers = si.get_day_losers()

    # Inspecting the first row of gainers and losers to understand the data structure
    print("Gainers Data Example:", gainers.head(1).to_dict("records"))
    print("Losers Data Example:", losers.head(1).to_dict("records"))

    top_gainers = gainers.head(5).to_dict("records")
    top_losers = losers.head(5).to_dict("records")

    return top_gainers, top_losers


@app.route("/market/trends")
def index():
    gainers, losers = get_market_data()
    return render_template("markettrends.html", gainers=gainers, losers=losers)


@app.route("/predict", methods=["POST"])
@login_required
def predict():
    stock_symbol = request.form["symbol"]
    return redirect(f"http://localhost:8501/?stock_symbol={stock_symbol}")


# Admin panel
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == "admin" and password == "admin@123":
            session["admin_logged_in"] = True
            flash("Admin login successful!", "success")
            return redirect(url_for("admin"))
        else:
            flash("Login Unsuccessful. Please check username and password", "danger")
    return render_template("admin_login.html")


@app.route("/admin_logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Admin has been logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    users = User.query.all()
    return render_template("admin.html", users=users)


@app.route("/admin/delete_user/<int:user_id>")
def delete_user(user_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully!", "success")
    return redirect(url_for("admin"))


@app.route("/admin/view_portfolio/<int:user_id>")
def admin_view_portfolio(user_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    user = User.query.get_or_404(user_id)
    transactions = StockTransaction.query.filter_by(user_id=user.id).all()
    portfolio = {}

    for transaction in transactions:
        if transaction.stock_symbol not in portfolio:
            portfolio[transaction.stock_symbol] = {"quantity": 0, "total_value": 0}

        if transaction.transaction_type == "BUY":
            portfolio[transaction.stock_symbol]["quantity"] += transaction.quantity
            portfolio[transaction.stock_symbol]["total_value"] += (
                transaction.price * transaction.quantity
            )
        elif transaction.transaction_type == "SELL":
            portfolio[transaction.stock_symbol]["quantity"] -= transaction.quantity
            portfolio[transaction.stock_symbol]["total_value"] -= (
                transaction.price * transaction.quantity
            )

    total_portfolio_value = sum(stock["total_value"] for stock in portfolio.values())
    return render_template(
        "portfolio.html",
        portfolio=portfolio,
        total_portfolio_value=total_portfolio_value,
        user=user,
    )


if __name__ == "__main__":
    app.run(debug=True)
