from sqlalchemy import create_engine, inspect, text, String, Float, Integer, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, sessionmaker, selectinload
from sqlalchemy.orm import DeclarativeBase
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import re
import hashlib
import warnings
import bcrypt


def _load_dotenv_file():
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv_file()

RESERVATION_BLOCK_DURATION = timedelta(hours=2)
DEFAULT_MENU_IMAGE = "default1.jpg"


def _reservation_intervals_overlap(t_a: datetime, t_b: datetime) -> bool:
    return t_a < t_b + RESERVATION_BLOCK_DURATION and t_b < t_a + RESERVATION_BLOCK_DURATION

from flask_login import UserMixin 

import bcrypt 

PGUSER = os.getenv("RESTAURANT_PGUSER", "postgres")
PGPASSWORD = os.getenv("RESTAURANT_PGPASSWORD") or os.getenv("PGPASSWORD")
# Note: Database password is only needed for PostgreSQL, not SQLite

RESTAURANT_DB_NAME = os.getenv("RESTAURANT_DB_NAME", "restaurant")

engine = create_engine("sqlite:///database.db")
Session = sessionmaker(bind=engine)
DBSession = Session  # Alias for compatibility

class Base(DeclarativeBase):
    def create_db(self):
        Base.metadata.create_all(engine)

    def drop_db(self):
        Base.metadata.drop_all(engine)

class Users(UserMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(150), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    status_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_color: Mapped[str] = mapped_column(String(20), nullable=True)
    avatar_letter: Mapped[str] = mapped_column(String(2), nullable=True)
    avatar_image: Mapped[str] = mapped_column(String(200), nullable=True)

    def set_password(self, password:str):
        self.password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def check_password(self, password:str):
        return bcrypt.checkpw(password.encode(), self.password.encode())

    orders = relationship("Orders", back_populates="user", cascade="all, delete")
    reservations = relationship("Reservations", back_populates="user", cascade="all, delete")

class Menu(Base):
    __tablename__ = "menu"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    weight: Mapped[float] = mapped_column()
    cal: Mapped[int] = mapped_column()
    ingredients: Mapped[str] = mapped_column(Text)
    price: Mapped[float] = mapped_column()
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    image: Mapped[str] = mapped_column(String(100))

    order_items = relationship("OrderDish", back_populates="dish", cascade="all, delete")

class Orders(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(50), default="Прийнято")
    total: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default=None)

    user = relationship("Users", back_populates="orders")
    dishes = relationship("OrderDish", back_populates="order", cascade="all, delete")

class OrderDish(Base):
    __tablename__ = "order_dish"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    dish_id: Mapped[int] = mapped_column(ForeignKey("menu.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    order = relationship("Orders", back_populates="dishes")
    dish = relationship("Menu", back_populates="order_items")

class Tables(Base):
    __tablename__ = "tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    seats: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(100), nullable=True)

    reservations = relationship("ReservationTables", back_populates="table", cascade="all, delete")

class Reservations(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    time: Mapped[datetime] = mapped_column(DateTime)

    user = relationship("Users", back_populates="reservations")
    tables = relationship("ReservationTables", back_populates="reservation", cascade="all, delete")

class ReservationTables(Base):
    __tablename__ = "reservation_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"))
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))

    reservation = relationship("Reservations", back_populates="tables")
    table = relationship("Tables", back_populates="reservations")

def validate_nickname(nickname: str):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,19}", nickname):
        return "Нікнейм має містити 3–20 символів, починатися з літери та містити лише латиницю, цифри або _"
    return None

def validate_password(password: str):
    if len(password) < 8:
        return "Пароль має містити щонайменше 8 символів"
    if not re.search(r"[A-Z]", password):
        return "Пароль має містити хоча б одну велику літеру"
    if not re.search(r"[a-z]", password):
        return "Пароль має містити хоча б одну малу літеру"
    if not re.search(r"[0-9]", password):
        return "Пароль має містити хоча б одну цифру"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Пароль має містити хоча б один спеціальний символ"
    return None

