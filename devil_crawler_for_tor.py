import requests, mysql.connector, re, urllib.parse, json
from bs4 import BeautifulSoup
from flask import Flask, request, render_template_string
from contextlib import contextmanager
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import logging, time, threading

app = Flask(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'kS8e!m@T4w9#Xq2v',
    'database': 'onion_crawler'
}

PROXIES = {
    'http': 'socks5h://127.0.0.1:9150',
    'https': 'socks5h://127.0.0.1:9150'
}

SEEDS = [
    "http://tordexpmg4xy32rfp4ovnz7zq5ujoejwq2u26uxxtkscgo5u3losmeid.onion/search?query={keyword}",
    "http://torlbmqwtudkorme6prgfpmsnile7ug2zm4u3ejpcncxuhpu4k2j4kyd.onion/index.php?a=search&q={keyword}",
    "http://bobby64o755x3gsuznts6hf6agxqjcz5bop6hs7ejorekbm7omes34ad.onion/search_result.php?search_text={keyword}&search_btn="
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

@contextmanager
def db_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS onion_urls (
                id INT AUTO_INCREMENT PRIMARY KEY,
                url VARCHAR(500) UNIQUE,
                title VARCHAR(300),
                description TEXT,
                genre VARCHAR(100),
                keywords TEXT
            )
        ''')
        conn.commit()

def extract_metadata(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        title = a.get_text(strip=True)
        if re.search(r'\.(onion|i2p|loki)\b', href) and href.startswith('http'):
            links.append({'url': href, 'title': title})
    description = ''
    desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
    if desc_tag and desc_tag.get('content'):
        description = desc_tag['content'].strip()
    genre = ''
    genre_tag = soup.find(string=re.compile(r'Género|Category|Tags', re.I))
    if genre_tag:
        genre = genre_tag.strip()
    return links, description, genre

def save_url(url, title, description, genre, keyword):
    keywords = keyword + ' ' + ' '.join(keyword.split()) + ' ' + title.lower()
    if not url or not title:
        return
    domain_type = ''
    if '.onion' in url:
        domain_type = 'onion'
    elif '.i2p' in url:
        domain_type = 'i2p'
    elif '.loki' in url:
        domain_type = 'loki'
    elif keyword in url.lower() or keyword in title.lower():
        domain_type = 'unknown'
    else:
        return
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT IGNORE INTO onion_urls (url, title, description, genre, keywords)
            VALUES (%s, %s, %s, %s, %s)
        """, (url, title, description, genre, keywords))
        conn.commit()

def crawl_and_store(keyword):
    collected = []
    def crawl_seed(seed):
        url = seed.format(keyword=urllib.parse.quote(keyword))
        try:
            response = requests.get(url, proxies=PROXIES, timeout=25)
            if response.status_code == 200:
                links, description, genre = extract_metadata(response.text)
                for item in links:
                    save_url(item['url'], item['title'], description, genre, keyword)
                    collected.append((item['url'], item['title'], description, genre))
        except: pass
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(crawl_seed, SEEDS)
    return collected

def expand_keywords(keyword):
    base = keyword.lower().strip()
    parts = base.split()
    variants = set([base])
    for part in parts:
        if len(part) > 4:
            variants.add(part)
            variants.add(part[:-1])
            variants.add(part[:4])
    return list(variants)

def devil_search(keyword):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT url, title, description, genre FROM onion_urls 
            WHERE MATCH(title, url, description, genre, keywords) AGAINST (%s IN NATURAL LANGUAGE MODE)
        """, (keyword,))
        db_results = cursor.fetchall()
    variants = expand_keywords(keyword)
    live_results = []
    for kw in variants:
        live_results.extend(crawl_and_store(kw))
    combined = list({(url, title, desc, genre) for (url, title, desc, genre) in db_results + live_results})
    return combined if combined else get_recent_urls()

def get_recent_urls(limit=10):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, description, genre FROM onion_urls ORDER BY id DESC LIMIT %s", (limit,))
        return cursor.fetchall()

def normalize_keyword(raw):
    return re.sub(r'\s+', ' ', raw.strip().lower())

def get_total_indexed():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM onion_urls")
        return cursor.fetchone()[0]

@app.route('/', methods=['GET', 'POST'])
def index():
    keyword = normalize_keyword(request.form.get('keyword', '') if request.method == 'POST' else request.args.get('keyword', ''))
    page = int(request.args.get('page', 1))
    per_page = 10
    results = devil_search(keyword) if keyword else []
    total = len(results)
    total_pages = (total + per_page - 1) // per_page
    paginated = results[(page - 1) * per_page : page * per_page]
    total_indexed = get_total_indexed()
    return render_template_string('''
    <!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Locknia - Motor de búsqueda especializado para la red TOR">
    <meta name="keywords" content="tor, dark web, buscador, anónimo, privacidad">
    <meta name="author" content="Locknia">
    <meta name="robots" content="noindex, nofollow">
    <meta name="referrer" content="no-referrer">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <meta name="theme-color" content="#ff0055">
    <meta name="color-scheme" content="dark">
    
    <!-- Favicon -->
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🕸️</text></svg>">
    
    <title>Locknia - Dark Web Search</title>
    <style>
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #1a1a1a;
            --accent-primary: #ff0055;
            --accent-secondary: #cc0044;
            --text-primary: #ffffff;
            --text-secondary: #b0b0b0;
            --text-muted: #666666;
            --border-color: #333333;
            --shadow-soft: 0 4px 20px rgba(0, 0, 0, 0.3);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
            line-height: 1.5;
        }

        .container {
            width: 100%;
            max-width: 700px;
            margin: 0 auto;
        }

        /* Header Styles */
        .brand-header {
            text-align: center;
            margin-bottom: 50px;
        }

        .spider-icon {
            font-size: 80px;
            color: var(--accent-primary);
            margin-bottom: 20px;
            animation: float 3s ease-in-out infinite;
            filter: drop-shadow(0 0 10px rgba(255, 0, 85, 0.3));
        }

        .brand-name {
            font-size: 3.5rem;
            font-weight: 300;
            color: var(--text-primary);
            letter-spacing: 3px;
            margin-bottom: 10px;
        }

        .brand-tagline {
            font-size: 1.1rem;
            color: var(--text-secondary);
            font-weight: 300;
            letter-spacing: 1px;
        }

        /* Stats Section */
        .stats-container {
            text-align: center;
            margin-bottom: 40px;
            padding: 15px;
        }

        .stats-value {
            color: var(--accent-primary);
            font-weight: 500;
            font-size: 1.2rem;
        }

        /* Search Form */
        .search-container {
            width: 100%;
            margin-bottom: 50px;
        }

        .search-form {
            display: flex;
            flex-direction: column;
            gap: 20px;
            align-items: center;
        }

        .search-input {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            padding: 18px 25px;
            border-radius: 50px;
            font-size: 1.1rem;
            width: 100%;
            max-width: 600px;
            transition: all 0.3s ease;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 2px rgba(255, 0, 85, 0.1);
        }

        .search-button {
            background: var(--accent-primary);
            color: white;
            border: none;
            padding: 16px 40px;
            border-radius: 50px;
            font-size: 1.1rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            min-width: 200px;
        }

        .search-button:hover {
            background: var(--accent-secondary);
            transform: translateY(-2px);
            box-shadow: var(--shadow-soft);
        }

        /* Results Section */
        .results-header {
            margin-bottom: 30px;
            text-align: center;
        }

        .results-title {
            font-size: 1.5rem;
            margin-bottom: 8px;
            font-weight: 400;
        }

        .results-count {
            color: var(--text-secondary);
            font-size: 1rem;
        }

        .results-list {
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-bottom: 40px;
        }

        .result-item {
            background: var(--bg-secondary);
            padding: 25px;
            border-radius: 16px;
            border: 1px solid var(--border-color);
            transition: transform 0.2s ease;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }

        .result-item:hover {
            transform: translateY(-2px);
            border-color: var(--accent-primary);
        }

        .result-title {
            margin-bottom: 12px;
        }

        .result-title a {
            color: var(--accent-primary);
            font-weight: 500;
            font-size: 1.2rem;
            text-decoration: none;
            line-height: 1.4;
        }

        .result-title a:hover {
            text-decoration: underline;
        }

        .result-url {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-bottom: 15px;
            word-break: break-all;
            line-height: 1.4;
        }

        .result-desc {
            font-size: 1rem;
            color: var(--text-secondary);
            line-height: 1.6;
        }

        /* Pagination */
        .pagination {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            margin-top: 40px;
            flex-wrap: wrap;
        }

        .pagination a, .pagination strong {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 44px;
            height: 44px;
            padding: 0 16px;
            border-radius: 8px;
            font-weight: 500;
            text-decoration: none;
            font-size: 1rem;
        }

        .pagination a {
            background: var(--bg-secondary);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
        }

        .pagination a:hover {
            background: var(--accent-primary);
            color: white;
            border-color: var(--accent-primary);
        }

        .pagination strong {
            background: var(--accent-primary);
            color: white;
        }

        /* No Results */
        .no-results {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
            font-size: 1.1rem;
        }

        /* Animations */
        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
        }

        /* Responsive Design */
        @media (max-width: 768px) {
            body {
                padding: 30px 15px;
            }
            
            .brand-name {
                font-size: 2.8rem;
            }
            
            .spider-icon {
                font-size: 70px;
            }
            
            .search-input {
                padding: 16px 22px;
                font-size: 1rem;
            }
            
            .search-button {
                padding: 15px 35px;
                font-size: 1rem;
            }
            
            .result-item {
                padding: 20px;
            }
        }

        @media (max-width: 480px) {
            .brand-name {
                font-size: 2.2rem;
                letter-spacing: 2px;
            }
            
            .brand-tagline {
                font-size: 1rem;
            }
            
            .spider-icon {
                font-size: 60px;
            }
            
            .search-input {
                padding: 14px 20px;
            }
            
            .search-button {
                padding: 14px 30px;
                min-width: 180px;
                width: 100%;
                max-width: 280px;
            }
            
            .result-item {
                padding: 18px;
            }
            
            .results-title {
                font-size: 1.3rem;
            }
        }

        /* Soporte específico para iPad */
        @media (min-width: 768px) and (max-width: 1024px) {
            .container {
                max-width: 90%;
            }
            
            .brand-name {
                font-size: 3rem;
            }
        }

        /* Soporte específico para iPhone */
        @media (max-width: 375px) {
            .brand-name {
                font-size: 2rem;
            }
            
            .spider-icon {
                font-size: 50px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Brand Header -->
        <header class="brand-header">
            <div class="spider-icon">🕸️</div>
            <h1 class="brand-name">LOCKNIA</h1>
            <p class="brand-tagline">Dark Web Search Engine</p>
        </header>

        <!-- Stats Section -->
        <div class="stats-container">
            <p>Total de URLs indexadas: <span class="stats-value">{{ total_indexed }}</span></p>
        </div>

        <!-- Search Form -->
        <div class="search-container">
            <form method="post" class="search-form">
                <input type="text" name="keyword" class="search-input" 
                       placeholder="Buscar en la red oscura..." value="{{ keyword }}" 
                       autocomplete="off" autofocus>
                <button type="submit" class="search-button">Buscar</button>
            </form>
        </div>

        <!-- Results Section -->
        {% if keyword %}
            <div class="results-header">
                <h2 class="results-title">Resultados para "{{ keyword }}"</h2>
                <p class="results-count">{{ total }} encontrados</p>
            </div>

            {% if total == 0 %}
                <div class="no-results">
                    <p>No se encontraron coincidencias exactas. El crawler está activado. Vuelve en unos segundos...</p>
                </div>
            {% else %}
                <div class="results-list">
                    {% for url, title, description, genre in paginated %}
                        <div class="result-item">
                            <div class="result-title">
                                <a href="{{ url }}" target="_blank">{{ title or 'Sin título' }}</a>
                            </div>
                            <div class="result-url">{{ url }}</div>
                            <div class="result-desc">{{ description or 'Sin descripción disponible' }}</div>
                        </div>
                    {% endfor %}
                </div>

                <!-- Pagination -->
                {% if total_pages > 1 %}
                    <div class="pagination">
                        {% for p in range(1, total_pages + 1) %}
                            {% if p == page %}
                                <strong>{{ p }}</strong>
                            {% else %}
                                <a href="/?keyword={{ keyword }}&page={{ p }}">{{ p }}</a>
                            {% endif %}
                        {% endfor %}
                    </div>
                {% endif %}
            {% endif %}
        {% endif %}
    </div>
</body>
</html>

    ''', keyword=keyword, results=results, paginated=paginated, page=page,
         total_pages=total_pages, total=total, total_indexed=total_indexed)


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5030, debug=False)
