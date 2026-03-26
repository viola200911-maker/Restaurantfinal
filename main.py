import os
import secrets
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory

from flask_login import login_required, current_user, login_user, logout_user, LoginManager 
from flask_session import Session as FlaskSession 

from database import *
from database import (
    cancel_reservation as cancel_res_db,
    add_to_cart as add_to_cart_db,
    remove_from_cart as remove_from_cart_db,
    clear_cart as clear_cart_db,
    Update_order_status,
    Session as DBSession,
    Users,
    get_user_by_email,
    update_user_password,
    update_avatar_image
)

from functools import wraps

from werkzeug.utils import secure_filename

from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv(
    'FLASK_SECRET_KEY', 'dev-only-change-FLASK_SECRET_KEY-for-production'
)

# Session configuration - use client-side session for simplicity
# app.config['SESSION_TYPE'] = 'filesystem'
# app.config['SESSION_PERMANENT'] = False
# app.config['SESSION_USE_SIGNER'] = True
# app.config['SESSION_KEY_PREFIX'] = 'restaurant:'
# app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session')

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  
app.config['MAX_FORM_MEMORY_SIZE'] = 1024 * 1024  
app.config['MAX_FORM_PARTS'] = 500

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() in ['true', '1']
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

PASSWORD_RESET_EXPIRY = 3600

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize Flask-Session - DISABLED for now
# import os
# if not os.path.exists(app.config['SESSION_FILE_DIR']):
#     os.makedirs(app.config['SESSION_FILE_DIR'])
# sess = FlaskSession(app)

csrf = CSRFProtect(app)

def generate_reset_token():
    return secrets.token_urlsafe(32)