def validate_email(email: str):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    if not re.fullmatch(pattern, email):
        return "Невірний формат електронної адреси"
    return None

def add_user(nickname, email, password, status=False):
    nickname_error = validate_nickname(nickname)
    if nickname_error:
        return nickname_error

    email_error = validate_email(email)
    if email_error:
        return email_error

    password_error = validate_password(password)
    if password_error:
        return password_error

    with Session() as session:
        existing_user = session.query(Users).filter(
            (Users.email == email) | (Users.nickname == nickname)
        ).first()
        if existing_user:
            return "Користувач з таким іменем або електронною адресою вже існує"

        user = Users(
        nickname=nickname,
        email=email,
        status_admin=status
    )
        user.set_password(password)
        generate_default_avatar(user)
        session.add(user)
        session.commit()
        return "Користувача успішно додано"
    
def check_user(nickname_or_email, password):
    with Session() as session:
        user = session.query(Users).filter(
            (Users.email == nickname_or_email) | (Users.nickname == nickname_or_email) 
        ).first()
        if not user:
            return "Користувача не існує"
        if not user.check_password(password):
            return "Неправильний пароль"
        if user:
            session.refresh(user)
        return "Користувач увійшов успішно", user
    
def search_user(user_id):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()
        return user  
        
def change_password(user_id: int, new_password: str):

    password_error = validate_password(new_password)
    if password_error:
        return password_error

    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()

        if not user:
            return "Користувача не знайдено"
        
        hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
        user.password = hashed.decode("utf-8")

        session.commit()
        return "Пароль успішно змінено"


def update_profile(user_id: int, new_username: Optional[str] = None, new_password: Optional[str] = None):
    nu = (new_username or "").strip()
    np = (new_password or "").strip()

    if not nu and not np:
        return "Нічого не змінено"

    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()
        if not user:
            return "Користувача не знайдено"

        if nu and nu != user.nickname:
            nickname_error = validate_nickname(nu)
            if nickname_error:
                return nickname_error
            existing = session.query(Users).filter(Users.nickname == nu).first()
            if existing and existing.id != user_id:
                return "Користувач з таким нікнеймом вже існує"

        if np:
            password_error = validate_password(np)
            if password_error:
                return password_error

        parts = []
        if nu and nu != user.nickname:
            user.nickname = nu
            generate_default_avatar(user)
            parts.append("нікнейм")
        if np:
            hashed = bcrypt.hashpw(np.encode("utf-8"), bcrypt.gensalt())
            user.password = hashed.decode("utf-8")
            parts.append("пароль")

        if not parts:
            return "Нічого не змінено"

        session.commit()
        return "Профіль успішно оновлено (" + ", ".join(parts) + ")"


def change_username(user_id: int, new_username: str):

    nickname_error = validate_nickname(new_username)
    if nickname_error:
        return nickname_error

    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()

        if not user:
            return "Користувача не знайдено"

        existing = session.query(Users).filter(Users.nickname == new_username).first()
        if existing and existing.id != user_id:
            return "Користувач з таким нікнеймом вже існує"

        user.nickname = new_username
        generate_default_avatar(user)
        session.commit()
        return "Нікнейм успішно змінено"
    
def generate_color_from_nickname(nickname: str) -> str:

    hash_value = hashlib.sha256(nickname.encode("utf-8")).hexdigest()

    color = "#" + hash_value[:6]

    return color

def generate_letter_from_nickname(nickname: str) -> str:
    return nickname[0].upper()

def generate_default_avatar(user: Users):
    user.avatar_letter = generate_letter_from_nickname(user.nickname)
    user.avatar_color = generate_color_from_nickname(user.nickname)
    user.avatar_image = None

def update_avatar_image(user_id: int, image_path: str):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()

        if not user:
            return "Користувача не знайдено"

        user.avatar_image = image_path  

        user.avatar_color = None
        user.avatar_letter = None

        session.commit()
        return "Аватарку оновлено"
    
