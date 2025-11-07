import requests, mysql.connector, re, urllib.parse, json
from bs4 import BeautifulSoup
from flask import Flask, request, render_template_string
from contextlib import contextmanager
from datetime import datetime, timedelta
import logging
import time

import threading
import logging


app = Flask(__name__)

# Configuración de base de datos
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'kS8e!m@T4w9#Xq2v',
    'database': 'onion_crawler'
}

# Proxy Tor
PROXIES = {
    'http': 'socks5h://127.0.0.1:9150',
    'https': 'socks5h://127.0.0.1:9150'
}

# Seeds de búsqueda
SEEDS = [
    "http://tordexpmg4xy32rfp4ovnz7zq5ujoejwq2u26uxxtkscgo5u3losmeid.onion/search?query={keyword}",
    "http://torlbmqwtudkorme6prgfpmsnile7ug2zm4u3ejpcncxuhpu4k2j4kyd.onion/index.php?a=search&q={keyword}",
    "http://bobby64o755x3gsuznts6hf6agxqjcz5bop6hs7ejorekbm7omes34ad.onion/search_result.php?search_text={keyword}&search_btn="
]
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("crawler.log"),
        logging.StreamHandler()  # ✅ Esto activa la salida en consola
    ]
)


@contextmanager
def db_connection():
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        yield conn
    finally:
        if conn:
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
                genre VARCHAR(100)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_cache (
                query VARCHAR(255) PRIMARY KEY,
                results LONGTEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cursor.close()

def background_indexer():
    keywords = ['market','bitcoin']
    while True:
        for kw in keywords:
            crawl_and_store(kw)
            time.sleep(300)  # cada 5 minutos por keyword

def extract_metadata(html):
    soup = BeautifulSoup(html, 'html.parser')
    links = []

    for a in soup.find_all('a', href=True):
        href = a['href']
        title = a.get_text(strip=True)
        if re.search(r'\.(onion|i2p|loki)\b', href) and href.startswith('http'):
            links.append({'url': href, 'title': title})

    if links:
        logging.info(f"[EXTRACT] Se extrajeron {len(links)} enlaces válidos.")

    description = ''
    desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
    if desc_tag and desc_tag.get('content'):
        description = desc_tag['content'].strip()

    genre = ''
    genre_tag = soup.find(string=re.compile(r'Género|Category|Tags', re.I))
    if genre_tag:
        genre = genre_tag.strip()

    return links, description, genre



from concurrent.futures import ThreadPoolExecutor

def crawl_and_store(keyword):
    logging.info(f"Iniciando crawling para: {keyword}")
    saved = 0
    def crawl_seed(seed):
        nonlocal saved
        url = seed.format(keyword=urllib.parse.quote(keyword))
        try:
            response = requests.get(url, proxies=PROXIES, timeout=25)
            if response.status_code == 200:
                links, description, genre = extract_metadata(response.text)
                for item in links:
                    save_url(item['url'], item['title'], description, genre, keyword)
                    logging.info(f"[CRAWL] Acceso exitoso a: {url}")
                    logging.info(f"[CRAWL] Enlaces extraídos: {len(links)}")

                    


                    saved += 1
        except Exception as e:
            logging.error(f"Error al acceder a {url}: {e}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(crawl_seed, SEEDS)

    logging.info(f"Crawler para '{keyword}' guardó {saved} enlaces.")


def save_url(url, title, description, genre, keyword):
    keywords = keyword + ' ' + ' '.join(keyword.split())

    if not url:
        logging.warning(f"URL ignorada por falta de URL: {url}")
        return
    if not title:
        title = keyword

    domain_type = ''
    if '.onion' in url:
        domain_type = 'onion'
    elif '.i2p' in url:
        domain_type = 'i2p'
    elif '.loki' in url:
        domain_type = 'loki'
    elif keyword in url.lower():
        domain_type = 'unknown'  # ✅ Permitir si el keyword está en el URL
    else:
        logging.info(f"Dominio desconocido y sin coincidencia: {url}")
        return

    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT IGNORE INTO onion_urls (url, title, description, genre, domain_type, keywords)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (url, title, description, genre, domain_type, keywords))
            conn.commit()
            if cursor.rowcount == 0:
                logging.info(f"URL duplicada o ignorada: {url}")
        except Exception as e:
            logging.error(f"Error al guardar: {e}")
        finally:
            cursor.close()



def search_urls(keyword, use_cache=True):
    logging.info(f"Búsqueda iniciada para: {keyword}")
    with db_connection() as conn:
        cursor = conn.cursor()

        if use_cache:
            cursor.execute("""
                SELECT results FROM search_cache 
                WHERE query = %s AND cached_at > %s
            """, (keyword, datetime.now() - timedelta(minutes=30)))
            cached = cursor.fetchone()
            if cached:
                result_data = json.loads(cached[0])
                cursor.close()
                logging.info(f"Resultado obtenido desde caché para '{keyword}'")
                return result_data

        time.sleep(2)  # margen para crawling

        try:
            cursor.execute("""
                SELECT url, title, description, genre FROM onion_urls 
                WHERE MATCH(title, url, description, genre, keywords) AGAINST (%s IN NATURAL LANGUAGE MODE)
            """, (keyword,))
            results = cursor.fetchall()
        except Exception as e:
            logging.error(f"Error en búsqueda semántica: {e}")
            results = []

        if results and use_cache:
            try:
                cursor.execute("""
                    INSERT INTO search_cache (query, results) VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE results = VALUES(results), cached_at = CURRENT_TIMESTAMP
                """, (keyword, json.dumps(results)))
                conn.commit()
            except Exception as e:
                logging.error(f"Error al guardar en caché: {e}")

        cursor.close()
        return results


def normalize_keyword(raw):
    return re.sub(r'\s+', ' ', raw.strip().lower())


def get_total_indexed():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM onion_urls")
        total = cursor.fetchone()[0]
        cursor.close()
        return total




active_rescues = set()
rescue_lock = threading.Lock()

def rescue_crawler(keyword):
    with rescue_lock:
        if keyword in active_rescues:
            logging.info(f"[RESCUE] Ya hay un rescate activo para '{keyword}', se omite.")
            return
        active_rescues.add(keyword)

    logging.info(f"[RESCUE] Activando crawler de rescate para: {keyword}")
    try:
        for seed in SEEDS:
            url = seed.format(keyword=urllib.parse.quote(keyword))
            for attempt in range(3):
                try:
                    logging.info(f"[RESCUE] Intento {attempt+1} accediendo a: {url}")
                    response = requests.get(url, proxies=PROXIES, timeout=25)
                    if response.status_code == 200:
                        links, description, genre = extract_metadata(response.text)
                        for item in links:
                            save_url(item['url'], item['title'], description, genre, keyword)
                            logging.info(f"[RESCUE] Guardado: {item['url']}")
                        break
                except Exception as e:
                    logging.warning(f"[RESCUE] Intento {attempt+1} falló para {url}: {e}")
                    time.sleep(5)
    finally:
        with rescue_lock:
            active_rescues.discard(keyword)


@app.route('/', methods=['GET', 'POST'])
def index():
    keyword = normalize_keyword(
        request.form.get('keyword', '') if request.method == 'POST'
        else request.args.get('keyword', '')
    )

    page = int(request.args.get('page', 1))
    per_page = 10
    results = []

    if keyword:
        logging.info(f"Usuario buscó: '{keyword}'")

        # ✅ Usa caché primero, sin bloquear
        results = search_urls(keyword, use_cache=True)

        # ✅ Si no hay resultados, lanza rescate en segundo plano
        if not results:
            logging.info(f"No hay resultados para '{keyword}', lanzando rescate en segundo plano...")
            threading.Thread(target=rescue_crawler, args=(keyword,), daemon=True).start()
            # No bloqueamos, mostramos lo que haya (vacío o caché previa)
    else:
        logging.info("Búsqueda sin keyword, mostrando página vacía.")

    total = len(results)
    total_pages = (total + per_page - 1) // per_page
    paginated = results[(page - 1) * per_page : page * per_page]
    total_indexed = get_total_indexed()

    return render_template_string('''
                                  <style>
    body { font-family: Arial, sans-serif; margin: 40px; background: #f9f9f9; }
    h3 { color: #333; }
    form input { padding: 8px; width: 300px; }
    form button { padding: 8px 12px; }
    ul { list-style: none; padding: 0; }
    li { margin-bottom: 15px; background: #fff; padding: 10px; border-radius: 5px; box-shadow: 0 0 5px rgba(0,0,0,0.1); }
    small { color: #666; }
    .pagination a { margin: 0 5px; text-decoration: none; }
    .pagination strong { margin: 0 5px; }
</style>

        <h3>Total de URLs .onion indexadas: {{ total_indexed }}</h3>
        <form method="post">
            <input name="keyword" placeholder="Buscar keyword .onion" value="{{ keyword }}">
            <button type="submit">Buscar</button>
        </form>

        {% if keyword %}
            <h3>Resultados para "{{ keyword }}" ({{ total }} encontrados)</h3>
            {% if total == 0 %}
                <p><em>No se encontraron coincidencias exactas para "{{ keyword }}". El sistema está intentando recuperar datos. Vuelve en unos segundos.</em></p>
            {% endif %}

            <ul>
            {% for url, title, description, genre in paginated %}
                <li>
                    <a href="{{ url }}" target="_blank"><strong>{{ title }}</strong></a><br>
                    <em>{{ description or 'Sin descripción disponible' }}</em><br>
                    {% if genre %}<small>Género: {{ genre }}</small>{% endif %}
                </li>
            {% endfor %}
            </ul>

            <div class="pagination">
                {% for p in range(1, total_pages + 1) %}
                    {% if p == page %}
                        <strong>[{{ p }}]</strong>
                    {% else %}
                        <a href="/?keyword={{ keyword }}&page={{ p }}">{{ p }}</a>
                    {% endif %}
                {% endfor %}
            </div>

        {% endif %}
    ''', keyword=keyword, results=results, paginated=paginated, page=page, total_pages=total_pages, total=total, total_indexed=total_indexed)






threading.Thread(target=background_indexer, daemon=True).start()

if __name__ == '__main__':
    try:
        app.run(host='127.0.0.1', port=5030, debug=False)
    except KeyboardInterrupt:
        logging.info("Servidor detenido manualmente.")