def send_password_reset_email(user_email, reset_token):
    try:
        reset_link = url_for('reset_password', token=reset_token, _external=True)
        
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = user_email
        msg['Subject'] = 'Відновлення паролю - Історичний Ресторан'
        
        body = f"""
        <html>
        <body>
            <h2>Відновлення паролю</h2>
            <p>Ви запросили відновлення паролю для вашого акаунту в Історичному Ресторані.</p>
            <p>Перейдіть за посиланням нижче, щоб встановити новий пароль:</p>
            <p><a href="{reset_link}" style="background-color: #8b6f47; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Відновити пароль</a></p>
            <p>Або скопіюйте це посилання в браузер:</p>
            <p>{reset_link}</p>
            <p>Це посилання дійсне протягом 1 години.</p>
            <p>Якщо ви не запитували відновлення паролю, проігноруйте цей лист.</p>
            <hr>
            <p>З повагою,<br>Команда Історичного Ресторану</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.starttls()
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.sendmail(app.config['MAIL_DEFAULT_SENDER'], user_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def store_reset_token(email, token):
    reset_data = {
        'token': token,
        'email': email,
        'timestamp': datetime.now().timestamp()
    }
    session['password_reset'] = reset_data

def validate_reset_token(token):
    reset_data = session.get('password_reset')
    if not reset_data:
        return None
    
    if reset_data['token'] != token:
        return None
    
    timestamp = reset_data['timestamp']
    if datetime.now().timestamp() - timestamp > PASSWORD_RESET_EXPIRY:
        session.pop('password_reset', None)
        return None
    
    return reset_data['email']

def clear_reset_token():
    session.pop('password_reset', None)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        app.static_folder,
        'favicon.svg',
        mimetype='image/svg+xml',
    )


@login_manager.user_loader
def load_user(user_id):
    return search_user(user_id)

@app.route('/')
def home():
    return render_template('about_us.html')

@app.route('/home/')
@login_required
def home_page():
    return render_template('home.html')

@app.route('/about-us/')
def about_us():
    return render_template('about_us.html')

@app.route('/menu/')
@login_required
def menu():
    search = request.args.get('search')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    max_cal = request.args.get('max_cal')
    min_cal = request.args.get('min_cal')

    dishes = get_all_menu_items()

    if search:
        dishes = search_menu_items(search)
    
    if min_price or max_price or max_cal or min_cal:
        try:
            min_price_val = float(min_price) if min_price else None
            max_price_val = float(max_price) if max_price else None
            min_cal_val = int(min_cal) if min_cal else None
            max_cal_val = int(max_cal) if max_cal else None
            
            dishes = filter_menu_items(
                min_price=min_price_val,
                max_price=max_price_val,
                min_cal=min_cal_val,
                max_cal=max_cal_val
            )
        except ValueError:
            flash("Невірні значення для фільтрів", "danger")
            dishes = get_all_menu_items()

    return render_template('menu.html', dishes=dishes)

@app.route('/dish/<int:dish_id>/')
@login_required
def dish(dish_id):
    dish = get_menu_item_by_id(dish_id)
    if not dish:
        flash("Страву не знайдено", "danger")
        return redirect(url_for('menu'))
    if not dish.active:
        flash("Ця страва тимчасово недоступна", "warning")
        return redirect(url_for('menu'))
    return render_template('dish.html', dish=dish)

@app.route('/add-to-cart/<int:dish_id>/', methods=['POST'])
@login_required
def add_to_cart(dish_id):
    dish = get_menu_item_by_id(dish_id)
    if not dish:
        flash("Страву не знайдено", "danger")
        return redirect(url_for('menu'))
    if not dish.active:
        flash("Ця страва тимчасово недоступна", "warning")
        return redirect(url_for('menu'))
    
    # Simple cart handling
    if 'cart' not in session:
        session['cart'] = {}
    
    cart = session['cart']
    if str(dish_id) in cart:
        cart[str(dish_id)] += 1
    else:
        cart[str(dish_id)] = 1
    
    session['cart'] = cart
    flash(f"{dish.name} додано в кошик", "success")
    return redirect(url_for('cart'))

@app.route('/decrease-from-cart/<int:dish_id>/', methods=['POST'])
@login_required
def decrease_from_cart(dish_id):
    cart = session.get('cart', {})
    if str(dish_id) in cart:
        if cart[str(dish_id)] > 1:
            cart[str(dish_id)] -= 1
        else:
            del cart[str(dish_id)]
        session['cart'] = cart
        flash("Кількість зменшено", "success")
    return redirect(url_for('cart'))

@app.route('/delete-from-cart/<int:dish_id>/', methods=['POST'])
@login_required
def delete_from_cart(dish_id):
    cart = session.get('cart', {})
    if str(dish_id) in cart:
        del cart[str(dish_id)]
        session['cart'] = cart
        flash("Страву видалено з кошика", "success")
    return redirect(url_for('cart'))

@app.route('/cart/')
@login_required
def cart():
    cart = session.get('cart', {})
    dishes = []
    
    for dish_id, qty in cart.items():
        try:
            dish = get_menu_item_by_id(int(dish_id))
            if dish and dish.active:
                dishes.append({'dish': dish, 'quantity': qty})
        except (ValueError, TypeError):
            continue
    
    return render_template('cart.html', cart_items=dishes)

@app.route('/checkout/')
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash("Кошик порожній", "warning")
        return redirect(url_for('menu'))
    return render_template('checkout.html')

@app.route('/confirm-order/', methods=['POST'])
@login_required
def confirm_order():
    cart = session.get('cart', {})
    if not cart:
        flash("Кошик порожній", "warning")
        return redirect(url_for('cart'))
    
    note = request.form.get('note', '').strip()
    
    try:
        result = create_order(current_user.id, cart, note)
        if isinstance(result, tuple):
            # Clear cart after successful order
            session['cart'] = {}
            flash(result[0], "success")
            return redirect(url_for('orders'))
        else:
            flash(result, "danger")
            return redirect(url_for('checkout'))
    except Exception as e:
        flash(f"Помилка при створенні замовлення: {str(e)}", "danger")
        return redirect(url_for('checkout'))

@app.route('/orders/')
@login_required
def orders():
    try:
        user_orders = get_user_orders(current_user.id)
        return render_template('orders.html', orders=user_orders)
    except Exception as e:
        flash(f"Помилка при завантаженні замовлень: {str(e)}", "danger")
        return render_template('orders.html', orders=[])

@app.route('/order/<int:order_id>/')
@login_required
def order_details(order_id):
    try:
        order = get_order_details(order_id)

        if not order or order.user_id != current_user.id:
            flash("Ви не можете переглядати це замовлення", "danger")
            return redirect(url_for('orders'))

        return render_template('order_details.html', order=order)
    except Exception as e:
        flash(f"Помилка при завантаженні деталей замовлення: {str(e)}", "danger")
        return redirect(url_for('orders'))

@app.route('/tables/')
@login_required
def tables():
    tables = get_all_tables()
    return render_template('tables.html', tables=tables)

@app.route('/reservation/<int:table_id>/', methods=['GET', 'POST'])
@login_required
def reservation(table_id):
    table = get_table_by_id(table_id)  

    if not table:
        flash("Стіл не знайдено", "danger")
        return redirect(url_for('tables'))

    if request.method == 'POST':
        time_str = request.form.get('time')
        try:
            reservation_time = datetime.fromisoformat(time_str)
        except (ValueError, TypeError):
            flash("Невірний формат дати і часу", "danger")
            return render_template('reservation.html', table=table)
        
        if reservation_time <= datetime.now():
            flash("Бронювання має бути на майбутній час", "danger")
            return render_template('reservation.html', table=table)

        result = create_reservation(current_user.id, [table_id], reservation_time)

        if isinstance(result, tuple):
            flash(result[0], "success")
            return redirect(url_for('reservations'))
        else:
            flash(result, "danger")

    return render_template('reservation.html', table=table)

@app.route('/reservations/')
@login_required
def reservations():
    user_res = get_user_reservations(current_user.id)
    return render_template('reservations.html', reservations=user_res)

@app.route('/cancel-reservation/<int:reservation_id>/', methods=['POST'])
@login_required
def cancel_reservation(reservation_id):
    result = cancel_res_db(reservation_id, current_user.id)
    rl = result.lower()
    if "успішно" in rl or "скасовано" in rl:
        flash(result, "success")
    else:
        flash(result, "danger")
    return redirect(url_for('reservations'))

@app.route('/profile/')
@login_required
def profile():
    user = get_user_profile(current_user.id)
    return render_template('profile.html', user=user)

@app.route('/profile/edit/', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        new_username = request.form.get('nickname', '').strip()
        new_password = request.form.get('password', '').strip()

        if not new_username and not new_password:
            flash("Заповніть хоча б одне поле", "warning")
            return render_template('edit_profile.html')

        res = update_profile(
            current_user.id,
            new_username if new_username else None,
            new_password if new_password else None,
        )
        if "успішно" in res.lower():
            flash(res, 'success')
            return redirect(url_for('profile'))
        if res == "Нічого не змінено":
            flash(res, 'warning')
            return render_template('edit_profile.html')
        flash(res, 'danger')
        return render_template('edit_profile.html')

    return render_template('edit_profile.html')

@app.route('/profile/upload-avatar/', methods=['POST'])
@login_required
def upload_avatar():
    file = request.files.get('avatar')
    
    # Check if file was actually uploaded
    if not file or file.filename == '':
        flash("Будь ласка, виберіть файл зображення", "danger")
        return redirect(url_for('profile'))
    
    # Validate file type
    if file.content_type not in ['image/png', 'image/jpeg', 'image/jpg']:
        flash("Неправильний тип файлу! Дозволені тільки PNG та JPG", "danger")
        return redirect(url_for('profile'))
    
    # Validate file size
    if file.content_length > 1024 * 1024:
        flash("Завеликий розмір файлу! Максимальний розмір 1MB", "danger")
        return redirect(url_for('profile'))
    
    # Validate filename
    if not secure_filename(file.filename):
        flash("Файл має некоректну назву!", "danger")
        return redirect(url_for('profile'))
    
    # Ensure directory exists
    profile_dir = os.path.join('static', 'images', 'profile')
    os.makedirs(profile_dir, exist_ok=True)
    
    # Save file
    file_path = os.path.join(profile_dir, file.filename)
    file.save(file_path)
    
    # Update database
    try:
        update_avatar_image(current_user.id, file.filename)
        flash("Аватар успішно оновлено!", "success")
    except Exception as e:
        print(f"Avatar update error: {e}")
        flash("Помилка при оновленні аватара", "danger")
    
    return redirect(url_for('profile'))

@app.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_or_nickname = request.form.get('email_or_nickname')
        password = request.form.get('password')
        if not email_or_nickname or not password:
            flash("Будь ласка, заповніть усі поля", "danger")
            return redirect(url_for('login'))

        res = check_user(email_or_nickname, password)

        if isinstance(res, str):
            flash(res, 'danger')
            return redirect(url_for('login'))

        flash(res[0], 'success')
        login_user(res[1])
        return redirect(url_for('home_page'))

    return render_template('login.html')

@app.route('/logout/')
@login_required
def logout():
    logout_user()
    flash("Ви вийшли з системи", "info")
    return redirect(url_for('login'))

@app.route('/register/', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        email = request.form.get('email')
        password = request.form.get('password')
        if not nickname or not email or not password:
            flash("Будь ласка, заповніть усі поля", "danger")
            return redirect(url_for('register'))

        res = add_user(nickname, email, password)

        if res != "Користувача успішно додано":
            flash(res, 'danger')
            return redirect(url_for('register'))
        else:
            flash(res, 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/forgot-password/', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash("Будь ласка, введіть email", "danger")
            return render_template('forgot_password.html')
        
        # Check if user exists with this email
        user = get_user_by_email(email)
        if not user:
            # Don't reveal if email exists or not for security
            flash("Якщо цей email існує в нашій системі, ви отримаєте інструкції для відновлення паролю", "info")
            return redirect(url_for('login'))
        
        # Generate reset token
        reset_token = generate_reset_token()
        
        # Store token in session
        store_reset_token(email, reset_token)
        
        # Send reset email
        if send_password_reset_email(email, reset_token):
            flash("Інструкції для відновлення паролю надіслано на вашу пошту", "success")
        else:
            flash("Помилка при відправці email. Спробуйте пізніше", "danger")
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>/', methods=['GET', 'POST'])
def reset_password(token):
    # Validate token
    email = validate_reset_token(token)
    if not email:
        flash("Посилання для відновлення паролю недійсне або закінчилося", "danger")
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not new_password or not confirm_password:
            flash("Будь ласка, заповніть усі поля", "danger")
            return render_template('reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash("Паролі не співпадають", "danger")
            return render_template('reset_password.html', token=token)
        
        def validate_password(password):
            if len(password) < 8:
                flash("Пароль повинен містити щонайменше 8 символів", "danger")
                return False
            if not re.search(r"[A-Z]", password):
                flash("Пароль повинен містити хоча б одну велику літеру", "danger")
                return False
            if not re.search(r"[a-z]", password):
                flash("Пароль повинен містити хоча б одну малу літеру", "danger")
                return False
            if not re.search(r"[0-9]", password):
                flash("Пароль повинен містити хоча б одну цифру", "danger")
                return False
            if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
                flash("Пароль повинен містити хоча б один спеціальний символ", "danger")
                return False
            return True
        
        if not validate_password(new_password):
            return render_template('reset_password.html', token=token)
        
        # Update user password
        result = update_user_password(email, new_password)
        if "успішно" in result.lower():
            # Clear reset token
            clear_reset_token()
            flash("Пароль успішно змінено! Тепер можете увійти з новим паролем", "success")
            return redirect(url_for('login'))
        else:
            flash("Помилка при зміні паролю. Спробуйте ще раз", "danger")
    
    return render_template('reset_password.html', token=token)

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.status_admin:
            flash("У вас немає прав адміністратора", "danger")
            return redirect(url_for('home'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/admin/')
@login_required
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/users/')
@login_required
@admin_required
def admin_users():
    users = get_all_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>/')
@login_required
@admin_required
def admin_user_details(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash("Користувача не знайдено", "danger")
        return redirect(url_for('admin_users'))

    orders = get_user_orders(user_id)
    reservations = get_user_reservations(user_id)

    return render_template(
        'admin_user_details.html',
        user=user,
        orders=orders,
        reservations=reservations
    )

@app.route('/admin/menu/')
@login_required
@admin_required
def admin_menu():
    dishes = get_all_menu_items(only_active=False)
    return render_template('admin_menu.html', dishes=dishes)

@app.route('/admin/menu/edit/<int:dish_id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_dish(dish_id):
    dish = get_menu_item_by_id(dish_id)
    if not dish:
        flash("Страву не знайдено", "danger")
        return redirect(url_for('admin_menu'))

    if request.method == 'POST':
        name = request.form.get('name')
        ingredients = request.form.get('ingredients')
        description = request.form.get('description')
        
        try:
            price = float(request.form.get('price')) if request.form.get('price') else None
            weight = float(request.form.get('weight')) if request.form.get('weight') else None
            cal = int(request.form.get('cal')) if request.form.get('cal') else None
        except (ValueError, TypeError):
            flash("Невірні значення для ціни, ваги або калорійності", "danger")
            return render_template('admin_edit_dish.html', dish=dish)
        
        if price is not None and price <= 0:
            flash("Ціна має бути більша за 0", "danger")
            return render_template('admin_edit_dish.html', dish=dish)
        
        if weight is not None and weight < 0:
            flash("Вага не може бути негативною", "danger")
            return render_template('admin_edit_dish.html', dish=dish)
        
        if cal is not None and cal < 0:
            flash("Калорійність не може бути негативною", "danger")
            return render_template('admin_edit_dish.html', dish=dish)
        
        file = request.files.get('file')

        # Check if file was uploaded (optional for edit)
        if file and file.filename != '':
            # Validate file type
            if file.content_type not in ['image/png', 'image/jpeg', 'image/jpg']:
                flash("Неправильний тип файлу! Дозволені тільки PNG та JPG", "danger")
                return render_template('admin_edit_dish.html', dish=dish)
            
            # Validate filename
            if not secure_filename(file.filename):
                flash("Файл має некоректну назву!", "danger")
                return render_template('admin_edit_dish.html', dish=dish)
            
            # Ensure directory exists
            menu_dir = os.path.join('static', 'images', 'menu')
            os.makedirs(menu_dir, exist_ok=True)
            
            # Save file
            file_path = os.path.join(menu_dir, file.filename)
            file.save(file_path)
            # Don't call add_file - just use the filename directly
            
            # Use new filename for update
            image_filename = file.filename
        else:
            # Keep existing image if no new file uploaded
            image_filename = dish.image

        update_menu_item(
            dish_id,
            name=name,
            price=price,
            weight=weight,
            cal=cal,
            ingredients=ingredients,
            description=description,
            image=image_filename
        )

        flash("Страву оновлено", "success")
        return redirect(url_for('admin_menu'))

    return render_template('admin_edit_dish.html', dish=dish)

@app.route('/admin/menu/add/', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_dish():
    if request.method == 'POST':
        name = request.form.get('name')
        ingredients = request.form.get('ingredients')
        description = request.form.get('description')
        
        try:
            price = float(request.form.get('price', 0))
            weight = float(request.form.get('weight', 0))
            cal = int(request.form.get('cal', 0))
        except (ValueError, TypeError):
            flash("Невірні значення для ціни, ваги або калорійності", "danger")
            return render_template('admin_add_dish.html')
        
        if not name or not ingredients or not description or price <= 0:
            flash("Будь ласка, заповніть усі поля коректно", "danger")
            return render_template('admin_add_dish.html')

        if weight < 0 or cal < 0:
            flash("Вага та калорійність не можуть бути негативними", "danger")
            return render_template('admin_add_dish.html')
        
        file = request.files.get('file')

        # Check if file was actually uploaded
        if not file or file.filename == '':
            flash("Будь ласка, виберіть файл зображення", "danger")
            return render_template('admin_add_dish.html')

        # Validate file type
        if file.content_type not in ['image/png', 'image/jpeg', 'image/jpg']:
            flash("Неправильний тип файлу! Дозволені тільки PNG та JPG", "danger")
            return render_template('admin_add_dish.html')
        
        # Validate file size
        if file.content_length > 1024 * 1024:
            flash("Завеликий розмір файлу! Максимальний розмір 1MB", "danger")
            return render_template('admin_add_dish.html')
        
        # Validate filename
        if not secure_filename(file.filename):
            flash("Файл має некоректну назву!", "danger")
            return render_template('admin_add_dish.html')
        
        # Ensure directory exists
        menu_dir = os.path.join('static', 'images', 'menu')
        os.makedirs(menu_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(menu_dir, file.filename)
        file.save(file_path)
        
        # Don't call add_file - just use the filename directly

        res = create_menu_item(
            name=name,
            price=price,
            weight=weight,
            cal=cal,
            ingredients=ingredients,
            description=description,
            image=file.filename
        )
        
        if isinstance(res, tuple):
            flash(res[0], "success")
            return redirect(url_for('admin_menu'))
        else:
            flash(res, 'danger')
            return render_template('admin_add_dish.html')

    return render_template('admin_add_dish.html')

@app.route('/admin/orders/')
@login_required
@admin_required
def admin_orders():
    orders = get_all_orders()
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/order/<int:order_id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_order_details(order_id):
    if request.method == 'POST':
        new_status = request.form.get('status')
        try:
            order = get_order_by_id(order_id)
            if not order:
                flash("Замовлення не знайдено", "danger")
                return redirect(url_for('admin_orders'))
            if not new_status:
                flash("Будь ласка, виберіть статус", "danger")
                return render_template('admin_order_details.html', order=order)

            msg = Update_order_status(order_id, new_status)
            if "не знайдено" in msg.lower():
                flash(msg, "danger")
            else:
                flash(msg, "success")
            return redirect(url_for('admin_order_details', order_id=order_id))
        except Exception as e:
            flash(f"Помилка при оновленні статусу: {str(e)}", "danger")
            return redirect(url_for('admin_orders'))
    
    try:
        order = get_order_by_id(order_id)
        if not order:
            flash("Замовлення не знайдено", "danger")
            return redirect(url_for('admin_orders'))

        return render_template('admin_order_details.html', order=order)
    except Exception as e:
        flash(f"Помилка при завантаженні замовлення: {str(e)}", "danger")
        return redirect(url_for('admin_orders'))

@app.route('/admin/reservations/')
@login_required
@admin_required
def admin_reservations():
    reservations = get_all_reservations()
    return render_template('admin_reservations.html', reservations=reservations)

@app.route('/admin/reservation/<int:reservation_id>/')
@login_required
@admin_required
def admin_reservation_details(reservation_id):
    reservation = get_reservation_by_id(reservation_id)

    if not reservation:
        flash("Бронювання не знайдено", "danger")
        return redirect(url_for('admin_reservations'))

    return render_template('admin_reservation_details.html', reservation=reservation)

@app.route('/admin/tables/')
@login_required
@admin_required
def admin_tables():
    tables = get_all_tables()
    return render_template('admin_tables.html', tables=tables)

@app.route('/admin/table/edit/<int:table_id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_table(table_id):
    table = get_table_by_id(table_id)

    if not table:
        flash("Стіл не знайдено", "danger")
        return redirect(url_for('admin_tables'))

    if request.method == 'POST':
        try:
            seats = int(request.form.get('seats'))
        except (ValueError, TypeError):
            flash("Неправильне значення для кількості місць", "danger")
            return render_template('admin_edit_table.html', table=table)
        
        location = request.form.get('location', '').strip()
        if seats <= 0:
            flash("Кількість місць має бути більша за 0", "danger")
            return render_template('admin_edit_table.html', table=table)

        update_table(table_id, seats, location if location else None)

        flash("Стіл оновлено", "success")
        return redirect(url_for('admin_tables'))

    return render_template('admin_edit_table.html', table=table)

@app.route('/admin/table/add/', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_table():
    if request.method == 'POST':
        try:
            seats = int(request.form.get('seats'))
        except (ValueError, TypeError):
            flash("Неправильне значення для кількості місць", "danger")
            return render_template('admin_add_table.html')
        
        location = request.form.get('location', '').strip()
        if seats <= 0:
            flash("Кількість місць має бути більша за 0", "danger")
            return render_template('admin_add_table.html')

        res = create_table(seats, location if location else None)
        flash(res[0], "success")

        return redirect(url_for('admin_tables'))

    return render_template('admin_add_table.html')

@app.route('/admin/menu/delete/<int:dish_id>/', methods=['POST'])
@login_required
@admin_required
def admin_delete_dish(dish_id):
    result = delete_menu_item(dish_id)
    if "видалено" in result.lower():
        flash(result, "success")
    else:
        flash(result, "danger")
    return redirect(url_for('admin_menu'))

@app.route('/admin/user/<int:user_id>/toggle-admin/', methods=['POST'])
@login_required
@admin_required
def admin_toggle_user_status(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash("Користувача не знайдено", "danger")
        return redirect(url_for('admin_users'))
    
    new_status = not user.status_admin
    result = set_user_admin_status(user_id, new_status)
    if "не знайдено" in result.lower():
        flash(result, "danger")
    else:
        flash(result, "success")
    return redirect(url_for('admin_user_details', user_id=user_id))

@app.route('/admin/user/<int:user_id>/delete/', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        flash("Не можна видалити власний акаунт з адміна", "danger")
        return redirect(url_for('admin_user_details', user_id=user_id))
    
    result = delete_user(user_id)
    if "видалено" in result.lower():
        flash(result, "success")
    else:
        flash(result, "danger")
    return redirect(url_for('admin_users'))

@app.route('/admin/table/delete/<int:table_id>/', methods=['POST'])
@login_required
@admin_required
def admin_delete_table(table_id):
    result = delete_table(table_id)
    if "видалено" in result.lower():
        flash(result, "success")
    else:
        flash(result, "danger")
    return redirect(url_for('admin_tables'))

@app.route('/admin/order/delete/<int:order_id>/', methods=['POST'])
@login_required
@admin_required
def admin_delete_order(order_id):
    result = delete_order_admin(order_id)
    if "видалено" in result.lower():
        flash(result, "success")
    else:
        flash(result, "danger")
    return redirect(url_for('admin_orders'))

@app.route('/admin/reservation/delete/<int:reservation_id>/', methods=['POST'])
@login_required
@admin_required
def admin_delete_reservation(reservation_id):
    result = delete_reservation_admin(reservation_id)
    if "видалено" in result.lower():
        flash(result, "success")
    else:
        flash(result, "danger")
    return redirect(url_for('admin_reservations'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    _debug = os.getenv('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(debug=_debug)