def reset_avatar_to_default(user_id: int):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()

        if not user:
            return "Користувача не знайдено"

        generate_default_avatar(user)
        session.commit()
        return "Аватарку скинуто до стандартної"


def get_user_profile(user_id: int):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()
        if user:
            session.refresh(user)
        return user
    
def delete_own_account(user_id: int):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()

        if not user:
            return "Користувача не знайдено"

        session.delete(user)
        session.commit()
        return "Обліковий запис видалено"

def get_all_menu_items(only_active=True):
    with Session() as session:
        query = session.query(Menu)
        if only_active:
            query = query.filter(Menu.active == True)
        items = query.all()
        for item in items:
            session.refresh(item)
        return items
    
def get_menu_item_by_id(dish_id: int):
    with Session() as session:
        dish = session.query(Menu).filter_by(id=dish_id).first()
        if dish:
            session.refresh(dish)
        return dish
    
def search_menu_items(keyword: str):
    with Session() as session:
        keyword = f"%{keyword.lower()}%"
        dishes = session.query(Menu).filter(
            Menu.active == True,
            Menu.name.ilike(keyword)
        ).all()
        for dish in dishes:
            session.refresh(dish)
        return dishes
    
def filter_menu_items(min_price=None, max_price=None, min_cal=None, max_cal=None, only_active=True):
    with Session() as session:
        query = session.query(Menu)

        if only_active:
            query = query.filter(Menu.active == True)

        if min_price is not None:
            query = query.filter(Menu.price >= min_price)

        if max_price is not None:
            query = query.filter(Menu.price <= max_price)

        if min_cal is not None:
            query = query.filter(Menu.cal >= min_cal)

        if max_cal is not None:
            query = query.filter(Menu.cal <= max_cal)

        items = query.all()
        for item in items:
            session.refresh(item)
        return items 

