from flask import Flask, render_template, request, jsonify
import requests
import os
from dotenv import load_dotenv
import concurrent.futures
import time
from functools import wraps
import re
from werkzeug.exceptions import BadRequest

# بارگذاری متغیرهای محیطی
load_dotenv()

app = Flask(__name__)

# تنظیمات امنیتی Flask
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 ساعت

# کلید API TMDB
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
if not TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY not found in environment variables")

BASE_URL = "https://api.themoviedb.org/3"

# کش ساده برای بهبود سرعت
cache = {}
CACHE_DURATION = 300  # 5 دقیقه

def validate_input(value, max_length=100, pattern=None):
    """اعتبارسنجی ورودی‌ها"""
    if not value or not isinstance(value, str):
        return False
    if len(value) > max_length:
        return False
    if pattern and not re.match(pattern, value):
        return False
    return True

def sanitize_input(value):
    """پاکسازی ورودی‌ها"""
    if not value:
        return ""
    # حذف کاراکترهای خطرناک
    dangerous_chars = ['<', '>', '"', "'", '&', 'script', 'javascript']
    for char in dangerous_chars:
        value = value.replace(char, '')
    return value.strip()

def cache_result(func):
    """دکوراتور برای کش کردن نتایج توابع"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # ایجاد کلید منحصر به فرد برای کش
        cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
        
        # بررسی وجود در کش
        if cache_key in cache:
            result, timestamp = cache[cache_key]
            if time.time() - timestamp < CACHE_DURATION:
                return result
        
        # اجرای تابع و ذخیره در کش
        result = func(*args, **kwargs)
        cache[cache_key] = (result, time.time())
        
        # پاک کردن کش قدیمی (اگر بیش از 100 آیتم باشد)
        if len(cache) > 100:
            oldest_key = min(cache.keys(), key=lambda k: cache[k][1])
            del cache[oldest_key]
        
        return result
    return wrapper

# ذخیره موقت داده‌ها در حافظه
movies_cache = {}
tv_cache = {}

@cache_result
def get_movie_details(movie_id):
    """دریافت جزئیات فیلم از API TMDB"""
    if movie_id in movies_cache:
        return movies_cache[movie_id]
    
    # دریافت اطلاعات اصلی فیلم (انگلیسی) - برای نام، کاور، ژانرها و...
    url = f"{BASE_URL}/movie/{movie_id}"
    params_en = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',
        'append_to_response': 'credits'
    }
    
    response_en = requests.get(url, params=params_en)
    movie_data_en = response_en.json() if response_en.status_code == 200 else {}
    
    # دریافت فقط توضیحات فارسی
    params_fa = {
        'api_key': TMDB_API_KEY,
        'language': 'fa-IR'
    }
    
    response_fa = requests.get(url, params=params_fa)
    movie_data_fa = response_fa.json() if response_fa.status_code == 200 else {}
    
    # ترکیب اطلاعات: همه چیز از انگلیسی، فقط توضیحات از فارسی
    movie_data = movie_data_en.copy()
    if movie_data_fa.get('overview'):
        movie_data['overview_fa'] = movie_data_fa['overview']
    
    # استخراج اطلاعات کارگردان و بازیگران اصلی
    credits = movie_data.get('credits', {})
    crew = credits.get('crew', [])
    cast = credits.get('cast', [])
    
    # پیدا کردن کارگردان
    director = next((person for person in crew if person['job'] == 'Director'), None)
    movie_data['director'] = director
    
    # انتخاب 4 بازیگر اصلی
    movie_data['main_cast'] = cast[:4]
    
    movies_cache[movie_id] = movie_data
    return movie_data

@cache_result
def get_tv_details(tv_id):
    """دریافت جزئیات سریال از API TMDB"""
    if tv_id in tv_cache:
        return tv_cache[tv_id]
    
    # دریافت اطلاعات اصلی سریال (انگلیسی) - برای نام، کاور، ژانرها و...
    url = f"{BASE_URL}/tv/{tv_id}"
    params_en = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',
        'append_to_response': 'credits'
    }
    
    response_en = requests.get(url, params=params_en)
    tv_data_en = response_en.json() if response_en.status_code == 200 else {}
    
    # دریافت فقط توضیحات فارسی
    params_fa = {
        'api_key': TMDB_API_KEY,
        'language': 'fa-IR'
    }
    
    response_fa = requests.get(url, params=params_fa)
    tv_data_fa = response_fa.json() if response_fa.status_code == 200 else {}
    
    # ترکیب اطلاعات: همه چیز از انگلیسی، فقط توضیحات از فارسی
    tv_data = tv_data_en.copy()
    if tv_data_fa.get('overview'):
        tv_data['overview_fa'] = tv_data_fa['overview']
    
    # استخراج اطلاعات کارگردان و بازیگران اصلی
    credits = tv_data.get('credits', {})
    crew = credits.get('crew', [])
    cast = credits.get('cast', [])
    
    # پیدا کردن کارگردان (Show Creator)
    creator = next((person for person in crew if person['job'] == 'Creator'), None)
    tv_data['creator'] = creator
    
    # انتخاب 4 بازیگر اصلی
    tv_data['main_cast'] = cast[:4]
    
    tv_cache[tv_id] = tv_data
    return tv_data

def fetch_fa_overview_movie(movie):
    if movie.get('id'):
        fa_url = f"{BASE_URL}/movie/{movie['id']}"
        fa_params = {
            'api_key': TMDB_API_KEY,
            'language': 'fa-IR'
        }
        try:
            fa_response = requests.get(fa_url, params=fa_params, timeout=5)
            if fa_response.status_code == 200:
                fa_data = fa_response.json()
                if fa_data.get('overview'):
                    movie['overview_fa'] = fa_data['overview']
        except (requests.RequestException, ValueError):
            # در صورت خطا، توضیح فارسی را اضافه نمی‌کنیم
            pass
    return movie

def fetch_fa_overview_tv(tv):
    if tv.get('id'):
        fa_url = f"{BASE_URL}/tv/{tv['id']}"
        fa_params = {
            'api_key': TMDB_API_KEY,
            'language': 'fa-IR'
        }
        try:
            fa_response = requests.get(fa_url, params=fa_params, timeout=5)
            if fa_response.status_code == 200:
                fa_data = fa_response.json()
                if fa_data.get('overview'):
                    tv['overview_fa'] = fa_data['overview']
        except (requests.RequestException, ValueError):
            # در صورت خطا، توضیح فارسی را اضافه نمی‌کنیم
            pass
    return tv

def search_movies(query):
    """جستجوی فیلم‌ها با اعتبارسنجی ورودی"""
    # اعتبارسنجی ورودی
    if not validate_input(query, max_length=50):
        return []
    
    # پاکسازی ورودی
    query = sanitize_input(query)
    
    url = f"{BASE_URL}/search/movie"
    params = {
        'api_key': TMDB_API_KEY,
        'query': query,
        'language': 'en-US',
        'page': 1,
        'per_page': 10  # کاهش تعداد نتایج جستجو
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json()['results']
            # موازی‌سازی دریافت توضیحات فارسی
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(fetch_fa_overview_movie, results))
            return results
    except (requests.RequestException, ValueError):
        pass
    return []

def get_similar_movies(movie_id):
    """دریافت فیلم‌های مشابه با اعتبارسنجی"""
    # اعتبارسنجی movie_id
    if not isinstance(movie_id, int) or movie_id <= 0:
        return []
    
    url = f"{BASE_URL}/movie/{movie_id}/similar"
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',
        'page': 1,
        'per_page': 8  # کاهش تعداد فیلم‌های مشابه
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json()['results']
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(fetch_fa_overview_movie, results))
            return results
    except (requests.RequestException, ValueError):
        pass
    return []

def get_similar_tv(tv_id):
    """دریافت سریال‌های مشابه با اعتبارسنجی"""
    # اعتبارسنجی tv_id
    if not isinstance(tv_id, int) or tv_id <= 0:
        return []
    
    url = f"{BASE_URL}/tv/{tv_id}/similar"
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',
        'page': 1,
        'per_page': 8  # کاهش تعداد سریال‌های مشابه
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            results = response.json()['results']
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(fetch_fa_overview_tv, results))
            return results
    except (requests.RequestException, ValueError):
        pass
    return []

def get_movies_by_preferences(genre_id, year, min_rating, content_type='movie', page=1):
    """دریافت محتوا بر اساس ترجیحات کاربر"""
    
    if content_type == 'series':
        # برای سریال‌ها از endpoint سریال استفاده می‌کنیم
        return get_tv_by_preferences(genre_id, year, min_rating, page)
    elif content_type == 'animation':
        # برای انیمیشن‌ها از endpoint فیلم با فیلتر انیمیشن
        return get_animation_by_preferences(genre_id, year, min_rating, page)
    elif content_type == 'anime':
        # برای انیمه‌ها از endpoint سریال با فیلتر انیمه
        return get_anime_by_preferences(genre_id, year, min_rating, page)
    else:
        # برای فیلم‌ها از endpoint فیلم
        return get_movie_by_preferences(genre_id, year, min_rating, page)

def get_movie_by_preferences(genre_id, year, min_rating, page=1):
    """دریافت فیلم‌ها بر اساس ترجیحات"""
    url = f"{BASE_URL}/discover/movie"
    
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',  # نتایج به انگلیسی برای نام و کاور
        'sort_by': 'popularity.desc',
        'page': page,
        'vote_count.gte': 100,
        'per_page': 12  # کاهش تعداد فیلم‌ها در هر صفحه
    }
    
    if genre_id:
        params['with_genres'] = genre_id
    
    # تنظیم بازه زمانی
    if year == '2020':
        params['primary_release_date.gte'] = '2020-01-01'
    elif year == '2010':
        params['primary_release_date.gte'] = '2010-01-01'
        params['primary_release_date.lte'] = '2019-12-31'
    elif year == '2000':
        params['primary_release_date.gte'] = '2000-01-01'
        params['primary_release_date.lte'] = '2009-12-31'
    else:  # قبل از 2000
        params['primary_release_date.lte'] = '1999-12-31'
    
    # تنظیم حداقل امتیاز
    if min_rating == '8':
        params['vote_average.gte'] = 8.0
    elif min_rating == '6':
        params['vote_average.gte'] = 6.0
        params['vote_average.lte'] = 7.9
    elif min_rating == '4':
        params['vote_average.gte'] = 4.0
        params['vote_average.lte'] = 5.9
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            movies = data['results']
            
            # موازی‌سازی دریافت توضیحات فارسی
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                movies = list(executor.map(fetch_fa_overview_movie, movies))
            
            return {
                'movies': movies,
                'total_pages': data['total_pages'],
                'current_page': page
            }
    except (requests.RequestException, ValueError):
        pass
    return {'movies': [], 'total_pages': 0, 'current_page': 1}

def get_tv_by_preferences(genre_id, year, min_rating, page=1):
    """دریافت سریال‌ها بر اساس ترجیحات"""
    url = f"{BASE_URL}/discover/tv"
    
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',  # نتایج به انگلیسی برای نام و کاور
        'sort_by': 'popularity.desc',
        'page': page,
        'vote_count.gte': 50,
        'per_page': 12  # کاهش تعداد سریال‌ها در هر صفحه
    }
    
    if genre_id:
        params['with_genres'] = genre_id
    
    # تنظیم بازه زمانی
    if year == '2020':
        params['first_air_date.gte'] = '2020-01-01'
    elif year == '2010':
        params['first_air_date.gte'] = '2010-01-01'
        params['first_air_date.lte'] = '2019-12-31'
    elif year == '2000':
        params['first_air_date.gte'] = '2000-01-01'
        params['first_air_date.lte'] = '2009-12-31'
    else:  # قبل از 2000
        params['first_air_date.lte'] = '1999-12-31'
    
    # تنظیم حداقل امتیاز
    if min_rating == '8':
        params['vote_average.gte'] = 8.0
    elif min_rating == '6':
        params['vote_average.gte'] = 6.0
        params['vote_average.lte'] = 7.9
    elif min_rating == '4':
        params['vote_average.gte'] = 4.0
        params['vote_average.lte'] = 5.9
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            tv_shows = data['results']
            
            # موازی‌سازی دریافت توضیحات فارسی
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                tv_shows = list(executor.map(fetch_fa_overview_tv, tv_shows))
            
            return {
                'movies': tv_shows,  # برای سازگاری با template
                'total_pages': data['total_pages'],
                'current_page': page
            }
    except (requests.RequestException, ValueError):
        pass
    return {'movies': [], 'total_pages': 0, 'current_page': 1}

def get_animation_by_preferences(genre_id, year, min_rating, page=1):
    """دریافت انیمیشن‌ها بر اساس ترجیحات"""
    url = f"{BASE_URL}/discover/movie"
    
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',  # نتایج به انگلیسی برای نام و کاور
        'sort_by': 'popularity.desc',
        'page': page,
        'vote_count.gte': 50,
        'per_page': 12  # کاهش تعداد انیمیشن‌ها در هر صفحه
    }
    
    # ژانر انیمیشن (ID: 16)
    animation_genre_id = 16
    if genre_id:
        params['with_genres'] = f"{genre_id},{animation_genre_id}"
    else:
        params['with_genres'] = animation_genre_id
    
    # تنظیم بازه زمانی
    if year == '2020':
        params['primary_release_date.gte'] = '2020-01-01'
    elif year == '2010':
        params['primary_release_date.gte'] = '2010-01-01'
        params['primary_release_date.lte'] = '2019-12-31'
    elif year == '2000':
        params['primary_release_date.gte'] = '2000-01-01'
        params['primary_release_date.lte'] = '2009-12-31'
    else:  # قبل از 2000
        params['primary_release_date.lte'] = '1999-12-31'
    
    # تنظیم حداقل امتیاز
    if min_rating == '8':
        params['vote_average.gte'] = 8.0
    elif min_rating == '6':
        params['vote_average.gte'] = 6.0
        params['vote_average.lte'] = 7.9
    elif min_rating == '4':
        params['vote_average.gte'] = 4.0
        params['vote_average.lte'] = 5.9
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            movies = data['results']
            
            # موازی‌سازی دریافت توضیحات فارسی
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                movies = list(executor.map(fetch_fa_overview_movie, movies))
            
            return {
                'movies': movies,
                'total_pages': data['total_pages'],
                'current_page': page
            }
    except (requests.RequestException, ValueError):
        pass
    return {'movies': [], 'total_pages': 0, 'current_page': 1}

def get_anime_by_preferences(genre_id, year, min_rating, page=1):
    """دریافت انیمه‌ها بر اساس ترجیحات"""
    url = f"{BASE_URL}/discover/tv"
    
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US',  # نتایج به انگلیسی برای نام و کاور
        'sort_by': 'popularity.desc',
        'page': page,
        'vote_count.gte': 30,
        'per_page': 12  # کاهش تعداد انیمه‌ها در هر صفحه
    }
    
    # ژانر انیمیشن (ID: 16) برای انیمه
    animation_genre_id = 16
    if genre_id:
        params['with_genres'] = f"{genre_id},{animation_genre_id}"
    else:
        params['with_genres'] = animation_genre_id
    
    # تنظیم بازه زمانی
    if year == '2020':
        params['first_air_date.gte'] = '2020-01-01'
    elif year == '2010':
        params['first_air_date.gte'] = '2010-01-01'
        params['first_air_date.lte'] = '2019-12-31'
    elif year == '2000':
        params['first_air_date.gte'] = '2000-01-01'
        params['first_air_date.lte'] = '2009-12-31'
    else:  # قبل از 2000
        params['first_air_date.lte'] = '1999-12-31'
    
    # تنظیم حداقل امتیاز
    if min_rating == '8':
        params['vote_average.gte'] = 8.0
    elif min_rating == '6':
        params['vote_average.gte'] = 6.0
        params['vote_average.lte'] = 7.9
    elif min_rating == '4':
        params['vote_average.gte'] = 4.0
        params['vote_average.lte'] = 5.9
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            tv_shows = data['results']
            
            # موازی‌سازی دریافت توضیحات فارسی
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                tv_shows = list(executor.map(fetch_fa_overview_tv, tv_shows))
            
            return {
                'movies': tv_shows,  # برای سازگاری با template
                'total_pages': data['total_pages'],
                'current_page': page
            }
    except (requests.RequestException, ValueError):
        pass
    return {'movies': [], 'total_pages': 0, 'current_page': 1}

def get_person_movies(person_id, person_type):
    """دریافت فیلم‌های کارگردان یا بازیگر"""
    url = f"{BASE_URL}/person/{person_id}/movie_credits"
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'en-US'
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if person_type == 'director':
                movies = [movie for movie in data['crew'] if movie['job'] == 'Director']
            else:
                movies = data['cast']
            movies.sort(key=lambda x: x.get('popularity', 0), reverse=True)
            movies = movies[:8]  # کاهش از ۱۲ به ۸
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                movies = list(executor.map(fetch_fa_overview_movie, movies))
            return movies
    except (requests.RequestException, ValueError):
        pass
    return []

@app.route('/')
def home():
    """صفحه اصلی با سوالات"""
    return render_template('questions.html')

@app.route('/search')
def search():
    """جستجوی فیلم‌ها با اعتبارسنجی"""
    query = request.args.get('q', '')
    
    # اعتبارسنجی ورودی
    if not validate_input(query, max_length=50):
        return render_template('index.html')
    
    # پاکسازی ورودی
    query = sanitize_input(query)
    
    if query:
        movies = search_movies(query)
        return render_template('search_results.html', movies=movies, query=query)
    return render_template('index.html')

@app.route('/recommendations', methods=['GET', 'POST'])
def get_recommendations():
    """دریافت پیشنهادات بر اساس پاسخ‌های کاربر با اعتبارسنجی"""
    try:
        if request.method == 'POST':
            content_type = request.form.get('content_type', 'movie')
            genre_id = request.form.get('genre')
            year = request.form.get('year')
            min_rating = request.form.get('rating')
        else:  # GET method
            content_type = request.args.get('content_type', 'movie')
            genre_id = request.args.get('genre_id')
            year = request.args.get('year')
            min_rating = request.args.get('min_rating')
        
        # اعتبارسنجی ورودی‌ها
        valid_content_types = ['movie', 'series', 'animation', 'anime']
        if content_type not in valid_content_types:
            content_type = 'movie'
        
        # اعتبارسنجی page
        try:
            page = int(request.args.get('page', 1))
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
        
        # اعتبارسنجی سایر پارامترها
        if genre_id and not validate_input(str(genre_id), max_length=10):
            genre_id = None
        
        valid_years = ['2020', '2010', '2000', '1990']
        if year not in valid_years:
            year = None
        
        valid_ratings = ['8', '6', '4', '2']
        if min_rating not in valid_ratings:
            min_rating = None
        
        data = get_movies_by_preferences(genre_id, year, min_rating, content_type, page)
        
        return render_template('recommendations.html', 
                             movies=data['movies'],
                             total_pages=data['total_pages'],
                             current_page=data['current_page'],
                             genre_id=genre_id,
                             year=year,
                             min_rating=min_rating,
                             content_type=content_type)
    except Exception as e:
        # در صورت خطا، به صفحه اصلی برگردان
        return render_template('questions.html')

@app.route('/movie/<int:movie_id>')
def movie_details(movie_id):
    """نمایش جزئیات فیلم با اعتبارسنجی"""
    # اعتبارسنجی movie_id
    if not isinstance(movie_id, int) or movie_id <= 0:
        return render_template('404.html'), 404
    
    try:
        movie = get_movie_details(movie_id)
        if movie:
            similar_movies = get_similar_movies(movie_id)
            return render_template('movie_details.html', movie=movie, similar_movies=similar_movies)
    except Exception:
        pass
    return render_template('404.html'), 404

@app.route('/tv/<int:tv_id>')
def tv_details(tv_id):
    """نمایش جزئیات سریال با اعتبارسنجی"""
    # اعتبارسنجی tv_id
    if not isinstance(tv_id, int) or tv_id <= 0:
        return render_template('404.html'), 404
    
    try:
        tv = get_tv_details(tv_id)
        if tv:
            similar_tv = get_similar_tv(tv_id)
            return render_template('tv_details.html', tv=tv, similar_tv=similar_tv)
    except Exception:
        pass
    return render_template('404.html'), 404

@app.route('/person/<int:person_id>/<person_type>')
def person_movies(person_id, person_type):
    """نمایش فیلم‌های کارگردان یا بازیگر با اعتبارسنجی"""
    # اعتبارسنجی ورودی‌ها
    if not isinstance(person_id, int) or person_id <= 0:
        return render_template('404.html'), 404
    
    valid_person_types = ['director', 'actor']
    if person_type not in valid_person_types:
        return render_template('404.html'), 404
    
    try:
        # دریافت اطلاعات شخص
        url = f"{BASE_URL}/person/{person_id}"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'en-US'  # اطلاعات به انگلیسی
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return render_template('404.html'), 404
            
        person_data = response.json()
        person_name = person_data.get('name', 'ناشناس')
        
        # دریافت فیلم‌ها
        movies = get_person_movies(person_id, person_type)
        
        return render_template('person_movies.html', 
                             movies=movies,
                             person_name=person_name,
                             person_type=person_type)
    except Exception:
        return render_template('404.html'), 404

if __name__ == '__main__':
    # تنظیمات بهینه‌سازی Flask
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # کش فایل‌های استاتیک برای 1 سال
    app.config['TEMPLATES_AUTO_RELOAD'] = False  # غیرفعال کردن auto-reload در production
    
    # تنظیمات امنیتی اضافی
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 ساعت
    
    # غیرفعال کردن debug mode در production
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.run(debug=debug_mode, host='0.0.0.0', port=8080, threaded=True) 