def get_cart(session):
    raw = session.get("cart", {}) or {}
    out = {}
    for k, v in raw.items():
        try:
            out[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out

def add_to_cart(session, dish_id: int, quantity: int = 1):
    dish_id = int(dish_id)
    quantity = int(quantity)
    cart = get_cart(session)

    if dish_id in cart:
        cart[dish_id] += quantity
    else:
        cart[dish_id] = quantity

    session["cart"] = cart
    session.modified = True

def delete_from_cart(session, dish_id: int, quantity: int = 1):
    dish_id = int(dish_id)
    quantity = int(quantity)
    cart = get_cart(session)
    cart[dish_id] -= quantity

    session["cart"] = cart
    session.modified = True

def update_cart_item(session, dish_id: int, quantity: int):
    dish_id = int(dish_id)
    cart = get_cart(session)

    if quantity <= 0:
        cart.pop(dish_id, None)
    else:
        cart[dish_id] = quantity

    session["cart"] = cart
    session.modified = True

def remove_from_cart(session, dish_id: int):
    dish_id = int(dish_id)
    cart = get_cart(session)
    cart.pop(dish_id, None)
    session["cart"] = cart
    session.modified = True

def clear_cart(session):
    session["cart"] = {}
    session.modified = True


def prune_invalid_cart_entries(session) -> bool:
    """Remove missing, inactive, or non-positive quantities from the session cart. Returns True if changed."""
    raw = get_cart(session)
    if not raw:
        return False
    cleaned = {}
    for dish_id, qty in raw.items():
        dish = get_menu_item_by_id(dish_id)
        if dish and dish.active and qty > 0:
            cleaned[dish_id] = qty
    if cleaned == raw:
        return False
    session["cart"] = cleaned
    session.modified = True
    return True


def create_order(user_id: int, cart: dict, note: str = None):
    if not cart:
        return "Кошик порожній"

    with Session() as session:
        order = Orders(user_id=user_id, note=note)
        total = 0.0
        
        session.add(order)
        session.flush() 

        items_added = 0
        for dish_id, quantity in cart.items():
            try:
                did = int(dish_id)
                qty = int(quantity)
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            dish = session.query(Menu).filter_by(id=did).first()
            if not dish or not dish.active:
                continue

            total += dish.price * qty
            item = OrderDish(
                order_id=order.id,
                dish_id=did,
                quantity=qty
            )
            session.add(item)
            items_added += 1

        if items_added == 0:
            session.rollback()
            return "У кошику немає доступних страв. Оновіть кошик і спробуйте знову."

        order.total = total
        session.commit()
        return "Замовлення створено успішно", order.id
    
def get_user_orders(user_id: int):
    with Session() as session:
        orders = (
            session.query(Orders)
            .options(selectinload(Orders.user), selectinload(Orders.dishes).selectinload(OrderDish.dish))
            .filter_by(user_id=user_id)
            .order_by(Orders.time.desc())
            .all()
        )
        return orders
    
def get_order_details(order_id: int):
    with Session() as session:
        order = (
            session.query(Orders)
            .options(selectinload(Orders.user), selectinload(Orders.dishes).selectinload(OrderDish.dish))
            .filter_by(id=order_id)
            .first()
        )
        return order
      
def cancel_order(order_id: int, user_id: int):
    with Session() as session:
        order = session.query(Orders).filter_by(id=order_id, user_id=user_id).first()

        if not order:
            return "Замовлення не знайдено"

        session.delete(order)
        session.commit()
        return "Замовлення скасовано"
    
def get_all_tables():
    with Session() as session:
        tables = session.query(Tables).order_by(Tables.id).all()
        for table in tables:
            session.refresh(table)
        return tables
    
def get_table_by_id(table_id: int):
    with Session() as session:
        table = session.query(Tables).filter_by(id=table_id).first()
        if table:
            session.refresh(table)
        return table
    
def check_table_availability(table_id: int, time: datetime):
    with Session() as session:
        links = (
            session.query(ReservationTables)
            .join(Reservations)
            .filter(ReservationTables.table_id == table_id)
            .all()
        )
        for link in links:
            if _reservation_intervals_overlap(link.reservation.time, time):
                return False
        return True


def create_reservation(user_id: int, table_ids: list[int], time: datetime):
    with Session() as session:

        for table_id in table_ids:
            links = (
                session.query(ReservationTables)
                .join(Reservations)
                .filter(ReservationTables.table_id == table_id)
                .all()
            )
            for link in links:
                if _reservation_intervals_overlap(link.reservation.time, time):
                    return f"Стіл {table_id} вже заброньований на обраний час"

        reservation = Reservations(
            user_id=user_id,
            time=time
        )
        session.add(reservation)
        session.flush()

        for table_id in table_ids:
            link = ReservationTables(
                reservation_id=reservation.id,
                table_id=table_id
            )
            session.add(link)

        session.commit()
        return "Бронювання створено успішно", reservation.id
    
def get_user_reservations(user_id: int):
    with Session() as session:
        reservations = (
            session.query(Reservations)
            .options(selectinload(Reservations.tables).selectinload(ReservationTables.table), selectinload(Reservations.user))
            .filter_by(user_id=user_id)
            .order_by(Reservations.time.desc())
            .all()
        )
        return reservations
    
def cancel_reservation(reservation_id: int, user_id: int):
    with Session() as session:
        reservation = (
            session.query(Reservations)
            .filter_by(id=reservation_id, user_id=user_id)
            .first()
        )

        if not reservation:
            return "Бронювання не знайдено"

        session.delete(reservation)
        session.commit()
        return "Бронювання скасовано"
    
# !ADMIN!

def get_all_users():
    with Session() as session:
        users = session.query(Users).order_by(Users.id).all()
        for user in users:
            session.refresh(user)
        return users
    
def get_user_by_id(user_id: int):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()
        if user:
            session.refresh(user)
        return user
    
def delete_user(user_id: int):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()

        if not user:
            return "Користувача не знайдено"

        session.delete(user)
        session.commit()
        return "Користувача видалено"
    
def set_user_admin_status(user_id: int, is_admin: bool):
    with Session() as session:
        user = session.query(Users).filter_by(id=user_id).first()

        if not user:
            return "Користувача не знайдено"

        user.status_admin = is_admin
        session.commit()

        if is_admin:
            return "Користувач отримав права адміністратора"
        else:
            return "Користувач позбавлений прав адміністратора"
        
def create_menu_item(name: str, price: float, ingredients: str, description: str, weight: float = 0.0, cal: int = 0, image: str = None):
    with Session() as session:
        img = image if image else DEFAULT_MENU_IMAGE
        item = Menu(
            name=name,
            price=price,
            ingredients=ingredients,
            description=description,
            weight=weight,
            cal=cal,
            active=True
        )
        item.image = img 
        session.add(item)
        session.commit()
        return "Страву створено успішно", item.id

def add_file(filename):
    with Session() as session:
        new_db_object = Menu(image=filename)
        session.add(new_db_object)
        session.commit()
    
def update_menu_item(item_id: int, name: str = None, price: float = None,
                     ingredients: str = None, description: str = None, weight: float = None, cal: int = None, image: str = None, active: bool = None):
    with Session() as session:
        item = session.query(Menu).filter_by(id=item_id).first()

        if not item:
            return "Страву не знайдено"

        if name is not None:
            item.name = name
        if price is not None:
            item.price = price
        if ingredients is not None:
            item.ingredients = ingredients
        if description is not None:
            item.description = description
        if weight is not None:
            item.weight = weight
        if cal is not None:
            item.cal = cal
        if image is not None:
            item.image = image  
        if active is not None:
            item.active = active

        session.commit()
        return "Страву оновлено успішно"
     
def delete_menu_item(item_id: int):
    with Session() as session:
        item = session.query(Menu).filter_by(id=item_id).first()

        if not item:
            return "Страву не знайдено"

        session.delete(item)
        session.commit()
        return "Страву видалено"

def get_all_orders():
    with Session() as session:
        orders = (
            session.query(Orders)
            .options(selectinload(Orders.user), selectinload(Orders.dishes).selectinload(OrderDish.dish))
            .order_by(Orders.time.desc())
            .all()
        )
        return orders
    
def get_order_by_id(order_id: int):
    with Session() as session:
        order = (
            session.query(Orders)
            .options(selectinload(Orders.user), selectinload(Orders.dishes).selectinload(OrderDish.dish))
            .filter_by(id=order_id)
            .first()
        )
        return order
    
def delete_order_admin(order_id: int):
    with Session() as session:
        order = session.query(Orders).filter_by(id=order_id).first()

        if not order:
            return "Замовлення не знайдено"

        session.delete(order)
        session.commit()
        return "Замовлення видалено"

def Update_order_status(order_id: int, new_status: str):
    with Session() as session:
        order = session.query(Orders).filter_by(id=order_id).first()
        
        if not order:
            return "Замовлення не знайдено"
        
        order.status = new_status
        session.commit()
        return "Статус оновлено"
    
def get_all_reservations():
    with Session() as session:
        reservations = (
            session.query(Reservations)
            .options(selectinload(Reservations.user), selectinload(Reservations.tables).selectinload(ReservationTables.table))
            .order_by(Reservations.time.desc())
            .all()
        )
        return reservations
    
def get_reservation_by_id(reservation_id: int):
    with Session() as session:
        reservation = (
            session.query(Reservations)
            .options(selectinload(Reservations.user), selectinload(Reservations.tables).selectinload(ReservationTables.table))
            .filter_by(id=reservation_id)
            .first()
        )
        return reservation
    
def delete_reservation_admin(reservation_id: int):
    with Session() as session:
        reservation = (
            session.query(Reservations)
            .filter_by(id=reservation_id)
            .first()
        )

        if not reservation:
            return "Бронювання не знайдено"

        session.delete(reservation)
        session.commit()
        return "Бронювання видалено"
    
def create_table(seats: int, location: str = None):
    with Session() as session:
        table = Tables(seats=seats, location=location)
        session.add(table)
        session.commit()
        return "Стіл створено успішно", table.id
    
def update_table(table_id: int, seats: int, location: str = None):
    with Session() as session:
        table = session.query(Tables).filter_by(id=table_id).first()

        if not table:
            return "Стіл не знайдено"

        table.seats = seats
        if location is not None:
            table.location = location
        session.commit()
        return "Стіл оновлено успішно"
    
def delete_table(table_id: int):
    with Session() as session:
        table = session.query(Tables).filter_by(id=table_id).first()

        if not table:
            return "Стіл не знайдено"

        session.delete(table)
        session.commit()
        return "Стіл видалено"

# base = Base()
# base.create_db()

# -----------------------------
# 1. USERS (з адміном)
# -----------------------------

def seed_users():
    with Session() as session:

        # Адмін
        admin = Users(
            nickname="AdminMaster",
            email="admin@example.com",
            status_admin=True
        )
        admin.set_password("Admin123!")
        generate_default_avatar(admin)
        session.add(admin)

        # Звичайні користувачі
        user1 = Users(
            nickname="Violetta",
            email="violetta@example.com",
            status_admin=False
        )
        user1.set_password("Violetta123!")
        generate_default_avatar(user1)
        session.add(user1)

        user2 = Users(
            nickname="Oliver",
            email="oliver@example.com",
            status_admin=False
        )
        user2.set_password("Oliver123!")
        generate_default_avatar(user2)
        session.add(user2)

        session.commit()
        print("Users added successfully!")


# -----------------------------
# 2. TABLES
# -----------------------------

def seed_tables():
    with Session() as session:

        tables = [
            Tables(seats=2),
            Tables(seats=4),
            Tables(seats=4),
            Tables(seats=6),
            Tables(seats=8),
        ]

        for t in tables:
            session.add(t)

        session.commit()
        print("Tables added successfully!")


# -----------------------------
# 3. MENU
# -----------------------------

def seed_menu():
    with Session() as session:

        dishes = [

            # 1. Давній Єгипет
            Menu(
                name="Хетепет — Хліб із медом",
                weight=180,
                cal=260,
                ingredients="Пшеничний хліб, мед, кунжут",
                price=120,
                description="Традиційний єгипетський хліб, поданий із запашним медом.",
                image="default1.jpg"
            ),

            # 2. Давня Греція
            Menu(
                name="Платонівська Олива",
                weight=150,
                cal=210,
                ingredients="Оливки, оливкова олія, зелень",
                price=140,
                description="Асорті грецьких оливок, натхненне філософськими трапезами.",
                image="default2.jpg"
            ),

            # 3. Давній Рим
            Menu(
                name="Гарум Стейк",
                weight=320,
                cal=540,
                ingredients="Яловичина, гарум, спеції",
                price=390,
                description="Римський стейк, маринований у гарумі — делікатес імператорів.",
                image="default3.jpg"
            ),

            # 4. Середньовіччя
            Menu(
                name="Королівська Порція",
                weight=450,
                cal=780,
                ingredients="Запечена курка, мед, чорнослив, трави",
                price=350,
                description="Страва, якою частували лицарів після турнірів.",
                image="default4.jpg"
            ),

            # 5. Епоха Відродження
            Menu(
                name="Флорентійська Паста",
                weight=300,
                cal=520,
                ingredients="Паста, вершки, шпинат, сир",
                price=230,
                description="Ніжна паста, натхненна кулінарією Флоренції XV століття.",
                image="default5.jpg"
            ),

            # 6. Бароко
            Menu(
                name="Трюфельний Крем-суп",
                weight=250,
                cal=410,
                ingredients="Трюфель, вершки, гриби",
                price=310,
                description="Вишуканий суп у стилі розкоші бароко.",
                image="default6.jpg"
            ),

            # 7. Вікторіанська епоха
            Menu(
                name="Англійський Ростбіф",
                weight=350,
                cal=620,
                ingredients="Яловичина, гірчиця, трави",
                price=420,
                description="Класичний вікторіанський ростбіф, соковитий і ароматний.",
                image="default7.jpg"
            ),

            # 8. Індустріальна епоха
            Menu(
                name="Паровий Пиріг",
                weight=280,
                cal=480,
                ingredients="М'ясо, овочі, тісто",
                price=190,
                description="Поживний пиріг, популярний серед робітників фабрик XIX століття.",
                image="default8.jpg"
            ),

            # 9. 1920s — Епоха Джазу
            Menu(
                name="Джазовий Коктейль-салат",
                weight=220,
                cal=330,
                ingredients="Креветки, лимон, зелень",
                price=260,
                description="Легкий салат у стилі вечірок 1920-х.",
                image="default9.jpg"
            ),

            # 10. 1950s — Американська класика
            Menu(
                name="Ретро Бургер",
                weight=310,
                cal=690,
                ingredients="Яловичина, сир чеддер, булочка",
                price=210,
                description="Соковитий бургер у стилі американських закладів 50-х.",
                image="default10.jpg"
            ),

            # 11. 1980s — Поп-культура
            Menu(
                name="Неонова Піца",
                weight=400,
                cal=740,
                ingredients="Пепероні, сир, томати",
                price=260,
                description="Яскрава піца, натхненна естетикою 80-х.",
                image="default11.jpg"
            ),

            # 12. Сучасність
            Menu(
                name="Філе Мізо‑Гласе з Димом Сакури та Перловим Соусом Юдзу",
                weight=280,
                cal=540,
                ingredients="Телятина, біле місо, юдзу, сакуровий дим, вершковий соус, молекулярні перли",
                price=520,
                description="Вишукане теляче філе, глазуроване білим місо, подане під куполом із димом сакури та доповнене перловим соусом юдзу.",
                image="default12.jpg"
            ),
        ]

        for d in dishes:
            session.add(d)

        session.commit()
        print("12 thematic menu items added successfully!")


# -----------------------------
# RUN ALL
# -----------------------------

def _drop_tables_that_reference_users() -> None:
    """
    If another app used the same database and created FKs to public.users (e.g. friends,
    messages), PostgreSQL blocks DROP TABLE users. Remove those tables first.
    """
    with engine.begin() as conn:
        for name in ("messages", "friends"):
            conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))


def _users_table_matches_model() -> bool:
    """False if an old users table exists without columns the ORM expects."""
    insp = inspect(engine)
    if not insp.has_table("users"):
        return True
    cols = {c["name"] for c in insp.get_columns("users")}
    required = {"status_admin", "avatar_color", "avatar_letter", "avatar_image"}
    return required.issubset(cols)


if __name__ == "__main__":
    import sys

    if "--reset" in sys.argv:
        print("Dropping all tables (all data will be lost)...", flush=True)
        _drop_tables_that_reference_users()
        Base.metadata.drop_all(engine)

    print("Creating tables if they do not exist...", flush=True)
    Base.metadata.create_all(engine)

    if not _users_table_matches_model():
        missing = {"status_admin", "avatar_color", "avatar_letter", "avatar_image"} - {
            c["name"] for c in inspect(engine).get_columns("users")
        }
        print(
            "\n*** Помилка схеми БД ***\n"
            f"Таблиця 'users' вже є, але без колонок: {sorted(missing)}\n"
            "create_all() не змінює існуючі таблиці — тому INSERT у seed падає.\n\n"
            f"Виконайте (видалить УСІ дані в базі {RESTAURANT_DB_NAME}):\n"
            "  python database.py --reset\n",
            flush=True,
        )
        sys.exit(1)

    print("Seeding...", flush=True)
    # seed_users()
    # seed_tables()
    # seed_menu()
    print("Done.", flush=True)

def get_user_by_email(email):
    """Get user by email"""
    with Session() as session:
        user = session.query(Users).filter(Users.email == email).first()
        if user:
            session.refresh(user)
        return user

def update_user_password(email, new_password):
    """Update user password"""
    try:
        with Session() as session:
            user = session.query(Users).filter(Users.email == email).first()
            if user:
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                user.password_hash = hashed_password
                session.commit()
                return "Пароль успішно оновлено"
            else:
                return "Користувача не знайдено"
    except Exception as e:
        return f"Помилка: {str(e)}"
